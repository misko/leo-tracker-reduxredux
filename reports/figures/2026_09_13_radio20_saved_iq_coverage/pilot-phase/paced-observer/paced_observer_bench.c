/* Actual passive observer with saved IQ; no radio or native controller ports. */
#define main original_benchmark_main
#include "adjacent_arm_bench.c"
#undef main
#include "glrt_tracking_observer.h"

#include <errno.h>
#include <string.h>
struct observer_context {
    unsigned retained;
    struct glrt_tracking_iq_owner *owner;
    const int16_t *input;
    FILE *retention;
    uint64_t origin_ns, maximum_age;
    int producer_result;
};
static void *produce(void *p) {
    struct observer_context *ctx=p;
    for(uint64_t at=114688;at<2392064;at+=16384) {
        uint64_t target=ctx->origin_ns+(at+16384-114688)*400;
        struct timespec deadline={(time_t)(target/1000000000),(long)(target%1000000000)};
        int rc;
        do { rc=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&deadline,NULL); } while(rc==EINTR);
        if(rc || glrt_tracking_iq_owner_publish(ctx->owner,1,at,ctx->input+2*at,16384,at+16384,now())) {
            ctx->producer_result=-1;break;
        }
    }
    return NULL;
}
static uint64_t observer_clock(void *p) { (void)p;return now(); }
static int observer_cancelled(void *p) { (void)p;return 0; }
static int observer_retain(void *p,const struct glrt_tracking_observer_trace *t,const int16_t *iq) {
    struct observer_context *ctx=p;
    if(t->source.source_now<t->job.start+3300 ||
       memcmp(iq,ctx->input+2*t->job.start,3300*4) ||
       fwrite(iq,4,3300,ctx->retention)!=3300 || fflush(ctx->retention))return -1;
    uint64_t age=t->source.source_now-t->job.start;
    if(age>ctx->maximum_age)ctx->maximum_age=age;
    ctx->retained++;
    return printf("{\"frame\":%u,\"start\":%" PRIu64 ",\"phase\":%u,\"step\":%u,\"coherence\":%.17g,\"delay_s\":%.17g,\"cfo_hz\":%.17g,\"rejection\":%u}\n",
        t->frame,t->job.start,t->job.reference_phase,t->job.phase_step,t->estimate.coherence,
        t->estimate.delay_correction_s,t->estimate.cfo_hz,t->estimate.rejection)<0 ? -1:0;
}
int main(int argc,char **argv) {
    if(argc!=6) return 2;
    unsigned offset=(unsigned)strtoul(argv[4],NULL,10);
    if(offset>2) return 2;
    alarm(15);
    int16_t *iq=malloc(25000000),*storage=malloc(131072*4),*refs=malloc(105600),scratch[6600];
    struct glrt_tracking_trend trend;
    struct glrt_tracking_iq_owner owner={0};
    struct glrt_tracking_observer observer;
    struct glrt_tracking_observer_trace trace;
    struct observer_context ctx={0};pthread_t producer;
    struct glrt_tracking_observer_ports ports={&ctx,observer_clock,observer_cancelled,observer_retain};
    if(!iq || !storage || !refs || glrt_tracking_trend_reset(&trend,1,2500000))return 2;
    load(argv[1],iq,25000000);load(argv[2],refs,105600);
    FILE *f=fopen(argv[3],"r");if(!f)return 2;
    for(unsigned k=0;k<32;k++) {
        unsigned frame,phase,rejection;uint64_t start;double delay,cfo,coherence;
        if(fscanf(f,"%u %" SCNu64 " %u %lf %lf %lf %u",&frame,&start,&phase,&delay,&cfo,&coherence,&rejection)!=7 || frame!=k)return 2;
        struct glrt_native_estimate e={.delay_correction_s=delay,.cfo_hz=cfo,.coherence=coherence,.rejection=rejection};
        if(glrt_tracking_trend_observe(&trend,1,frame,start,phase,&e)!=(rejection==0))return 2;
    }
    if(fclose(f) || glrt_tracking_iq_owner_init(&owner,storage,131072,1,0) ||
       glrt_tracking_iq_owner_publish(&owner,1,0,iq,114688,114688,now()) ||
       glrt_tracking_observer_init_cadence(&observer,&trend,32+offset,3,200,2500000,now(),UINT64_C(2000000000)))return 2;
    ctx.owner=&owner;ctx.input=iq;ctx.retention=fopen(argv[5],"wb");ctx.origin_ns=now();
    if(!ctx.retention || pthread_create(&producer,NULL,produce,&ctx))return 2;
    int rc;unsigned accepted=0,waits=0;uint64_t elapsed=now();
    for(;;) {
        rc=glrt_tracking_observer_step(&observer,&owner,refs,scratch,&ports,&trace);
        if(rc==GLRT_OBSERVER_MEASURED) { accepted+=trace.accepted;continue; }
        if(rc!=GLRT_OBSERVER_WAIT)break;
        struct timespec pause={0,200000};nanosleep(&pause,NULL);waits++;
    }
    elapsed=now()-elapsed;
    if(pthread_join(producer,NULL) || ctx.producer_result || fclose(ctx.retention))return 2;
    if(rc!=GLRT_OBSERVER_DONE || observer.measurements!=200 || ctx.retained!=200)return 3;
    printf("{\"summary\":true,\"offset\":%u,\"measurements\":%u,\"accepted\":%u,\"elapsed_ns\":%" PRIu64 ",\"terminal_status\":%d,\"waits\":%u,\"maximum_source_age_samples\":%" PRIu64 "}\n",offset,observer.measurements,accepted,elapsed,rc,waits,ctx.maximum_age);
    if(glrt_tracking_iq_owner_close(&owner,0) || glrt_tracking_iq_owner_destroy(&owner))return 2;
    free(iq);free(storage);free(refs);return fflush(stdout)?2:0;
}
