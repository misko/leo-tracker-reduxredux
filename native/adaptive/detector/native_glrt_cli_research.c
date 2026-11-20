#define _GNU_SOURCE
#if LEO_NATIVE_GLRT_ENABLE_SERVER_REFERENCE
#include "native_glrt_research.h"
#else
#include "native_glrt.h"
#endif

#include <errno.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef LEO_NATIVE_GLRT_CLI_AFFINITY
#include <sched.h>
#endif

typedef struct {
    uint32_t rate,dwell_ms,stride_ms;
    const char *exact_path,*control_path,*input_path;
    uint32_t mode;
    double center_hz[2],residual_min_hz,residual_max_hz;
    unsigned geometry_fields;
} options;

static double cpu_ms(void)
{
    struct timespec value;
    if(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&value))return 0;
    return 1000.0*(double)value.tv_sec+1e-6*(double)value.tv_nsec;
}

static int number(const char *text,uint32_t *value)
{
    char *end=NULL;errno=0;unsigned long parsed=strtoul(text,&end,10);
    if(errno||!text[0]||text[0]=='-'||*end||parsed>UINT32_MAX)return -1;
    *value=(uint32_t)parsed;return 0;
}

static int real_number(const char *text,double *value)
{
    char *end=NULL;errno=0;double parsed=strtod(text,&end);
    if(errno||!text[0]||*end||!isfinite(parsed))return -1;
    *value=parsed;return 0;
}

static int arguments(int argc,char **argv,options *o)
{
    *o=(options){.dwell_ms=120,.stride_ms=10};
    unsigned seen=0;
    for(int i=1;i<argc;++i){
        if(!strcmp(argv[i],"--fractional-epoch")){
            if(seen&64u)return -1;
            seen|=64u;o->mode=LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH;
            continue;
        }
        if(!strcmp(argv[i],"--server-coverage-fractional")){
            if(seen&64u)return -1;
            seen|=64u;o->mode=LEO_NATIVE_GLRT_MODE_SERVER_COVERAGE_FRACTIONAL;
            continue;
        }
        if(!strcmp(argv[i],"--server-reference-fractional")){
            if(seen&64u)return -1;
            seen|=64u;o->mode=LEO_NATIVE_GLRT_MODE_SERVER_REFERENCE_FRACTIONAL;
            continue;
        }
        if(!strcmp(argv[i],"--deployed-server-wrapper-fractional")){
            if(seen&64u)return -1;
            seen|=64u;o->mode=LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_WRAPPER_FRACTIONAL;
            continue;
        }
        if(!strcmp(argv[i],"--deployed-server-interval-fractional")){
            if(seen&64u)return -1;
            seen|=64u;o->mode=LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_INTERVAL_FRACTIONAL;
            continue;
        }
        if(i+1==argc)return -1;
        const char *value=argv[++i];
        unsigned bit=0;
        if(!strcmp(argv[i-1],"--rate-hz")){bit=1u;if(number(value,&o->rate))return -1;}
        else if(!strcmp(argv[i-1],"--dwell-ms")){bit=2u;if(number(value,&o->dwell_ms))return -1;}
        else if(!strcmp(argv[i-1],"--probe-stride-ms")){bit=4u;if(number(value,&o->stride_ms))return -1;}
        else if(!strcmp(argv[i-1],"--exact-template")){bit=8u;o->exact_path=value;}
        else if(!strcmp(argv[i-1],"--control-template")){bit=16u;o->control_path=value;}
        else if(!strcmp(argv[i-1],"--input-ci16")){bit=32u;o->input_path=value;}
        else if(!strcmp(argv[i-1],"--receiver-0-center-hz")){
            if(real_number(value,&o->center_hz[0]))return -1;
            o->geometry_fields|=1u;
        }
        else if(!strcmp(argv[i-1],"--receiver-1-center-hz")){
            if(real_number(value,&o->center_hz[1]))return -1;
            o->geometry_fields|=2u;
        }
        else if(!strcmp(argv[i-1],"--residual-cfo-min-hz")){
            if(real_number(value,&o->residual_min_hz))return -1;
            o->geometry_fields|=4u;
        }
        else if(!strcmp(argv[i-1],"--residual-cfo-max-hz")){
            if(real_number(value,&o->residual_max_hz))return -1;
            o->geometry_fields|=8u;
        }
        else return -1;
        if(seen&bit)return -1;
        seen|=bit;
    }
    if((o->mode==LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_WRAPPER_FRACTIONAL||
        o->mode==LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_INTERVAL_FRACTIONAL)&&
       o->geometry_fields!=15u)return -1;
    return !o->rate||!o->exact_path||!o->control_path||!o->input_path ? -1:0;
}

