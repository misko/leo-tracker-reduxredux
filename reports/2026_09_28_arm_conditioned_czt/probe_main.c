#define _GNU_SOURCE
#include "full_search.h"
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#ifdef LEO_FULL_ARM_AFFINITY
#include <sched.h>
#endif

static void *read_items(const char *path, size_t count, size_t size)
{
    FILE *f=fopen(path,"rb");
    void *p=calloc(count,size);
    if (!f || !p || fread(p,size,count,f)!=count || fgetc(f)!=EOF) {
        fprintf(stderr,"Invalid binary input: %s\n",path);
        if (f) fclose(f);
        free(p); return NULL;
    }
    fclose(f); return p;
}

int main(int argc, char **argv)
{
#ifdef LEO_FULL_ARM_AFFINITY
    cpu_set_t allowed;
    CPU_ZERO(&allowed); CPU_SET(0,&allowed);
    if (sched_setaffinity(0,sizeof(allowed),&allowed)) {
        perror("CPU0 affinity"); return 6;
    }
#endif
    if (argc!=7) {
        fprintf(stderr,"Usage: probe rate exact.c128 control.c128 probe.c128 coarse.f64 repeats\n");
        return 2;
    }
    char *end;
    errno=0;
    unsigned long rate=strtoul(argv[1],&end,10);
    if (errno || *end || (rate!=2500000 && rate!=5000000 && rate!=7500000 && rate!=10000000)) return 2;
    unsigned long repeats=strtoul(argv[6],&end,10);
    if (*end || !repeats || repeats>100) return 2;
    size_t n=(size_t)((rate+375)/750), count=rate/50;
    leo_presence_complex *exact=read_items(argv[2],n,sizeof(*exact));
    leo_presence_complex *control=read_items(argv[3],n,sizeof(*control));
    leo_presence_complex *probe=read_items(argv[4],count,sizeof(*probe));
    if (!exact || !control || !probe) return 2;
    leo_presence_workspace *w=leo_presence_create((uint32_t)rate,exact,control,n);
    if (!w) { fprintf(stderr,"Workspace creation failed\n"); return 3; }
    double *grid=calloc(11*n,sizeof(double));
    if (!grid || leo_presence_coarse(w,probe,count,grid)) return 4;
    FILE *f=fopen(argv[5],"wb");
    if (!f || fwrite(grid,sizeof(double),11*n,f)!=11*n || fclose(f)) return 4;
    leo_full_search_result result;
    double total=0;
    for (unsigned long r=0; r<repeats; ++r) {
        if (leo_full_search_run(w,probe,count,&result)) return 5;
        total+=result.total_cpu_ms;
    }
    printf("{\"candidate_count\":%d,\"retained_peak_count\":%d,\"repeats\":%lu,\"mean_cpu_ms\":%.17g,\"timings_ms\":{\"total_cpu\":%.17g,\"coarse\":%.17g,\"acquisition\":%.17g,\"glrt\":%.17g,\"fine_fft\":%.17g,\"conditioned\":%.17g,\"verification\":%.17g},\"conditioned_bins_screened\":%d,\"conditioned_bins_rechecked\":%d,\"candidates\":[",
        result.candidate_count,result.retained_peak_count,repeats,total/repeats,
        result.total_cpu_ms,result.coarse_cpu_ms,result.acquisition_cpu_ms,result.glrt_cpu_ms,
        result.fine_fft_cpu_ms,result.conditioned_cpu_ms,result.verification_cpu_ms,
        result.conditioned_bins_screened,result.conditioned_bins_rechecked);
    for (int i=0; i<result.candidate_count; ++i) {
        const leo_full_search_candidate *v=&result.candidates[i];
        const leo_presence_candidate *c=&v->candidate;
        printf("%s{\"coarse_epoch\":%d,\"coarse_bin\":%d,\"refined_epoch\":%d,\"frame_support\":%d,\"glrt_complete\":%d,\"coarse_cfo_hz\":%.17g,\"fine_cfo_hz\":%.17g,\"conditioned_cfo_hz\":%.17g,\"epoch\":%d,\"acquired_cfo_hz\":%.17g,\"tracking_cfo_hz\":%.17g,\"exact_score\":%.17g,\"control_score\":%.17g,\"margin\":%.17g,\"acquire_score\":%.17g,\"verify_score\":%.17g,\"verify_control_score\":%.17g,\"conditioned_score\":%.17g,\"coarse_score\":%.17g}",
            i ? "," : "",v->coarse_epoch,v->coarse_bin,v->refined_epoch,v->frame_support,v->glrt_complete,
            v->coarse_cfo_hz,v->fine_cfo_hz,v->conditioned_cfo_hz,c->epoch,c->acquired_cfo_hz,
            c->tracking_cfo_hz,c->exact_score,c->control_score,c->margin,c->acquire_score,
            c->verify_score,c->verify_control_score,c->conditioned_score,c->coarse_score);
    }
    puts("]}");
    leo_presence_destroy(w); free(exact); free(control); free(probe); free(grid);
    return 0;
}
