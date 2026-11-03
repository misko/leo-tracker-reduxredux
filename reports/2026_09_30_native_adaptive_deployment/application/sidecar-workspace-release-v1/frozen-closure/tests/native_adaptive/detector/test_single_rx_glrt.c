#define _POSIX_C_SOURCE 200809L

#include "native_glrt.h"
#include "single_rx_glrt.h"

#include <fenv.h>
#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    leo_single_rx_glrt *context;
    const int16_t *samples;
    size_t count;
    pthread_barrier_t *barrier;
    int status;
    leo_native_glrt_result result;
} call;

static void *run_call(void *opaque)
{
    call *item=opaque;
    pthread_barrier_wait(item->barrier);
    item->status=leo_single_rx_glrt_analyze(item->context,item->samples,
        item->count,120,10,&item->result);
    return NULL;
}

static int read_exact(const char *path,void **data,size_t *size)
{
    FILE *file=fopen(path,"rb");
    if(!file||fseek(file,0,SEEK_END))return -1;
    long end=ftell(file);
    if(end<=0||fseek(file,0,SEEK_SET)){fclose(file);return -1;}
    void *value=malloc((size_t)end);
    if(!value||fread(value,1,(size_t)end,file)!=(size_t)end||fgetc(file)!=EOF){
        free(value);fclose(file);return -1;
    }
    fclose(file);*data=value;*size=(size_t)end;return 0;
}

static int same_candidate(const leo_native_glrt_candidate *a,
    const leo_native_glrt_candidate *b)
{
#define SAME_FIELD(name) if(memcmp(&a->name,&b->name,sizeof(a->name)))return 0
    SAME_FIELD(coarse_epoch);SAME_FIELD(coarse_bin);SAME_FIELD(refined_epoch);
    SAME_FIELD(frame_support);SAME_FIELD(glrt_complete);
    SAME_FIELD(conditioned_fallback);SAME_FIELD(refinement_skipped);
    SAME_FIELD(coarse_cfo_hz);SAME_FIELD(fine_cfo_hz);
    SAME_FIELD(conditioned_cfo_hz);SAME_FIELD(epoch);
    SAME_FIELD(acquired_cfo_hz);SAME_FIELD(tracking_cfo_hz);
    SAME_FIELD(exact_score);SAME_FIELD(control_score);SAME_FIELD(margin);
    SAME_FIELD(acquire_score);SAME_FIELD(verify_score);
    SAME_FIELD(verify_control_score);SAME_FIELD(conditioned_score);
    SAME_FIELD(coarse_score);SAME_FIELD(fractional_epoch_status);
    SAME_FIELD(fractional_epoch_offset_samples);
    SAME_FIELD(fractional_epoch_log_curvature);
    SAME_FIELD(fractional_epoch_exact_grid);SAME_FIELD(fractional_epoch_control_grid);
    SAME_FIELD(fractional_exact_score);SAME_FIELD(fractional_control_score);
    SAME_FIELD(fractional_margin);SAME_FIELD(fractional_residual_cfo_hz);
    SAME_FIELD(fractional_tracking_cfo_hz);
#undef SAME_FIELD
    return 1;
}

static int same_row(const leo_native_glrt_row *dual,
    const leo_native_glrt_row *single,int receiver)
{
    if(dual->receiver_id!=receiver||single->receiver_id!=0||
       dual->probe_index!=single->probe_index||
       dual->probe_start_ms!=single->probe_start_ms)return 0;
#define SAME_COUNT(name) if(dual->name!=single->name)return 0
    SAME_COUNT(proposal_executed);SAME_COUNT(proposal_tracking_fallback);
    SAME_COUNT(proposal_neighbor_matches);SAME_COUNT(candidate_count);
    SAME_COUNT(retained_peak_count);SAME_COUNT(coarse_gate_skipped_count);
    SAME_COUNT(conditioned_fallback_count);SAME_COUNT(actual_executed_glrt_calls);
    SAME_COUNT(glrt_cache_hits);SAME_COUNT(conditioned_cache_hits);
    SAME_COUNT(fine_fft_cache_entries);SAME_COUNT(fine_fft_cache_hits);
    SAME_COUNT(fine_precision_calls);SAME_COUNT(fine_precision_guard_checks);
    SAME_COUNT(fine_precision_fallbacks);
    SAME_COUNT(fine_precision_nonfinite_fallbacks);
    SAME_COUNT(fine_precision_near_tie_fallbacks);
    SAME_COUNT(fine_precision_interpolation_fallbacks);
    SAME_COUNT(conditioned_bins_screened);SAME_COUNT(conditioned_bins_rechecked);
#undef SAME_COUNT
    for(int index=0;index<dual->candidate_count;++index)
        if(!same_candidate(&dual->candidates[index],&single->candidates[index]))return 0;
    return 1;
}