static void *read_exact(const char *path,size_t count,size_t size)
{
    if(count&&size>SIZE_MAX/count)return NULL;
    FILE *file=fopen(path,"rb");void *data=malloc(count*size);
    if(!file||!data||fread(data,size,count,file)!=count||fgetc(file)!=EOF){
        if(file)fclose(file);
        free(data);return NULL;
    }
    if(fclose(file)){free(data);return NULL;}return data;
}

static void nullable(double value,int available)
{
    if(available)printf("%.17g",value);else fputs("null",stdout);
}

static void candidate(const leo_native_glrt_candidate *c)
{
    printf("{\"coarse_epoch\":%d,\"coarse_bin\":%d,\"refined_epoch\":%d,"
        "\"frame_support\":%d,\"glrt_complete\":%d,\"refinement_skipped\":%s,"
        "\"conditioned_fallback\":%s,\"coarse_cfo_hz\":%.17g,\"fine_cfo_hz\":",
        c->coarse_epoch,c->coarse_bin,c->refined_epoch,c->frame_support,
        c->glrt_complete,c->refinement_skipped?"true":"false",
        c->conditioned_fallback?"true":"false",c->coarse_cfo_hz);
    nullable(c->fine_cfo_hz,1);
    fputs(",\"conditioned_cfo_hz\":",stdout);
    nullable(c->conditioned_cfo_hz,c->conditioned_fallback);
    printf(",\"epoch\":%d,\"acquired_cfo_hz\":%.17g,\"tracking_cfo_hz\":%.17g,"
        "\"exact_score\":%.17g,\"control_score\":%.17g,\"margin\":%.17g,"
        "\"acquire_score\":",c->epoch,c->acquired_cfo_hz,c->tracking_cfo_hz,
        c->exact_score,c->control_score,c->margin);
    nullable(c->acquire_score,!c->refinement_skipped);
    fputs(",\"verify_score\":",stdout);nullable(c->verify_score,!c->refinement_skipped);
    fputs(",\"verify_control_score\":",stdout);nullable(c->verify_control_score,!c->refinement_skipped);
    fputs(",\"conditioned_score\":",stdout);nullable(c->conditioned_score,c->conditioned_fallback);
    printf(",\"coarse_score\":%.17g,\"fractional_epoch\":{\"status\":\"%s\","
        "\"exact_score_grid\":",c->coarse_score,
        c->fractional_epoch_status==1?"complete":
        (c->fractional_epoch_status==2?"unbracketed":"not_evaluated"));
    if(c->fractional_epoch_status){
        putchar('[');for(int i=0;i<5;++i)printf("%s%.17g",i?",":"",
            c->fractional_epoch_exact_grid[i]);putchar(']');
    }else fputs("null",stdout);
    fputs(",\"control_score_grid\":",stdout);
    if(c->fractional_epoch_status){
        putchar('[');for(int i=0;i<5;++i)printf("%s%.17g",i?",":"",
            c->fractional_epoch_control_grid[i]);putchar(']');
    }else fputs("null",stdout);
    fputs(",\"offset_samples\":",stdout);
    nullable(c->fractional_epoch_offset_samples,c->fractional_epoch_status==1);
    fputs(",\"log_curvature\":",stdout);
    nullable(c->fractional_epoch_log_curvature,c->fractional_epoch_status==1);
    fputs(",\"exact_score\":",stdout);
    nullable(c->fractional_exact_score,c->fractional_epoch_status==1);
    fputs(",\"control_score\":",stdout);
    nullable(c->fractional_control_score,c->fractional_epoch_status==1);
    fputs(",\"margin\":",stdout);
    nullable(c->fractional_margin,c->fractional_epoch_status==1);
    fputs(",\"residual_cfo_hz\":",stdout);
    nullable(c->fractional_residual_cfo_hz,c->fractional_epoch_status==1);
    fputs(",\"tracking_cfo_hz\":",stdout);
    nullable(c->fractional_tracking_cfo_hz,c->fractional_epoch_status==1);
    fputs("}}",stdout);
}

