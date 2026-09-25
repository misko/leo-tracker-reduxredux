/* Actual passive observer with saved IQ; no radio or native controller ports. */
#define main original_benchmark_main
#include "adjacent_arm_bench.c"
#undef main
#include "glrt_tracking_observer.h"

struct observer_context { unsigned retained; };
static uint64_t observer_clock(void *p) { (void)p;return now(); }
static int observer_cancelled(void *p) { (void)p;return 0; }
static int observer_retain(void *p,const struct glrt_tracking_observer_trace *t,const int16_t *iq) {
    struct observer_context *ctx=p;(void)iq;
    ctx->retained++;
    return printf("{\"frame\":%u,\"start\":%" PRIu64 ",\"phase\":%u,\"step\":%u,\"coherence\":%.17g,\"delay_s\":%.17g,\"cfo_hz\":%.17g,\"rejection\":%u}\n",
        t->frame,t->job.start,t->job.reference_phase,t->job.phase_step,t->estimate.coherence,
        t->estimate.delay_correction_s,t->estimate.cfo_hz,t->estimate.rejection)<0 ? -1:0;
}
int main(int argc,char **argv) {
    if(argc!=5) return 2;
    unsigned offset=(unsigned)strtoul(argv[4],NULL,10);
    if(offset>2) return 2;
    alarm(15);
    int16_t *iq=malloc(25000000),*storage=malloc(25000000),*refs=malloc(105600),scratch[6600];
    struct glrt_tracking_trend trend;
    struct glrt_tracking_iq_owner owner={0};
    struct glrt_tracking_observer observer;
    struct glrt_tracking_observer_trace trace;
    struct observer_context ctx={0};
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
    if(fclose(f) || glrt_tracking_iq_owner_init(&owner,storage,6250000,1,0) ||
       glrt_tracking_iq_owner_publish(&owner,1,0,iq,6250000,6250000,now()) ||
       glrt_tracking_observer_init_cadence(&observer,&trend,32+offset,3,200,6250000,now(),UINT64_C(5000000000)))return 2;
    int rc;unsigned accepted=0;uint64_t elapsed=now();
    while((rc=glrt_tracking_observer_step(&observer,&owner,refs,scratch,&ports,&trace))==GLRT_OBSERVER_MEASURED)accepted+=trace.accepted;
    elapsed=now()-elapsed;
    if(rc!=GLRT_OBSERVER_DONE || observer.measurements!=200 || ctx.retained!=200)return 3;
    printf("{\"summary\":true,\"offset\":%u,\"measurements\":%u,\"accepted\":%u,\"elapsed_ns\":%" PRIu64 ",\"terminal_status\":%d}\n",offset,observer.measurements,accepted,elapsed,rc);
    if(glrt_tracking_iq_owner_close(&owner,0) || glrt_tracking_iq_owner_destroy(&owner))return 2;
    free(iq);free(storage);free(refs);return fflush(stdout)?2:0;
}
