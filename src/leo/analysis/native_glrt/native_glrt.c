#define _POSIX_C_SOURCE 200809L

#include "native_glrt.h"

#include <fenv.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "kernel/private_namespace.h"
static int regional_count;
static int regional_epochs[13334];
#include "kernel/private/full_search.c"
#include "kernel/private/dwell_input.h"
#include "kernel/private/proposal_core.h"
#include "kernel/private/proposal_tracking.h"

struct leo_native_glrt {
    uint32_t rate;
    size_t frame;
    leo_presence_workspace *search;
    leo_proposal_workspace *proposal;
};

_Static_assert(sizeof(leo_native_glrt_complex)==sizeof(leo_presence_complex),
    "public and frozen template lanes must have identical storage");

static atomic_flag process_busy = ATOMIC_FLAG_INIT;

static int enter(void)
{
    return atomic_flag_test_and_set_explicit(&process_busy,memory_order_acquire)
        ? LEO_NATIVE_GLRT_BUSY : LEO_NATIVE_GLRT_OK;
}

static void leave(void)
{
    atomic_flag_clear_explicit(&process_busy,memory_order_release);
}

static int cpu_ms(double *result)
{
    struct timespec value;
    if(!result||clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&value))return -1;
    *result=1000.0*(double)value.tv_sec+1e-6*(double)value.tv_nsec;return 0;
}

static int valid_rate(uint32_t rate)
{
    return rate==2500000u || rate==5000000u ||
        rate==7500000u || rate==10000000u;
}

int leo_native_glrt_layout(uint32_t rate,uint32_t dwell_ms,uint32_t stride_ms,
    size_t *complex_times,size_t *row_count)
{
    if(!complex_times||!row_count||!valid_rate(rate)||
       (dwell_ms!=120&&dwell_ms!=240&&dwell_ms!=360)||
       (stride_ms!=10&&stride_ms!=20&&stride_ms!=120))
        return LEO_NATIVE_GLRT_INVALID;
    *complex_times=(size_t)rate*dwell_ms/1000u;
    *row_count=2u*(1u+(dwell_ms-20u)/stride_ms);
    return *row_count<=LEO_NATIVE_GLRT_MAX_ROWS
        ? LEO_NATIVE_GLRT_OK:LEO_NATIVE_GLRT_INVALID;
}

static void copy_candidate(leo_native_glrt_candidate *to,
    const leo_full_search_candidate *from)
{
    const leo_presence_candidate *candidate=&from->candidate;
    *to=(leo_native_glrt_candidate){
        .coarse_epoch=from->coarse_epoch,.coarse_bin=from->coarse_bin,
        .refined_epoch=from->refined_epoch,.frame_support=from->frame_support,
        .glrt_complete=from->glrt_complete,
        .conditioned_fallback=from->conditioned_fallback,
        .refinement_skipped=from->refinement_skipped,
        .coarse_cfo_hz=from->coarse_cfo_hz,.fine_cfo_hz=from->fine_cfo_hz,
        .conditioned_cfo_hz=from->conditioned_cfo_hz,
        .epoch=candidate->epoch,.acquired_cfo_hz=candidate->acquired_cfo_hz,
        .tracking_cfo_hz=candidate->tracking_cfo_hz,
        .exact_score=candidate->exact_score,.control_score=candidate->control_score,
        .margin=candidate->margin,.acquire_score=candidate->acquire_score,
        .verify_score=candidate->verify_score,
        .verify_control_score=candidate->verify_control_score,
        .conditioned_score=candidate->conditioned_score,
        .coarse_score=candidate->coarse_score};
}

