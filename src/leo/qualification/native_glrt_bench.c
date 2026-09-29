/* Persistent-context saved-IQ qualification adapter.
 *
 * The tab-separated manifest has no header. Each line is:
 * sequence, rate_hz, dwell_ms, stride_ms, exact_template, control_template,
 * input_ci16. Sequence starts at zero and fixes repeat order. One invocation
 * deliberately accepts one rate/template context; all input files are loaded
 * before setup and timed calls. JSONL stdout contains setup, one full result
 * per call, then destruction/process summary. --no-profile selects the public
 * compatibility call and suppresses profile output; it does not claim to
 * remove clocks internal to that wrapper. It is benchmark evidence, not a
 * scanner or capture entry point. */
#define _GNU_SOURCE
#include "native_glrt.h"
#ifdef LEO_NATIVE_GLRT_DIAGNOSTIC_WRAP
#include "native_glrt_profile_wrap.h"
#endif

#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>
#ifdef LEO_NATIVE_GLRT_BENCH_AFFINITY
#include <sched.h>
#endif

#define PATH_CAP 4096
#define MAX_ENTRIES 4096
#define MAX_UNIQUE_INPUTS 32
#define MAX_PRELOAD_BYTES (128u*1024u*1024u)

typedef struct {
    unsigned sequence,rate,dwell,stride;
    char exact[PATH_CAP],control[PATH_CAP],input[PATH_CAP];
    int16_t *samples;size_t times;int owns_samples;
} entry;

static double now(clockid_t clock)
{
    struct timespec value;if(clock_gettime(clock,&value))return NAN;
    return 1000.0*(double)value.tv_sec+1e-6*(double)value.tv_nsec;
}

static void *read_file(const char *path,size_t count,size_t size)
{
    if(!count||size>SIZE_MAX/count)return NULL;
    FILE *file=fopen(path,"rb");void *data=malloc(count*size);
    if(!file||!data||fread(data,size,count,file)!=count||fgetc(file)!=EOF){
        if(file)fclose(file);
        free(data);return NULL;
    }
    if(fclose(file)){free(data);return NULL;}return data;
}

static long thermal(const char *path,double scale,double offset,int *available)
{
    FILE *file=path?fopen(path,"r"):NULL;double raw=0;long value=0;
    *available=file&&fscanf(file,"%lf",&raw)==1&&isfinite(raw)&&
        raw+offset>=(double)LONG_MIN/scale&&raw+offset<=(double)LONG_MAX/scale;
    if(*available)value=lround((raw+offset)*scale);
    if(file)fclose(file);
    return value;
}

static long peak_rss(void)
{
    struct rusage usage;return getrusage(RUSAGE_SELF,&usage)?-1:usage.ru_maxrss;
}

static void number(FILE *out,double value)
{
    if(isfinite(value))fprintf(out,"%.17g",value);else fputs("null",out);
}

static void number_field(FILE *out,const char *name,double value)
{
    fprintf(out,",\"%s\":",name);number(out,value);
}

static void string(FILE *out,const char *value)
{
    fputc('"',out);
    for(const unsigned char *p=(const unsigned char *)value;*p;++p){
        if(*p=='"'||*p=='\\')fprintf(out,"\\%c",*p);
        else if(*p<0x20)fprintf(out,"\\u%04x",*p);
        else fputc(*p,out);
    }
    fputc('"',out);
}

static void optional_field(FILE *out,const char *name,double value,int available)
{
    fprintf(out,",\"%s\":",name);
    if(available)number(out,value);else fputs("null",out);
}

static void candidate(FILE *out,const leo_native_glrt_candidate *c)
{
    fprintf(out,"{\"coarse_epoch\":%d,\"coarse_bin\":%d,\"refined_epoch\":%d,"
        "\"frame_support\":%d,\"glrt_complete\":%s,\"conditioned_fallback\":%s,"
        "\"refinement_skipped\":%s",c->coarse_epoch,c->coarse_bin,c->refined_epoch,
        c->frame_support,c->glrt_complete?"true":"false",
        c->conditioned_fallback?"true":"false",c->refinement_skipped?"true":"false");
    number_field(out,"coarse_cfo_hz",c->coarse_cfo_hz);
    number_field(out,"fine_cfo_hz",c->fine_cfo_hz);
    optional_field(out,"conditioned_cfo_hz",c->conditioned_cfo_hz,c->conditioned_fallback);
    fprintf(out,",\"epoch\":%d",c->epoch);
    number_field(out,"acquired_cfo_hz",c->acquired_cfo_hz);
    number_field(out,"tracking_cfo_hz",c->tracking_cfo_hz);
    number_field(out,"exact_score",c->exact_score);
    number_field(out,"control_score",c->control_score);
    number_field(out,"margin",c->margin);
    optional_field(out,"acquire_score",c->acquire_score,!c->refinement_skipped);
    optional_field(out,"verify_score",c->verify_score,!c->refinement_skipped);
    optional_field(out,"verify_control_score",c->verify_control_score,!c->refinement_skipped);
    optional_field(out,"conditioned_score",c->conditioned_score,c->conditioned_fallback);
    number_field(out,"coarse_score",c->coarse_score);fputc('}',out);
}