static void row(const leo_native_glrt_row *r)
{
    printf("{\"receiver_id\":%d,\"probe_index\":%d,\"probe_start_ms\":%d,"
        "\"proposal_executed\":%d,\"proposal_tracking_fallback\":%d,"
        "\"proposal_neighbor_matches\":%d,\"candidate_count\":%d,"
        "\"retained_peak_count\":%d,\"coarse_gate_skipped_count\":%d,"
        "\"conditioned_fallback_count\":%d,\"actual_executed_glrt_calls\":%d,"
        "\"glrt_cache_hits\":%d,\"conditioned_cache_hits\":%d,"
        "\"fine_fft_cache_entries\":%d,\"fine_fft_cache_hits\":%d,"
        "\"fine_precision_calls\":%d,\"fine_precision_guard_checks\":%d,"
        "\"fine_precision_fallbacks\":%d,\"fine_precision_nonfinite_fallbacks\":%d,"
        "\"fine_precision_near_tie_fallbacks\":%d,"
        "\"fine_precision_interpolation_fallbacks\":%d,"
        "\"conditioned_bins_screened\":%d,\"conditioned_bins_rechecked\":%d,"
        "\"interval_screened_cells\":%d,\"interval_possible_peaks\":%d,"
        "\"interval_repaired_cells\":%d,\"interval_scalar_fallbacks\":%d,"
        "\"timings_ms\":{\"total_cpu\":%.17g,\"proposal\":%.17g,"
        "\"stage_sum\":%.17g,\"proposal_fold\":%.17g,"
        "\"proposal_correlation\":%.17g,\"proposal_ranking\":%.17g,"
        "\"coarse\":%.17g,\"acquisition\":%.17g,\"fine_fft\":%.17g,"
        "\"conditioned\":%.17g,\"verification\":%.17g,\"glrt\":%.17g,"
        "\"fractional_epoch\":%.17g},"
        "\"candidates\":[",
        r->receiver_id,r->probe_index,r->probe_start_ms,r->proposal_executed,
        r->proposal_tracking_fallback,r->proposal_neighbor_matches,r->candidate_count,
        r->retained_peak_count,r->coarse_gate_skipped_count,
        r->conditioned_fallback_count,r->actual_executed_glrt_calls,
        r->glrt_cache_hits,r->conditioned_cache_hits,r->fine_fft_cache_entries,
        r->fine_fft_cache_hits,r->fine_precision_calls,r->fine_precision_guard_checks,
        r->fine_precision_fallbacks,r->fine_precision_nonfinite_fallbacks,
        r->fine_precision_near_tie_fallbacks,r->fine_precision_interpolation_fallbacks,
        r->conditioned_bins_screened,r->conditioned_bins_rechecked,
        r->interval_screened_cells,r->interval_possible_peaks,
        r->interval_repaired_cells,r->interval_scalar_fallbacks,r->total_cpu_ms,
        r->proposal_ms,r->stage_sum_ms,r->proposal_fold_ms,
        r->proposal_correlation_ms,r->proposal_ranking_ms,r->coarse_ms,
        r->acquisition_ms,r->fine_fft_ms,r->conditioned_ms,r->verification_ms,r->glrt_ms,
        r->fractional_epoch_ms);
    for(int i=0;i<r->candidate_count;++i){if(i)putchar(',');candidate(&r->candidates[i]);}
    fputs("]}",stdout);
}