static int compare_receiver(const leo_native_glrt_result *dual,
    const leo_native_glrt_result *single,int receiver)
{
    if(dual->row_count!=2*single->row_count)return 0;
    int candidates=0;
    for(size_t row=0;row<single->row_count;++row){
        const leo_native_glrt_row *expected=&dual->rows[2*row+(size_t)receiver];
        if(!same_row(expected,&single->rows[row],receiver)){
            fprintf(stderr,"row mismatch: receiver=%d row=%zu\n",receiver,row);
            return 0;
        }
        candidates+=single->rows[row].candidate_count;
    }
    return candidates>0;
}

int main(int argc,char **argv)
{
    if(argc!=4)return 2;
    void *exact_data=NULL,*control_data=NULL,*dual_data=NULL;
    size_t exact_size=0,control_size=0,dual_size=0;
    if(read_exact(argv[1],&exact_data,&exact_size)||
       read_exact(argv[2],&control_data,&control_size)||
       read_exact(argv[3],&dual_data,&dual_size))return 3;
    const size_t template_count=exact_size/sizeof(leo_native_glrt_complex);
    size_t complex_times=0,dual_rows=0,single_times=0,single_rows=0;
    if(!template_count||control_size!=exact_size||
       leo_native_glrt_layout(2500000,120,10,&complex_times,&dual_rows)||
       leo_single_rx_glrt_layout(2500000,120,10,&single_times,&single_rows)||
       complex_times!=single_times||dual_rows!=2*single_rows||
       dual_size!=4*complex_times*sizeof(int16_t))return 4;
    if(leo_single_rx_glrt_layout(2500000,120,30,&single_times,&single_rows)!=
       LEO_NATIVE_GLRT_INVALID)return 4;

    leo_single_rx_glrt_capabilities capabilities={0};
    if(leo_single_rx_glrt_get_capabilities(&capabilities)||
       capabilities.abi_version!=LEO_SINGLE_RX_GLRT_ABI_VERSION||
       capabilities.receiver_count!=1||capabilities.input_scalar_stride!=2||
       capabilities.maximum_candidates_per_row!=8||
       !capabilities.native_per_receiver_semantics||
       capabilities.peer_recovery_available||
       capabilities.fractional_epoch_server_parity_qualified)return 4;

    int16_t *single[2]={calloc(2*complex_times,sizeof(int16_t)),
        calloc(2*complex_times,sizeof(int16_t))};
    if(!single[0]||!single[1])return 5;
    const int16_t *dual_samples=dual_data;
    for(size_t sample=0;sample<complex_times;++sample)
        for(int receiver=0;receiver<2;++receiver){
            single[receiver][2*sample]=dual_samples[4*sample+2*(size_t)receiver];
            single[receiver][2*sample+1]=dual_samples[4*sample+2*(size_t)receiver+1];
        }

    leo_native_glrt *dual=NULL;
    if(leo_native_glrt_create(&dual,2500000,exact_data,control_data,template_count))
        return 6;
    leo_native_glrt_result dual_result={0};
    if(leo_native_glrt_analyze(dual,dual_samples,complex_times,120,10,&dual_result))
        return 6;

    leo_single_rx_glrt *contexts[2]={NULL,NULL};
    for(int receiver=0;receiver<2;++receiver){
        if(leo_single_rx_glrt_create(&contexts[receiver],2500000,
            exact_data,control_data,template_count))return 7;
        leo_native_glrt_result result={0};
        if(leo_single_rx_glrt_analyze(contexts[receiver],single[receiver],
            complex_times,120,10,&result)||
           !compare_receiver(&dual_result,&result,receiver))return 8;
    }

    if(leo_native_glrt_analyze(dual,dual_samples,complex_times,120,120,
        &dual_result))return 8;
    for(int receiver=0;receiver<2;++receiver){
        leo_native_glrt_result result={0};
        leo_native_glrt_profile profile={0};
        if(leo_single_rx_glrt_analyze_profiled(contexts[receiver],single[receiver],
            complex_times,120,120,&result,&profile)||
           profile.prepared_complex_times!=50000||
           !compare_receiver(&dual_result,&result,receiver))return 8;
    }

    leo_native_glrt *fractional_dual=NULL;
    leo_single_rx_glrt *fractional_single[2]={NULL,NULL};
    if(leo_native_glrt_create_with_mode(&fractional_dual,2500000,exact_data,
        control_data,template_count,LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH)||
       leo_native_glrt_analyze(fractional_dual,dual_samples,complex_times,120,120,
        &dual_result))return 8;
    for(int receiver=0;receiver<2;++receiver){
        leo_native_glrt_result result={0};
        if(leo_single_rx_glrt_create_with_mode(&fractional_single[receiver],2500000,
            exact_data,control_data,template_count,
            LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH)||
           leo_single_rx_glrt_analyze(fractional_single[receiver],single[receiver],
            complex_times,120,120,&result)||
           !compare_receiver(&dual_result,&result,receiver))return 8;
        for(size_t row=0;row<result.row_count;++row)
            for(int candidate=0;candidate<result.rows[row].candidate_count;++candidate)
                if(result.rows[row].candidates[candidate].fractional_epoch_status==0)
                    return 8;
    }

    leo_native_glrt_result unchanged;
    memset(&unchanged,0xa5,sizeof(unchanged));
    leo_native_glrt_result before=unchanged;
    if(leo_single_rx_glrt_analyze(contexts[0],single[0],complex_times-1,
        120,10,&unchanged)!=LEO_NATIVE_GLRT_INVALID||
       memcmp(&unchanged,&before,sizeof(unchanged)))return 9;
    if(leo_native_glrt_analyze((leo_native_glrt *)contexts[0],dual_samples,
        complex_times,120,10,&unchanged)!=LEO_NATIVE_GLRT_INVALID||
       leo_single_rx_glrt_analyze((leo_single_rx_glrt *)dual,single[0],
        complex_times,120,10,&unchanged)!=LEO_NATIVE_GLRT_INVALID)return 9;

    int busy_observed=0;
    for(int attempt=0;attempt<5&&!busy_observed;++attempt){
        pthread_barrier_t barrier;
        pthread_t threads[2];
        call calls[2]={{contexts[0],single[0],complex_times,&barrier,99,{0}},
                       {contexts[0],single[0],complex_times,&barrier,99,{0}}};
        if(pthread_barrier_init(&barrier,NULL,3)||
           pthread_create(&threads[0],NULL,run_call,&calls[0])||
           pthread_create(&threads[1],NULL,run_call,&calls[1]))return 10;
        pthread_barrier_wait(&barrier);
        pthread_join(threads[0],NULL);pthread_join(threads[1],NULL);
        pthread_barrier_destroy(&barrier);
        busy_observed=(calls[0].status==LEO_NATIVE_GLRT_OK&&
                       calls[1].status==LEO_NATIVE_GLRT_BUSY)||
                      (calls[1].status==LEO_NATIVE_GLRT_OK&&
                       calls[0].status==LEO_NATIVE_GLRT_BUSY);
        if(!busy_observed&&
           (calls[0].status!=LEO_NATIVE_GLRT_OK||calls[1].status!=LEO_NATIVE_GLRT_OK))
            return 10;
    }
    if(!busy_observed)return 10;

    leo_native_glrt_complex *invalid_template=malloc(exact_size);
    if(!invalid_template)return 10;
    memcpy(invalid_template,exact_data,exact_size);
    invalid_template[0].real=NAN;
    leo_single_rx_glrt *invalid_context=(leo_single_rx_glrt *)(uintptr_t)1;
    if(leo_single_rx_glrt_create(&invalid_context,2500000,invalid_template,
        control_data,template_count)!=LEO_NATIVE_GLRT_INVALID||invalid_context)
        return 10;
    free(invalid_template);
    if(fesetround(FE_DOWNWARD)||
       leo_single_rx_glrt_create(&invalid_context,2500000,exact_data,
        control_data,template_count)!=LEO_NATIVE_GLRT_INVALID||invalid_context||
       fesetround(FE_TONEAREST))return 10;

    for(int receiver=0;receiver<2;++receiver)
        if(leo_single_rx_glrt_destroy(fractional_single[receiver]))return 11;
    if(leo_native_glrt_destroy(fractional_dual))return 11;
    for(int receiver=0;receiver<2;++receiver)
        if(leo_single_rx_glrt_destroy(contexts[receiver]))return 11;
    if(leo_native_glrt_destroy(dual))return 11;
    free(single[1]);free(single[0]);free(dual_data);free(control_data);free(exact_data);
    puts("single-rx GLRT component tests passed");
    return 0;
}