static void row(FILE *out,const leo_native_glrt_row *r)
{
    fprintf(out,"{\"receiver_id\":%d,\"probe_index\":%d,\"probe_start_ms\":%d,"
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
        r->retained_peak_count,r->coarse_gate_skipped_count,r->conditioned_fallback_count,
        r->actual_executed_glrt_calls,r->glrt_cache_hits,r->conditioned_cache_hits,
        r->fine_fft_cache_entries,r->fine_fft_cache_hits,r->fine_precision_calls,
        r->fine_precision_guard_checks,r->fine_precision_fallbacks,
        r->fine_precision_nonfinite_fallbacks,r->fine_precision_near_tie_fallbacks,
        r->fine_precision_interpolation_fallbacks,r->conditioned_bins_screened,
        r->conditioned_bins_rechecked,r->total_cpu_ms,r->proposal_ms,r->stage_sum_ms,
        r->proposal_fold_ms,r->proposal_correlation_ms,r->proposal_ranking_ms,r->coarse_ms,
        r->acquisition_ms,r->fine_fft_ms,r->conditioned_ms,r->verification_ms,r->glrt_ms);
    for(int i=0;i<r->candidate_count;++i){if(i)fputc(',',out);candidate(out,&r->candidates[i]);}
    fputs("]}",out);
}

static int parse_manifest(const char *path,entry **values,size_t *count)
{
    FILE *file=fopen(path,"r");if(!file)return -1;
    entry *items=NULL;size_t used=0,capacity=0;char *line=NULL;size_t linecap=0;
    while(getline(&line,&linecap,file)>=0){
        if(line[0]=='#'||line[0]=='\n')continue;
        entry item={0};
        int fields=sscanf(line,"%u\t%u\t%u\t%u\t%4095[^\t]\t%4095[^\t]\t%4095[^\n]",
            &item.sequence,&item.rate,&item.dwell,&item.stride,item.exact,item.control,item.input);
        if(fields!=7||item.sequence!=used||used==MAX_ENTRIES)goto fail;
        size_t times=0,rows=0;
        if(leo_native_glrt_layout(item.rate,item.dwell,item.stride,&times,&rows))goto fail;
        item.times=times;
        if(used==capacity){
            size_t next=capacity?2*capacity:16;entry *grown=realloc(items,next*sizeof(*items));
            if(!grown)goto fail;
            items=grown;capacity=next;
        }
        items[used++]=item;
    }
    free(line);if(fclose(file)||!used){free(items);return -1;}
    *values=items;*count=used;return 0;
fail:
    free(line);free(items);fclose(file);return -1;
}

