/* Persistent-workspace full-inventory runner for one saved dual-CI16 dwell. */
#define _GNU_SOURCE
#include "full_search.h"
#include <complex.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#ifdef LEO_FULL_ARM_AFFINITY
#include <sched.h>
#endif

static void emit(int rx, int window, const leo_full_search_result *r) {
    printf("{\"receiver_id\":%d,\"probe_index\":%d,\"refinement_mode\":\"boundary_fallback\",\"candidate_count\":%d,\"retained_peak_count\":%d,\"conditioned_fallback_count\":%d,\"timings_ms\":{\"total_cpu\":%.17g,\"coarse\":%.17g,\"acquisition\":%.17g,\"fine_fft\":%.17g,\"conditioned\":%.17g,\"verification\":%.17g,\"glrt\":%.17g},\"conditioned_bins_screened\":%d,\"conditioned_bins_rechecked\":%d,\"candidates\":[",rx,window,r->candidate_count,r->retained_peak_count,r->conditioned_fallback_count,r->total_cpu_ms,r->coarse_cpu_ms,r->acquisition_cpu_ms,r->fine_fft_cpu_ms,r->conditioned_cpu_ms,r->verification_cpu_ms,r->glrt_cpu_ms,r->conditioned_bins_screened,r->conditioned_bins_rechecked);
    for (int i=0;i<r->candidate_count;i++) { const leo_full_search_candidate *v=&r->candidates[i]; const leo_presence_candidate *c=&v->candidate;
        printf("%s{\"coarse_epoch\":%d,\"coarse_bin\":%d,\"refined_epoch\":%d,\"frame_support\":%d,\"glrt_complete\":%d,\"refinement_skipped\":true,\"conditioned_fallback\":%s,\"coarse_cfo_hz\":%.17g,\"fine_cfo_hz\":",i?",":"",v->coarse_epoch,v->coarse_bin,v->refined_epoch,v->frame_support,v->glrt_complete,v->conditioned_fallback?"true":"false",v->coarse_cfo_hz);
        if(LEO_FULL_REFINEMENT_MODE==1) fputs("null,\"conditioned_cfo_hz\":null",stdout);
        else if(LEO_FULL_REFINEMENT_MODE==2) {printf("%.17g,\"conditioned_cfo_hz\":",v->fine_cfo_hz);if(v->conditioned_fallback)printf("%.17g",v->conditioned_cfo_hz);else fputs("null",stdout);}
        else printf("%.17g,\"conditioned_cfo_hz\":%.17g",v->fine_cfo_hz,v->conditioned_cfo_hz);
        printf(",\"epoch\":%d,\"acquired_cfo_hz\":%.17g,\"tracking_cfo_hz\":%.17g,\"exact_score\":%.17g,\"control_score\":%.17g,\"margin\":%.17g,\"acquire_score\":",c->epoch,c->acquired_cfo_hz,c->tracking_cfo_hz,c->exact_score,c->control_score,c->margin);
        if(v->refinement_skipped){fputs("null,\"verify_score\":null,\"verify_control_score\":null,\"conditioned_score\":",stdout);if(v->conditioned_fallback)printf("%.17g",c->conditioned_score);else fputs("null",stdout);}
        else printf("%.17g,\"verify_score\":%.17g,\"verify_control_score\":%.17g,\"conditioned_score\":%.17g",c->acquire_score,c->verify_score,c->verify_control_score,c->conditioned_score);
        printf(",\"coarse_score\":%.17g}",c->coarse_score);
    } puts("]}");
}
static void *read_all(const char *path,size_t n,size_t item) { FILE *f=fopen(path,"rb"); void *p=calloc(n,item); if(!f||!p||fread(p,item,n,f)!=n||fgetc(f)!=EOF){if(f)fclose(f);free(p);return NULL;}fclose(f);return p; }
int main(int argc,char **argv) {
#ifdef LEO_FULL_ARM_AFFINITY
    cpu_set_t allowed; CPU_ZERO(&allowed); CPU_SET(0,&allowed);
    if (sched_setaffinity(0,sizeof(allowed),&allowed)) return 6;
#endif
    if(argc!=5) return 2;
    char *end; errno=0; unsigned long rate=strtoul(argv[1],&end,10);
    if (errno || *end || (rate!=2500000 && rate!=5000000 && rate!=7500000 && rate!=10000000)) return 2;
    size_t frame=(rate+375)/750, dwell=rate*120/1000, probe=rate/50, stride=rate/100;
    leo_presence_complex *exact=read_all(argv[2],frame,sizeof(*exact)),*control=read_all(argv[3],frame,sizeof(*control)); short *ci16=read_all(argv[4],dwell*4,sizeof(*ci16)); if(!exact||!control||!ci16)return 2;
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,frame); leo_presence_complex *samples=calloc(probe,sizeof(*samples)); if(!w||!samples)return 3;
    for(int window=0;window<11;window++) for(int rx=0;rx<2;rx++){ for(size_t i=0;i<probe;i++){size_t at=((size_t)window*stride+i)*4+rx*2;samples[i]=(leo_presence_complex){ci16[at],ci16[at+1]};} leo_full_search_result r; if(leo_full_search_run(w,samples,probe,&r)) return 4; emit(rx,window,&r); fflush(stdout); }
    leo_presence_destroy(w);free(samples);free(ci16);free(control);free(exact);return 0;
}