int main(int argc,char **argv)
{
#ifdef LEO_NATIVE_GLRT_CLI_AFFINITY
    cpu_set_t allowed;CPU_ZERO(&allowed);CPU_SET(0,&allowed);
    if(sched_setaffinity(0,sizeof(allowed),&allowed)){
        fprintf(stderr,"cannot pin native GLRT CLI to CPU0\n");return 7;
    }
#endif
    options o;if(arguments(argc,argv,&o)){
        fprintf(stderr,"usage: %s --rate-hz RATE --exact-template FILE --control-template FILE --input-ci16 FILE [--dwell-ms 120|240|360] [--probe-stride-ms 10|20|120] [--fractional-epoch|--server-coverage-fractional|--server-reference-fractional|--deployed-server-wrapper-fractional|--deployed-server-interval-fractional --receiver-0-center-hz HZ --receiver-1-center-hz HZ --residual-cfo-min-hz HZ --residual-cfo-max-hz HZ]\n",argv[0]);return 2;
    }
    const uint16_t endian=1;
    if(*(const uint8_t *)&endian!=1||sizeof(int16_t)!=2||sizeof(double)!=8||
       DBL_MANT_DIG!=53||sizeof(leo_native_glrt_complex)!=16){
        fprintf(stderr,"unsupported binary input representation\n");return 8;
    }
    if((o.rate!=2500000u&&o.rate!=5000000u&&o.rate!=7500000u&&o.rate!=10000000u)||
       (o.dwell_ms!=120&&o.dwell_ms!=240&&o.dwell_ms!=360)||
       (o.stride_ms!=10&&o.stride_ms!=20&&o.stride_ms!=120))return 2;
    size_t template_count=(o.rate+375u)/750u;
    size_t times=(size_t)o.rate*o.dwell_ms/1000u;
    double io_started=cpu_ms();
    leo_native_glrt_complex *exact=read_exact(o.exact_path,template_count,sizeof(*exact));
    leo_native_glrt_complex *control=read_exact(o.control_path,template_count,sizeof(*control));
    int16_t *input=read_exact(o.input_path,times*4,sizeof(*input));
    double io=cpu_ms()-io_started;
    if(!exact||!control||!input){fprintf(stderr,"input file size/read failure\n");free(input);free(control);free(exact);return 3;}
    double setup_started=cpu_ms();leo_native_glrt *context=NULL;
    int status=leo_native_glrt_create_with_mode(&context,o.rate,exact,control,
        template_count,o.mode);
    double setup=cpu_ms()-setup_started;
    if(status){fprintf(stderr,"setup: %s\n",leo_native_glrt_status_string(status));free(input);free(control);free(exact);return 4;}
    if(o.mode==LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_WRAPPER_FRACTIONAL||
       o.mode==LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_INTERVAL_FRACTIONAL){
        status=leo_native_glrt_set_server_reference_geometry(context,o.center_hz,
            o.residual_min_hz,o.residual_max_hz);
        if(status){fprintf(stderr,"geometry: %s\n",leo_native_glrt_status_string(status));
            leo_native_glrt_destroy(context);free(input);free(control);free(exact);return 4;}
    }
    leo_native_glrt_result result;
    status=leo_native_glrt_analyze(context,input,times,o.dwell_ms,o.stride_ms,&result);
    if(status){fprintf(stderr,"analysis: %s\n",leo_native_glrt_status_string(status));leo_native_glrt_destroy(context);free(input);free(control);free(exact);return 5;}
    printf("{\"schema\":\"leo-native-glrt/v2\","
        "\"algorithm_id\":\"wave8-gate314-source-v1\","
        "\"sample_rate_hz\":%u,\"dwell_ms\":%u,\"probe_ms\":20,"
        "\"probe_stride_ms\":%u,\"receiver_count\":2,"
        "\"input_complex_times\":%zu,\"template_complex_count\":%zu,"
        "\"thread_safety\":\"process-serialized\","
        "\"refinement_mode\":\"%s\","
        "\"timings_ms\":{\"setup\":%.17g,\"detector_cpu\":%.17g,\"io\":%.17g},\"rows\":[",
        o.rate,o.dwell_ms,o.stride_ms,times,template_count,
        o.mode==LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_INTERVAL_FRACTIONAL?
            "deployed-server-interval-fractional":
        (o.mode==LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_WRAPPER_FRACTIONAL?
            "deployed-server-wrapper-fractional":
        (o.mode==LEO_NATIVE_GLRT_MODE_SERVER_REFERENCE_FRACTIONAL?
            "server-reference-fractional":
        (o.mode==LEO_NATIVE_GLRT_MODE_SERVER_COVERAGE_FRACTIONAL?
            "server-coverage-fractional":
        (o.mode==LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH?
                "ordinary-with-fractional-epoch":"ordinary")))),
        setup,result.detector_cpu_ms,io);
    for(size_t i=0;i<result.row_count;++i){if(i)putchar(',');row(&result.rows[i]);}
    fputs("]}\n",stdout);
    leo_native_glrt_destroy(context);free(input);free(control);free(exact);
    return ferror(stdout)?6:0;
}