static void copy_row(leo_native_glrt_row *to,int receiver,int probe_index,
    int start_ms,const leo_full_search_result *search,
    const leo_proposal_timing *proposal,int proposal_executed,
    int tracking_fallback,int neighbor_matches)
{
    *to=(leo_native_glrt_row){
        .receiver_id=receiver,.probe_index=probe_index,.probe_start_ms=start_ms,
        .proposal_executed=proposal_executed,
        .proposal_tracking_fallback=tracking_fallback,
        .proposal_neighbor_matches=neighbor_matches,
        .candidate_count=search->candidate_count,
        .retained_peak_count=search->retained_peak_count,
        .coarse_gate_skipped_count=search->coarse_gate_skipped_count,
        .conditioned_fallback_count=search->conditioned_fallback_count,
        .actual_executed_glrt_calls=search->actual_executed_glrt_calls,
        .glrt_cache_hits=search->glrt_cache_hits,
        .conditioned_cache_hits=search->conditioned_cache_hits,
        .fine_fft_cache_entries=search->fine_fft_cache_entries,
        .fine_fft_cache_hits=search->fine_fft_cache_hits,
        .fine_precision_calls=search->fine_precision_calls,
        .fine_precision_guard_checks=search->fine_precision_guard_checks,
        .fine_precision_fallbacks=search->fine_precision_fallbacks,
        .fine_precision_nonfinite_fallbacks=search->fine_precision_nonfinite_fallbacks,
        .fine_precision_near_tie_fallbacks=search->fine_precision_near_tie_fallbacks,
        .fine_precision_interpolation_fallbacks=search->fine_precision_interpolation_fallbacks,
        .conditioned_bins_screened=search->conditioned_bins_screened,
        .conditioned_bins_rechecked=search->conditioned_bins_rechecked,
        .total_cpu_ms=search->total_cpu_ms,.proposal_ms=proposal->total_ms,
        .stage_sum_ms=proposal->total_ms+search->total_cpu_ms,
        .proposal_fold_ms=proposal->fold_ms,
        .proposal_correlation_ms=proposal->correlation_ms,
        .proposal_ranking_ms=proposal->ranking_ms,
        .coarse_ms=search->coarse_cpu_ms,.acquisition_ms=search->acquisition_cpu_ms,
        .fine_fft_ms=search->fine_fft_cpu_ms,
        .conditioned_ms=search->conditioned_cpu_ms,
        .verification_ms=search->verification_cpu_ms,.glrt_ms=search->glrt_cpu_ms};
    for(int i=0;i<search->candidate_count;++i)
        copy_candidate(&to->candidates[i],&search->candidates[i]);
}

static int finite_result(const leo_native_glrt_result *result)
{
    for(size_t r=0;r<result->row_count;++r){
        const leo_native_glrt_row *row=&result->rows[r];
        const double timings[]={row->total_cpu_ms,row->proposal_ms,row->stage_sum_ms,
            row->proposal_fold_ms,row->proposal_correlation_ms,row->proposal_ranking_ms,
            row->coarse_ms,row->acquisition_ms,row->fine_fft_ms,row->conditioned_ms,
            row->verification_ms,row->glrt_ms};
        for(size_t i=0;i<sizeof(timings)/sizeof(timings[0]);++i)
            if(!isfinite(timings[i]))return 0;
        if(row->candidate_count<0||row->candidate_count>LEO_NATIVE_GLRT_MAX_CANDIDATES)
            return 0;
        for(int i=0;i<row->candidate_count;++i){
            const leo_native_glrt_candidate *c=&row->candidates[i];
            const double values[]={c->coarse_cfo_hz,c->fine_cfo_hz,
                c->conditioned_cfo_hz,c->acquired_cfo_hz,c->tracking_cfo_hz,
                c->exact_score,c->control_score,c->margin,c->acquire_score,
                c->verify_score,c->verify_control_score,c->conditioned_score,
                c->coarse_score};
            for(size_t j=0;j<sizeof(values)/sizeof(values[0]);++j)
                if(!isfinite(values[j]))return 0;
        }
    }
    return 1;
}