int main(int argc,char **argv)
{
#ifdef LEO_NATIVE_GLRT_BENCH_AFFINITY
    cpu_set_t allowed;CPU_ZERO(&allowed);CPU_SET(0,&allowed);
    if(sched_setaffinity(0,sizeof(allowed),&allowed)){
        fprintf(stderr,"cannot pin native GLRT benchmark to CPU0\n");return 9;
    }
#endif
    const char *manifest=NULL,*thermal_path="/sys/class/thermal/thermal_zone0/temp";
    int profile_enabled=1;double thermal_scale=1.0,thermal_offset=0.0;
    for(int i=1;i<argc;++i){
        if(!strcmp(argv[i],"--no-profile")){profile_enabled=0;continue;}
        if(i+1==argc){fprintf(stderr,"missing option value\n");return 2;}
        if(!strcmp(argv[i],"--manifest"))manifest=argv[++i];
        else if(!strcmp(argv[i],"--thermal-path"))thermal_path=argv[++i];
        else if(!strcmp(argv[i],"--thermal-scale")){
            char *end=NULL;thermal_scale=strtod(argv[++i],&end);
            if(!end||*end||!isfinite(thermal_scale)||thermal_scale<=0)return 2;
        }else if(!strcmp(argv[i],"--thermal-offset")){
            char *end=NULL;thermal_offset=strtod(argv[++i],&end);
            if(!end||*end||!isfinite(thermal_offset))return 2;
        }
        else {fprintf(stderr,"unknown option\n");return 2;}
    }
    if(!manifest){fprintf(stderr,
        "usage: %s --manifest TSV [--thermal-path PATH] [--thermal-scale N] "
        "[--thermal-offset N] [--no-profile]\n",argv[0]);return 2;}
    double process_cpu=now(CLOCK_PROCESS_CPUTIME_ID),process_wall=now(CLOCK_MONOTONIC);
    double io_cpu=now(CLOCK_PROCESS_CPUTIME_ID),io_wall=now(CLOCK_MONOTONIC);
    entry *items=NULL;size_t count=0;if(parse_manifest(manifest,&items,&count))return 3;
    unsigned rate=items[0].rate;const char *exact_path=items[0].exact,*control_path=items[0].control;
    for(size_t i=0;i<count;++i)if(items[i].rate!=rate||strcmp(items[i].exact,exact_path)||
       strcmp(items[i].control,control_path)){fprintf(stderr,"manifest mixes contexts\n");return 3;}
    size_t frame=(rate+375u)/750u;
    leo_native_glrt_complex *exact=read_file(exact_path,frame,sizeof(*exact));
    leo_native_glrt_complex *control=read_file(control_path,frame,sizeof(*control));
    size_t unique=0,preload_bytes=0;
    for(size_t i=0;i<count;++i){
        for(size_t prior=0;prior<i;++prior)if(!strcmp(items[i].input,items[prior].input)){
            if(items[i].times!=items[prior].times){fprintf(stderr,"reused input geometry differs\n");return 3;}
            items[i].samples=items[prior].samples;break;
        }
        if(items[i].samples)continue;
        size_t bytes=items[i].times*4*sizeof(int16_t);
        if(unique==MAX_UNIQUE_INPUTS||bytes>MAX_PRELOAD_BYTES-preload_bytes){
            fprintf(stderr,"manifest exceeds bounded unique-input preload\n");return 4;
        }
        items[i].samples=read_file(items[i].input,items[i].times*4,sizeof(int16_t));
        items[i].owns_samples=1;unique++;preload_bytes+=bytes;
    }
    if(!exact||!control){fprintf(stderr,"template read failure\n");return 4;}
    for(size_t i=0;i<count;++i)if(!items[i].samples){fprintf(stderr,"input read failure\n");return 4;}
    io_cpu=now(CLOCK_PROCESS_CPUTIME_ID)-io_cpu;io_wall=now(CLOCK_MONOTONIC)-io_wall;

    double setup_cpu=now(CLOCK_PROCESS_CPUTIME_ID),setup_wall=now(CLOCK_MONOTONIC);
    leo_native_glrt *context=NULL;int status=leo_native_glrt_create(&context,rate,exact,control,frame);
    setup_cpu=now(CLOCK_PROCESS_CPUTIME_ID)-setup_cpu;
    setup_wall=now(CLOCK_MONOTONIC)-setup_wall;
    if(status){fprintf(stderr,"setup: %s\n",leo_native_glrt_status_string(status));return 5;}
    printf("{\"kind\":\"setup\",\"entries\":%zu,\"unique_inputs\":%zu,"
        "\"preloaded_bytes\":%zu,\"profile_enabled\":%s,\"io_cpu_ms\":%.17g,"
        "\"io_wall_ms\":%.17g,\"setup_cpu_ms\":%.17g,\"setup_wall_ms\":%.17g,"
        "\"thermal_path\":",
        count,unique,preload_bytes,profile_enabled?"true":"false",
        io_cpu,io_wall,setup_cpu,setup_wall);
    string(stdout,thermal_path);
    printf(",\"thermal_scale\":%.17g,\"thermal_offset\":%.17g}\n",
        thermal_scale,thermal_offset);
    if(fflush(stdout))return 7;
    double *e2e_cpu=calloc(count,sizeof(*e2e_cpu)),*e2e_wall=calloc(count,sizeof(*e2e_wall));
    double *write_cpu=calloc(count,sizeof(*write_cpu)),*write_wall=calloc(count,sizeof(*write_wall));
    if(!e2e_cpu||!e2e_wall||!write_cpu||!write_wall)return 7;
    for(size_t i=0;i<count;++i){
        double e2e_cpu_started=now(CLOCK_PROCESS_CPUTIME_ID);
        double e2e_wall_started=now(CLOCK_MONOTONIC);
        int before_ok=0,after_ok=0;
        long before_temp=thermal(thermal_path,thermal_scale,thermal_offset,&before_ok);
        long rss_before=peak_rss();double call_cpu=now(CLOCK_PROCESS_CPUTIME_ID);
        double call_wall=now(CLOCK_MONOTONIC);leo_native_glrt_result result;
        leo_native_glrt_profile profile;
        memset(&profile,0,sizeof(profile));
#ifdef LEO_NATIVE_GLRT_DIAGNOSTIC_WRAP
        leo_native_glrt_wrap_profile_reset();
#endif
        status=profile_enabled?
            leo_native_glrt_analyze_profiled(context,items[i].samples,items[i].times,
                items[i].dwell,items[i].stride,&result,&profile):
            leo_native_glrt_analyze(context,items[i].samples,items[i].times,
                items[i].dwell,items[i].stride,&result);
#ifdef LEO_NATIVE_GLRT_DIAGNOSTIC_WRAP
        leo_native_glrt_wrap_profile wrapped=leo_native_glrt_wrap_profile_snapshot();
#endif
        call_cpu=now(CLOCK_PROCESS_CPUTIME_ID)-call_cpu;
        call_wall=now(CLOCK_MONOTONIC)-call_wall;
        long rss_after=peak_rss();
        long after_temp=thermal(thermal_path,thermal_scale,thermal_offset,&after_ok);
        if(status){fprintf(stderr,"entry %zu: %s\n",i,leo_native_glrt_status_string(status));return 6;}
        char *body=NULL;size_t body_size=0;double serial_cpu=now(CLOCK_PROCESS_CPUTIME_ID);
        double serial_wall=now(CLOCK_MONOTONIC);FILE *memory=open_memstream(&body,&body_size);
        if(!memory)return 7;
        fprintf(memory,"{\"kind\":\"call\",\"sequence\":%u,\"rate_hz\":%u,"
            "\"dwell_ms\":%u,\"stride_ms\":%u,\"call_cpu_ms\":%.17g,"
            "\"call_wall_ms\":%.17g,\"detector_cpu_ms\":%.17g,"
            "\"peak_rss_kib_before\":%ld,"
            "\"peak_rss_kib_after\":%ld,\"thermal_available_before\":%s,"
            "\"thermal_millidegrees_before\":%ld,\"thermal_available_after\":%s,"
            "\"thermal_millidegrees_after\":%ld,\"profile_enabled\":%s,\"profile\":{"
            "\"allocation_cpu_ms\":%.17g,\"allocation_wall_ms\":%.17g,"
            "\"preparation_cpu_ms\":%.17g,\"preparation_wall_ms\":%.17g,"
            "\"proposals_cpu_ms\":%.17g,\"proposals_wall_ms\":%.17g,"
            "\"search_cpu_ms\":%.17g,\"search_wall_ms\":%.17g,"
            "\"cleanup_cpu_ms\":%.17g,\"cleanup_wall_ms\":%.17g,"
            "\"prepared_complex_times\":%zu}",items[i].sequence,rate,
            items[i].dwell,items[i].stride,call_cpu,call_wall,result.detector_cpu_ms,
            rss_before,rss_after,
            before_ok?"true":"false",before_temp,after_ok?"true":"false",after_temp,
            profile_enabled?"true":"false",
            profile.allocation_cpu_ms,profile.allocation_wall_ms,
            profile.preparation_cpu_ms,profile.preparation_wall_ms,
            profile.proposals_cpu_ms,profile.proposals_wall_ms,profile.search_cpu_ms,
            profile.search_wall_ms,profile.cleanup_cpu_ms,profile.cleanup_wall_ms,
            profile.prepared_complex_times);
#ifdef LEO_NATIVE_GLRT_DIAGNOSTIC_WRAP
        fprintf(memory,",\"diagnostic_inclusive_with_wrapper_overhead\":{"
            "\"malloc_calls\":%" PRIu64 ",\"calloc_calls\":%" PRIu64 ","
            "\"realloc_calls\":%" PRIu64 ",\"free_calls\":%" PRIu64 ","
            "\"allocation_requested_bytes\":%" PRIu64 ","
            "\"allocation_cpu_ms\":%.17g,\"allocation_wall_ms\":%.17g,"
            "\"fft_plan_calls\":%" PRIu64 ",\"fftf_plan_calls\":%" PRIu64 ","
            "\"fft_plan_cpu_ms\":%.17g,\"fft_plan_wall_ms\":%.17g,"
            "\"fftf_plan_cpu_ms\":%.17g,\"fftf_plan_wall_ms\":%.17g,"
            "\"fft_execute_calls\":%" PRIu64 ",\"fftf_execute_calls\":%" PRIu64 ","
            "\"fft_execute_cpu_ms\":%.17g,\"fft_execute_wall_ms\":%.17g,"
            "\"fftf_execute_cpu_ms\":%.17g,\"fftf_execute_wall_ms\":%.17g}",
            wrapped.malloc_calls,wrapped.calloc_calls,wrapped.realloc_calls,
            wrapped.free_calls,wrapped.allocation_requested_bytes,
            wrapped.allocation_cpu_ms,wrapped.allocation_wall_ms,wrapped.fft_plan_calls,
            wrapped.fftf_plan_calls,wrapped.fft_plan_cpu_ms,wrapped.fft_plan_wall_ms,
            wrapped.fftf_plan_cpu_ms,wrapped.fftf_plan_wall_ms,wrapped.fft_execute_calls,
            wrapped.fftf_execute_calls,wrapped.fft_execute_cpu_ms,wrapped.fft_execute_wall_ms,
            wrapped.fftf_execute_cpu_ms,wrapped.fftf_execute_wall_ms);
#else
        fputs(",\"diagnostic_inclusive_with_wrapper_overhead\":null",memory);
#endif
        fputs(",\"rows\":[",memory);
        for(size_t j=0;j<result.row_count;++j){if(j)fputc(',',memory);row(memory,&result.rows[j]);}
        if(fputs("]}",memory)==EOF||fclose(memory)){free(body);return 7;}
        serial_cpu=now(CLOCK_PROCESS_CPUTIME_ID)-serial_cpu;
        serial_wall=now(CLOCK_MONOTONIC)-serial_wall;
        double write_cpu_started=now(CLOCK_PROCESS_CPUTIME_ID);
        double write_wall_started=now(CLOCK_MONOTONIC);
        printf("{\"serialization_cpu_ms\":%.17g,\"serialization_wall_ms\":%.17g,"
            "\"result\":%s}\n",serial_cpu,serial_wall,body);free(body);
        if(fflush(stdout))return 7;
        write_cpu[i]=now(CLOCK_PROCESS_CPUTIME_ID)-write_cpu_started;
        write_wall[i]=now(CLOCK_MONOTONIC)-write_wall_started;
        e2e_cpu[i]=now(CLOCK_PROCESS_CPUTIME_ID)-e2e_cpu_started;
        e2e_wall[i]=now(CLOCK_MONOTONIC)-e2e_wall_started;
    }
    double destroy_cpu=now(CLOCK_PROCESS_CPUTIME_ID),destroy_wall=now(CLOCK_MONOTONIC);
    status=leo_native_glrt_destroy(context);
    destroy_cpu=now(CLOCK_PROCESS_CPUTIME_ID)-destroy_cpu;
    destroy_wall=now(CLOCK_MONOTONIC)-destroy_wall;
    for(size_t i=0;i<count;++i)if(items[i].owns_samples)free(items[i].samples);
    free(items);free(control);free(exact);
    double write_cpu_sum=0,write_wall_sum=0,write_cpu_max=0,write_wall_max=0;
    for(size_t i=0;i<count;++i){write_cpu_sum+=write_cpu[i];write_wall_sum+=write_wall[i];
        if(write_cpu[i]>write_cpu_max)write_cpu_max=write_cpu[i];
        if(write_wall[i]>write_wall_max)write_wall_max=write_wall[i];}
    printf("{\"kind\":\"summary\",\"destroy_status\":%d,\"destroy_cpu_ms\":%.17g,"
        "\"destroy_wall_ms\":%.17g,\"main_phase_through_cleanup_cpu_ms\":%.17g,"
        "\"main_phase_through_cleanup_wall_ms\":%.17g,\"peak_rss_kib\":%ld,"
        "\"write_cpu_ms_sum\":%.17g,\"write_wall_ms_sum\":%.17g,"
        "\"write_cpu_ms_max\":%.17g,\"write_wall_ms_max\":%.17g,"
        "\"e2e_cpu_ms\":[",status,destroy_cpu,destroy_wall,
        now(CLOCK_PROCESS_CPUTIME_ID)-process_cpu,now(CLOCK_MONOTONIC)-process_wall,
        peak_rss(),write_cpu_sum,write_wall_sum,write_cpu_max,write_wall_max);
    for(size_t i=0;i<count;++i){if(i)fputc(',',stdout);printf("%.17g",e2e_cpu[i]);}
    fputs("],\"e2e_wall_ms\":[",stdout);
    for(size_t i=0;i<count;++i){if(i)fputc(',',stdout);printf("%.17g",e2e_wall[i]);}
    fputs("]}\n",stdout);fflush(stdout);
    free(write_wall);free(write_cpu);free(e2e_wall);free(e2e_cpu);
    return status?8:0;
}
