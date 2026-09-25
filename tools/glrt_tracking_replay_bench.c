#define _POSIX_C_SOURCE 200809L
#include "glrt_tracking_bootstrap.h"
#include "glrt_tracking_resolver.h"
#include "glrt_tracking_iq.h"
#include <fftw3.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "fixture requires little endian"
#endif
struct resolver_record {
    uint32_t samples;
    size_t starts[4];
    int16_t iq[28000];
    struct glrt_resolver_peak expected[17];
};
struct anchor {
    uint32_t frame;
    struct glrt_tracking_job job;
    uint32_t expected[16];
    int16_t iq[6600];
};
static void read_exact(FILE *f,void *value,size_t size)
{ if(fread(value,size,1,f)!=1) exit(2); }
static uint32_t word(FILE *f)
{ uint32_t value;read_exact(f,&value,4);return value; }
static uint64_t wide(FILE *f)
{ uint64_t value;read_exact(f,&value,8);return value; }
static double real(FILE *f)
{ double value;read_exact(f,&value,8);if(!isfinite(value)) exit(2);return value; }
static double now(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t)) exit(2);
    return (double)t.tv_sec+1e-9*t.tv_nsec;
}
static int transform(void *context,double (*bins)[2],size_t count)
{
    if(count!=GLRT_RESOLVER_FFT) return -1;
    fftw_execute_dft((fftw_plan)context,bins,bins);return 0;
}
int main(int argc,char **argv)
{
    FILE *f,*a;
    struct resolver_record *records;
    struct glrt_resolver_workspace *workspace;
    int16_t reference[6600],references[4][13200],cut[6600];
    fftw_plan plan;
    uint32_t count,i,j,ready_count=0,control_ready=0;
    double before,plan_us;
    /* The radio's minimal BusyBox has no timeout applet. Bound file reads,
     * FFT execution and catch-up inside the process, including after SSH loss. */
    alarm(45);
    if(argc!=3 || !(f=fopen(argv[1],"rb")) || word(f)!=UINT32_C(0x31525347)) return 2;
    count=word(f);
    if(count!=14 || !(records=calloc(count,sizeof(*records)))) return 2;
    read_exact(f,reference,sizeof(reference));
    for(i=0;i<count;i++) {
        records[i].samples=word(f);
        if(records[i].samples>14000 || records[i].samples<3316) return 2;
        for(j=0;j<4;j++) records[i].starts[j]=word(f);
        for(j=0;j<17;j++) {
            records[i].expected[j].shift=(int32_t)word(f);
            records[i].expected[j].cfo_hz=real(f);
            records[i].expected[j].power_coherence=real(f);
        }
        read_exact(f,records[i].iq,records[i].samples*4);
    }
    if(fgetc(f)!=EOF || ferror(f)) return 2;
    fclose(f);
    if(!(a=fopen(argv[2],"rb")) || word(a)!=UINT32_C(0x31425347) || word(a)!=14) return 2;
    read_exact(a,references,sizeof(references));
    workspace=fftw_malloc(sizeof(*workspace));
    if(!workspace) return 2;
    before=now();
    plan=fftw_plan_dft_1d(GLRT_RESOLVER_FFT,workspace->bins,workspace->bins,FFTW_FORWARD,FFTW_ESTIMATE);
    plan_us=(now()-before)*1e6;
    if(!plan) return 2;
    printf("{\"scope\":\"full_resolver_catchup_saved_iq_no_iio\",\"plan_us\":%.12g,\"cases\":[",plan_us);
    for(i=0;i<count;i++) {
        struct resolver_record *r=&records[i];
        struct glrt_resolver_result result;
        struct glrt_tracking_bootstrap state;
        struct glrt_tracking_batch handoff;
        struct glrt_tracking_job job;
        struct anchor *anchors;
        uint64_t origin,available_base,available,earliest;
        uint32_t fraction,supported,anchor_count,frame=0,checked=0;
        double start,resolver_us,elapsed;
        int status;
        if(word(a)!=i) return 2;
        origin=wide(a);fraction=word(a);available_base=wide(a);earliest=wide(a);
        supported=word(a);anchor_count=word(a);
        if(!anchor_count || anchor_count>200 || !(anchors=calloc(anchor_count,sizeof(*anchors)))) return 2;
        for(j=0;j<anchor_count;j++) {
            anchors[j].frame=word(a);anchors[j].job.start=wide(a);
            anchors[j].job.phase_step=word(a);anchors[j].job.reference_phase=word(a);
            if(anchors[j].job.reference_phase>3) return 2;
            read_exact(a,anchors[j].expected,sizeof(anchors[j].expected));
            read_exact(a,anchors[j].iq,sizeof(anchors[j].iq));
        }
        start=now();
        if(glrt_tracking_resolve_2500000(workspace,reference,3300,r->iq,r->samples,
                                       r->starts,4,transform,plan,&result)) return 1;
        resolver_us=(now()-start)*1e6;
        for(j=0;j<17;j++) {
            struct glrt_resolver_peak x=result.hypotheses[j],e=r->expected[j];
            if(x.shift!=e.shift || fabs(x.cfo_hz-e.cfo_hz)>1e-5 ||
               fabs(x.power_coherence-e.power_coherence)>1e-10) return 1;
        }
        if(result.best.shift<0) {
            if(origin<(uint64_t)-result.best.shift) return 2;
            origin-=(uint64_t)-result.best.shift;
        } else origin+=(uint32_t)result.best.shift;
        if(glrt_tracking_bootstrap_init(&state,3,origin,fraction,result.best.cfo_hz)) return 1;
        for(;;) {
            struct anchor *expected;
            struct glrt_tracking_moments moments;
            struct glrt_native_estimate estimate;
            double samples=(now()-start)*2500000;
            if(samples<0 || samples>10000000) return 1;
            available=available_base+(uint64_t)samples;
            status=glrt_tracking_bootstrap_next(&state,earliest,available,2500,&frame,&job,&handoff);
            if(status!=GLRT_BOOTSTRAP_PAST) break;
            if(checked>=anchor_count) return 1;
            expected=&anchors[checked];
            if(frame!=expected->frame || job.start!=expected->job.start ||
               job.phase_step!=expected->job.phase_step || job.reference_phase!=expected->job.reference_phase ||
               job.start+3300>available) return 1;
            memcpy(cut,expected->iq,sizeof(cut));
            if(glrt_tracking_iq_moments_2500000(cut,references[job.reference_phase],3300,
                job.start,0,job.phase_step,&moments) || memcmp(moments.words,expected->expected,sizeof(moments.words)) ||
                glrt_tracking_solve(2500000,job.reference_phase,&moments,&estimate) ||
                glrt_tracking_bootstrap_observe(&state,3,frame,&job,&estimate)<0) return 1;
            checked++;
        }
        elapsed=(now()-start)*1e6;
        if(status==GLRT_BOOTSTRAP_READY) { ready_count++; if(!supported) control_ready++; }
        else if(state.failure!=GLRT_BOOTSTRAP_HISTORY && state.failure!=GLRT_BOOTSTRAP_BUDGET) return 1;
        printf("%s{\"case\":%u,\"acquisition_supported\":%u,\"status\":%d,\"failure\":%u,"
            "\"resolver_us\":%.12g,\"total_us\":%.12g,\"past_jobs\":%u,\"available_through\":%"PRIu64
            ",\"first_future_frame\":%u,\"handoff\":{\"start\":%"PRIu64",\"fraction\":%u,"
            "\"period\":%"PRIu64",\"step\":%"PRIu64",\"delta\":%"PRIu64",\"expires\":%"PRIu64"}}",
            i?",":"",i,supported,status,state.failure,resolver_us,elapsed,checked,available,frame,
            handoff.prediction.start,handoff.prediction.fraction,handoff.prediction.period,
            handoff.prediction.step,handoff.prediction.delta,handoff.prediction.expires);
        free(anchors);
    }
    if(fgetc(a)!=EOF || ferror(a)) return 2;
    fclose(a);
    printf("],\"ready_cases\":%u,\"control_ready_cases\":%u}\n",ready_count,control_ready);
    fftw_destroy_plan(plan);fftw_free(workspace);free(records);
    return ready_count==3 && control_ready==0 ? 0:1;
}