int leo_native_glrt_create(leo_native_glrt **out,uint32_t rate,
    const leo_native_glrt_complex *exact,const leo_native_glrt_complex *control,
    size_t count)
{
    if(!out||!exact||!control||!valid_rate(rate)||
       count!=(rate+375u)/750u||fegetround()!=FE_TONEAREST)
        return LEO_NATIVE_GLRT_INVALID;
    *out=NULL;
    int status=enter();if(status)return status;
    leo_presence_complex *native_exact=malloc(count*sizeof(*native_exact));
    leo_presence_complex *native_control=malloc(count*sizeof(*native_control));
    double (*proposal_template)[2]=malloc(count*sizeof(*proposal_template));
    if(!native_exact||!native_control||!proposal_template){
        free(proposal_template);free(native_control);free(native_exact);leave();
        return LEO_NATIVE_GLRT_NOMEM;
    }
    for(size_t i=0;i<count;++i){
        if(!isfinite(exact[i].real)||!isfinite(exact[i].imaginary)||
           !isfinite(control[i].real)||!isfinite(control[i].imaginary)||
           fabs(exact[i].real)>16||fabs(exact[i].imaginary)>16||
           fabs(control[i].real)>16||fabs(control[i].imaginary)>16){
            free(proposal_template);free(native_control);free(native_exact);leave();
            return LEO_NATIVE_GLRT_INVALID;
        }
        native_exact[i]=(leo_presence_complex){exact[i].real,exact[i].imaginary};
        native_control[i]=(leo_presence_complex){control[i].real,control[i].imaginary};
        proposal_template[i][0]=exact[i].real;proposal_template[i][1]=exact[i].imaginary;
    }
    leo_native_glrt *context=calloc(1,sizeof(*context));
    if(!context){free(proposal_template);free(native_control);free(native_exact);leave();return LEO_NATIVE_GLRT_NOMEM;}
    context->rate=rate;context->frame=count;
    context->search=leo_presence_create(rate,native_exact,native_control,count);
    context->proposal=leo_proposal_create(proposal_template,count,(double)rate);
    free(proposal_template);free(native_control);free(native_exact);
    if(!context->search||!context->proposal){
        if(context->proposal)leo_proposal_destroy(context->proposal);
        if(context->search)leo_presence_destroy(context->search);
        free(context);leave();return LEO_NATIVE_GLRT_NOMEM;
    }
    *out=context;leave();return LEO_NATIVE_GLRT_OK;
}

int leo_native_glrt_destroy(leo_native_glrt *context)
{
    if(!context)return LEO_NATIVE_GLRT_INVALID;
    int status=enter();if(status)return status;
    leo_proposal_destroy(context->proposal);
    leo_presence_destroy(context->search);
    free(context);leave();return LEO_NATIVE_GLRT_OK;
}

