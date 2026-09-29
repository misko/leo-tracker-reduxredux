#define _GNU_SOURCE
#include "native_glrt.h"

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

static int arguments(int argc,char **argv,options *o)
{
    *o=(options){.dwell_ms=120,.stride_ms=10};
    unsigned seen=0;
    for(int i=1;i<argc;++i){
        if(i+1==argc)return -1;
        const char *value=argv[++i];
        unsigned bit=0;
        if(!strcmp(argv[i-1],"--rate-hz")){bit=1u;if(number(value,&o->rate))return -1;}
        else if(!strcmp(argv[i-1],"--dwell-ms")){bit=2u;if(number(value,&o->dwell_ms))return -1;}
        else if(!strcmp(argv[i-1],"--probe-stride-ms")){bit=4u;if(number(value,&o->stride_ms))return -1;}
        else if(!strcmp(argv[i-1],"--exact-template")){bit=8u;o->exact_path=value;}
        else if(!strcmp(argv[i-1],"--control-template")){bit=16u;o->control_path=value;}
        else if(!strcmp(argv[i-1],"--input-ci16")){bit=32u;o->input_path=value;}
        else return -1;
        if(seen&bit)return -1;
        seen|=bit;
    }
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
    printf(",\"coarse_score\":%.17g}",c->coarse_score);
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
        "\"timings_ms\":{\"total_cpu\":%.17g,\"proposal\":%.17g,"
        "\"stage_sum\":%.17g,\"proposal_fold\":%.17g,"
        "\"proposal_correlation\":%.17g,\"proposal_ranking\":%.17g,"
        "\"coarse\":%.17g,\"acquisition\":%.17g,\"fine_fft\":%.17g,"
        "\"conditioned\":%.17g,\"verification\":%.17g,\"glrt\":%.17g},"
        "\"candidates\":[",
        r->receiver_id,r->probe_index,r->probe_start_ms,r->proposal_executed,
        r->proposal_tracking_fallback,r->proposal_neighbor_matches,r->candidate_count,
        r->retained_peak_count,r->coarse_gate_skipped_count,
        r->conditioned_fallback_count,r->actual_executed_glrt_calls,
        r->glrt_cache_hits,r->conditioned_cache_hits,r->fine_fft_cache_entries,
        r->fine_fft_cache_hits,r->fine_precision_calls,r->fine_precision_guard_checks,
        r->fine_precision_fallbacks,r->fine_precision_nonfinite_fallbacks,
        r->fine_precision_near_tie_fallbacks,r->fine_precision_interpolation_fallbacks,
        r->conditioned_bins_screened,r->conditioned_bins_rechecked,r->total_cpu_ms,
        r->proposal_ms,r->stage_sum_ms,r->proposal_fold_ms,
        r->proposal_correlation_ms,r->proposal_ranking_ms,r->coarse_ms,
        r->acquisition_ms,r->fine_fft_ms,r->conditioned_ms,r->verification_ms,r->glrt_ms);
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
        fprintf(stderr,"usage: %s --rate-hz RATE --exact-template FILE --control-template FILE --input-ci16 FILE [--dwell-ms 120|240|360] [--probe-stride-ms 10|20|120]\n",argv[0]);return 2;
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
    int status=leo_native_glrt_create(&context,o.rate,exact,control,template_count);
    double setup=cpu_ms()-setup_started;
    if(status){fprintf(stderr,"setup: %s\n",leo_native_glrt_status_string(status));free(input);free(control);free(exact);return 4;}
    leo_native_glrt_result result;
    status=leo_native_glrt_analyze(context,input,times,o.dwell_ms,o.stride_ms,&result);
    if(status){fprintf(stderr,"analysis: %s\n",leo_native_glrt_status_string(status));leo_native_glrt_destroy(context);free(input);free(control);free(exact);return 5;}
    printf("{\"schema\":\"leo-native-glrt/v1\","
        "\"algorithm_id\":\"wave8-gate314-source-v1\","
        "\"sample_rate_hz\":%u,\"dwell_ms\":%u,\"probe_ms\":20,"
        "\"probe_stride_ms\":%u,\"receiver_count\":2,"
        "\"input_complex_times\":%zu,\"template_complex_count\":%zu,"
        "\"thread_safety\":\"process-serialized\","
        "\"timings_ms\":{\"setup\":%.17g,\"detector_cpu\":%.17g,\"io\":%.17g},\"rows\":[",
        o.rate,o.dwell_ms,o.stride_ms,times,template_count,setup,result.detector_cpu_ms,io);
    for(size_t i=0;i<result.row_count;++i){if(i)putchar(',');row(&result.rows[i]);}
    fputs("]}\n",stdout);
    leo_native_glrt_destroy(context);free(input);free(control);free(exact);
    return ferror(stdout)?6:0;
}
