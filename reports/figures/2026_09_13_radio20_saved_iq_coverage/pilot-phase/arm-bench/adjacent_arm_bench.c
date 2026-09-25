#define _POSIX_C_SOURCE 200809L
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
#include "glrt_tracking_trend.h"
#include "glrt_tracking_iq.h"

static uint64_t now(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) exit(2);
    return (uint64_t)t.tv_sec*1000000000U+t.tv_nsec;
}
static void load(const char *path, void *data, size_t size) {
    FILE *f=fopen(path,"rb");
    if (!f || fread(data,1,size,f)!=size || fgetc(f)!=EOF || fclose(f)) exit(2);
}
int main(int argc,char **argv) {
    struct glrt_tracking_trend trend;
    int16_t *iq=malloc(25000000),*refs=malloc(105600);
    uint64_t total=0,maximum=0;unsigned accepted=0;
    alarm(15);
    if(argc!=4 || !iq || !refs) return 2;
    load(argv[1],iq,25000000);load(argv[2],refs,105600);
    FILE *f=fopen(argv[3],"r");
    if(!f || glrt_tracking_trend_reset(&trend,1,2500000)) return 2;
    for(unsigned k=0;k<32;k++) {
        unsigned frame,phase,rejection;uint64_t start;
        double delay,cfo,coherence;
        if(fscanf(f,"%u %" SCNu64 " %u %lf %lf %lf %u",&frame,&start,&phase,&delay,&cfo,&coherence,&rejection)!=7 || frame!=k) return 2;
        struct glrt_native_estimate e={.delay_correction_s=delay,.cfo_hz=cfo,.coherence=coherence,.rejection=rejection};
        if(glrt_tracking_trend_observe(&trend,1,frame,start,phase,&e)!=(rejection==0)) return 2;
    }
    if(fclose(f))return 2;
    for(unsigned frame=32;frame<1800;frame++) {
        struct glrt_tracking_batch b;struct glrt_tracking_job job;
        struct glrt_tracking_moments m;struct glrt_native_estimate e;double slope;
        uint64_t begin=now();
        if(glrt_tracking_trend_batch(&trend,frame,1,frame,0,&b,&slope) ||
           glrt_tracking_prediction(&b,0,&job) || job.start+3300>6250000 ||
           glrt_tracking_iq_moments_2500000(iq+2*job.start,refs+job.reference_phase*3300*4,
               3300,job.start,0,job.phase_step,&m) ||
           glrt_tracking_solve(2500000,job.reference_phase,&m,&e) ||
           glrt_tracking_trend_observe(&trend,1,frame,job.start,job.reference_phase,&e)!=(e.rejection==0)) return 3;
        uint64_t elapsed=now()-begin;total+=elapsed;if(elapsed>maximum)maximum=elapsed;
        accepted+=e.rejection==0;
        printf("{\"frame\":%u,\"start\":%" PRIu64 ",\"phase\":%u,\"step\":%u,\"coherence\":%.17g,\"delay_s\":%.17g,\"cfo_hz\":%.17g,\"rejection\":%u,\"elapsed_ns\":%" PRIu64 "}\n",
            frame,job.start,job.reference_phase,job.phase_step,e.coherence,e.delay_correction_s,e.cfo_hz,e.rejection,elapsed);
    }
    printf("{\"summary\":true,\"measurements\":1768,\"accepted\":%u,\"compute_ns\":%" PRIu64 ",\"maximum_ns\":%" PRIu64 "}\n",accepted,total,maximum);
    free(iq);free(refs);return fflush(stdout)?2:0;
}