int leo_native_glrt_analyze(leo_native_glrt *context,const int16_t *ci16,
    size_t complex_times,uint32_t dwell_ms,uint32_t stride_ms,
    leo_native_glrt_result *result)
{
    size_t required_times=0,row_count=0;
    if(!context||!ci16||!result||
       leo_native_glrt_layout(context->rate,dwell_ms,stride_ms,
           &required_times,&row_count)||complex_times!=required_times)
        return LEO_NATIVE_GLRT_INVALID;
    size_t windows=row_count/2;
    if(fegetround()!=FE_TONEAREST)return LEO_NATIVE_GLRT_INVALID;
    int status=enter();if(status)return status;
    double started=0,finished=0;
    if(cpu_ms(&started)){leave();return LEO_NATIVE_GLRT_KERNEL;}
    leo_native_glrt_result temporary={0};
    leo_dwell_input prepared={0};
    unsigned char *selected=calloc(context->frame,1);
    size_t anchors=1+(dwell_ms-20)/20;
    int (*centers)[2][4]=calloc(anchors,sizeof(*centers));
    int (*counts)[2]=calloc(anchors,sizeof(*counts));
    leo_proposal_timing (*timings)[2]=calloc(anchors,sizeof(*timings));
    if(!selected||!centers||!counts||!timings||
       leo_dwell_input_prepare(&prepared,ci16,complex_times)){
        status=LEO_NATIVE_GLRT_NOMEM;goto done;
    }
    /* Sparse strides execute only scheduled anchors. Dense stride 10 needs all
     * 20 ms anchors to reproduce the frozen odd-window neighbor tracking. */
    for(size_t window=0;window<windows;++window){
        unsigned start_ms=(unsigned)window*stride_ms;
        if(stride_ms==10 && start_ms%20)continue;
        size_t anchor=start_ms/20;
        for(int rx=0;rx<2;++rx)
            if(leo_proposal_top4(context->proposal,ci16,
                (size_t)start_ms*context->rate/1000u,rx,
                centers[anchor][rx],&counts[anchor][rx],&timings[anchor][rx])){
                status=LEO_NATIVE_GLRT_KERNEL;goto done;
            }
    }
    for(size_t window=0;window<windows;++window)for(int rx=0;rx<2;++rx){
        unsigned start_ms=(unsigned)window*stride_ms;
        int current[4]={0},count=0,executed=0,fallback=0,matches=0;
        leo_proposal_timing timing={0};
        if(start_ms%20==0){
            size_t anchor=start_ms/20;count=counts[anchor][rx];
            memcpy(current,centers[anchor][rx],sizeof(current));
            timing=timings[anchor][rx];executed=1;
        }else{
            size_t left=start_ms/20,right=left+1;
            count=leo_tracked_centers(centers[left][rx],counts[left][rx],
                centers[right][rx],counts[right][rx],(int)(start_ms/10),
                context->rate,(int)context->frame,current,&matches);
            if(!count){
                if(leo_proposal_top4(context->proposal,ci16,
                    (size_t)start_ms*context->rate/1000u,rx,current,&count,&timing)){
                    status=LEO_NATIVE_GLRT_KERNEL;goto done;
                }
                executed=1;fallback=1;
            }
        }
        if(count>4)count=4;
        memset(selected,0,context->frame);
        for(int c=0;c<count;++c){
            int first=current[c]-1,last=current[c]+1;
            if(first<0)first=0;
            if(last>=(int)context->frame)last=(int)context->frame-1;
            for(int epoch=first;epoch<=last;++epoch)selected[epoch]=1;
        }
        regional_count=0;
        for(size_t epoch=0;epoch<context->frame;++epoch)
            if(selected[epoch])regional_epochs[regional_count++]=(int)epoch;
        size_t offset=(size_t)start_ms*context->rate/1000u;
        leo_full_search_result search;
        if(leo_full_search_run_prepared(context->search,prepared.raw[rx]+offset,
            prepared.normalized[rx]+2*offset,prepared.prefix[rx]+offset,
            context->rate/50u,&search)){
            status=LEO_NATIVE_GLRT_KERNEL;goto done;
        }
        copy_row(&temporary.rows[temporary.row_count++],rx,(int)window,
            (int)start_ms,&search,&timing,executed,fallback,matches);
    }
    status=LEO_NATIVE_GLRT_OK;
done:
    leo_dwell_input_free(&prepared);free(timings);free(counts);free(centers);free(selected);
    if(status==LEO_NATIVE_GLRT_OK){
        if(cpu_ms(&finished))status=LEO_NATIVE_GLRT_KERNEL;
        else {
            temporary.detector_cpu_ms=finished-started;
            if(!isfinite(temporary.detector_cpu_ms)||!finite_result(&temporary))
                status=LEO_NATIVE_GLRT_KERNEL;
            else *result=temporary;
        }
    }
    leave();return status;
}

const char *leo_native_glrt_status_string(int status)
{
    switch(status){
    case LEO_NATIVE_GLRT_OK:return "ok";
    case LEO_NATIVE_GLRT_INVALID:return "invalid argument";
    case LEO_NATIVE_GLRT_NOMEM:return "out of memory";
    case LEO_NATIVE_GLRT_BUSY:return "process-global kernel busy";
    case LEO_NATIVE_GLRT_KERNEL:return "detector kernel failed";
    default:return "unknown error";
    }
}
