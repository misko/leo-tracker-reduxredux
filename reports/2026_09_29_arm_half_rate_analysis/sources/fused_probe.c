/* Persistent-workspace full-inventory runner for one saved dual-CI16 dwell. */
#define _GNU_SOURCE
static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include "proposal_core.h"
#include <complex.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#ifdef LEO_FULL_ARM_AFFINITY
#include <sched.h>
#endif

static void emit(int rx, int window, const leo_full_search_result *r,
    const leo_proposal_timing *p, double fused_cpu_ms) {
    printf("{\"receiver_id\":%d,\"probe_index\":%d,\"refinement_mode\":\"boundary_fallback\",\"candidate_count\":%d,\"retained_peak_count\":%d,\"conditioned_fallback_count\":%d,\"actual_executed_glrt_calls\":%d,\"glrt_cache_hits\":%d,\"conditioned_cache_hits\":%d,\"fine_fft_cache_entries\":%d,\"fine_fft_cache_hits\":%d,\"fine_precision_mode\":\"raw\",\"fine_frame_budget\":%d,\"coarse_frames\":16,\"coarse_fixed_scale\":32768,\"conditioned_moments\":\"v3\",\"conditioned_frames\":16,\"skip_conditioned_recheck\":%d,\"final_scorer\":\"fp64\",\"fine_precision_calls\":%d,\"fine_precision_guard_checks\":%d,\"fine_precision_fallbacks\":%d,\"fine_precision_nonfinite_fallbacks\":%d,\"fine_precision_near_tie_fallbacks\":%d,\"fine_precision_interpolation_fallbacks\":%d,\"timings_ms\":{\"total_cpu\":%.17g,\"proposal\":%.17g,\"stage_sum\":%.17g,\"fused_total\":%.17g,\"proposal_fold\":%.17g,\"proposal_correlation\":%.17g,\"proposal_ranking\":%.17g,\"coarse\":%.17g,\"acquisition\":%.17g,\"fine_fft\":%.17g,\"conditioned\":%.17g,\"verification\":%.17g,\"glrt\":%.17g},\"conditioned_bins_screened\":%d,\"conditioned_bins_rechecked\":%d,\"candidates\":[",rx,window,r->candidate_count,r->retained_peak_count,r->conditioned_fallback_count,r->actual_executed_glrt_calls,r->glrt_cache_hits,r->conditioned_cache_hits,r->fine_fft_cache_entries,r->fine_fft_cache_hits,leo_fine_precision_frame_budget,SKIP_CONDITIONED_RECHECK,r->fine_precision_calls,r->fine_precision_guard_checks,r->fine_precision_fallbacks,r->fine_precision_nonfinite_fallbacks,r->fine_precision_near_tie_fallbacks,r->fine_precision_interpolation_fallbacks,r->total_cpu_ms,p->total_ms,p->total_ms+r->total_cpu_ms,fused_cpu_ms,p->fold_ms,p->correlation_ms,p->ranking_ms,r->coarse_cpu_ms,r->acquisition_cpu_ms,r->fine_fft_cpu_ms,r->conditioned_cpu_ms,r->verification_cpu_ms,r->glrt_cpu_ms,r->conditioned_bins_screened,r->conditioned_bins_rechecked);
    for (int i=0;i<r->candidate_count;i++) { const leo_full_search_candidate *v=&r->candidates[i]; const leo_presence_candidate *c=&v->candidate;
        printf("%s{\"coarse_epoch\":%d,\"coarse_bin\":%d,\"refined_epoch\":%d,\"frame_support\":%d,\"glrt_complete\":%d,\"refinement_skipped\":true,\"conditioned_fallback\":%s,\"coarse_cfo_hz\":%.17g,\"fine_cfo_hz\":",i?",":"",2*v->coarse_epoch,v->coarse_bin,2*v->refined_epoch,v->frame_support,v->glrt_complete,v->conditioned_fallback?"true":"false",v->coarse_cfo_hz);
        if(LEO_FULL_REFINEMENT_MODE==1) fputs("null,\"conditioned_cfo_hz\":null",stdout);
        else if(LEO_FULL_REFINEMENT_MODE==2) {printf("%.17g,\"conditioned_cfo_hz\":",v->fine_cfo_hz);if(v->conditioned_fallback)printf("%.17g",v->conditioned_cfo_hz);else fputs("null",stdout);}
        else printf("%.17g,\"conditioned_cfo_hz\":%.17g",v->fine_cfo_hz,v->conditioned_cfo_hz);
        printf(",\"epoch\":%d,\"acquired_cfo_hz\":%.17g,\"tracking_cfo_hz\":%.17g,\"exact_score\":%.17g,\"control_score\":%.17g,\"margin\":%.17g,\"acquire_score\":",2*c->epoch,c->acquired_cfo_hz,c->tracking_cfo_hz,c->exact_score,c->control_score,c->margin);
        if(v->refinement_skipped){fputs("null,\"verify_score\":null,\"verify_control_score\":null,\"conditioned_score\":",stdout);if(v->conditioned_fallback)printf("%.17g",c->conditioned_score);else fputs("null",stdout);}
        else printf("%.17g,\"verify_score\":%.17g,\"verify_control_score\":%.17g,\"conditioned_score\":%.17g",c->acquire_score,c->verify_score,c->verify_control_score,c->conditioned_score);
        printf(",\"coarse_score\":%.17g}",c->coarse_score);
    } puts("]}");
}
static void *read_all(const char *path,size_t n,size_t item) { FILE *f=fopen(path,"rb"); void *p=calloc(n,item); if(!f||!p||fread(p,item,n,f)!=n||fgetc(f)!=EOF){if(f)fclose(f);free(p);return NULL;}fclose(f);return p; }
static int half_rate_copy_templates(const leo_presence_complex *src,size_t src_n,leo_presence_complex *dst,size_t dst_n){if(!src||!dst||(dst_n&&2*(dst_n-1)>=src_n))return -1;for(size_t k=0;k<dst_n;k++)dst[k]=src[2*k];return 0;}
static int half_rate_copy_ci16(const short *src,size_t src_samples,short *dst,size_t dst_samples){if(!src||!dst||(dst_samples&&2*(dst_samples-1)>=src_samples))return -1;for(size_t k=0;k<dst_samples;k++)for(int c=0;c<4;c++)dst[4*k+c]=src[8*k+c];return 0;}
int main(int argc,char **argv) {
#ifdef LEO_FULL_ARM_AFFINITY
    cpu_set_t allowed; CPU_ZERO(&allowed); CPU_SET(0,&allowed);
    if (sched_setaffinity(0,sizeof(allowed),&allowed)) return 6;
#endif
    int top=4;
    if(argc==6 && !strcmp(argv[5],"--top=3")) top=3;
    else if(argc==6 && !strcmp(argv[5],"--top=4")) top=4;
    else if(argc!=5) return 2;
    const char *budget_text=getenv("LEO_FINE_FRAME_BUDGET");
    if(budget_text) {char *budget_end;errno=0;long budget=strtol(budget_text,&budget_end,10);
        if(errno||*budget_end||leo_fine_precision_set_frame_budget((int)budget))return 2;}
    char *end; errno=0; unsigned long rate=strtoul(argv[1],&end,10);
    if (errno || *end || (rate!=2500000 && rate!=5000000 && rate!=7500000 && rate!=10000000)) return 2;
    size_t original_frame=(rate+375)/750,original_dwell=rate*120/1000;
    unsigned long effective_rate=rate/2;size_t frame=(effective_rate+375)/750,dwell=effective_rate*120/1000,probe=effective_rate/50,stride=effective_rate/100;
    leo_presence_complex *original_exact=read_all(argv[2],original_frame,sizeof(*original_exact)),*original_control=read_all(argv[3],original_frame,sizeof(*original_control));short *original_ci16=read_all(argv[4],original_dwell*4,sizeof(*original_ci16));
    leo_presence_complex *exact=calloc(frame,sizeof(*exact)),*control=calloc(frame,sizeof(*control));short *ci16=calloc(dwell*4,sizeof(*ci16));if(!original_exact||!original_control||!original_ci16||!exact||!control||!ci16)return 2;
    double decimation_begin=clock_ms(CLOCK_PROCESS_CPUTIME_ID);if(half_rate_copy_templates(original_exact,original_frame,exact,frame)||half_rate_copy_templates(original_control,original_frame,control,frame)||half_rate_copy_ci16(original_ci16,original_dwell,ci16,dwell))return 2;double decimation_share=(clock_ms(CLOCK_PROCESS_CPUTIME_ID)-decimation_begin)/22.0;
    free(original_ci16);free(original_control);free(original_exact);
    leo_presence_workspace *w=leo_presence_create(effective_rate,exact,control,frame); leo_presence_complex *samples=calloc(probe,sizeof(*samples));
    leo_proposal_workspace *proposal=leo_proposal_create((const double (*)[2])exact,frame,(double)effective_rate);
    unsigned char *selected=calloc(frame,1); if(!w||!samples||!proposal||!selected)return 3;
    for(int window=0;window<11;window++) for(int rx=0;rx<2;rx++){
        double fused_begin=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        int centers[4],center_count=0;leo_proposal_timing pt;
        if(leo_proposal_top4(proposal,ci16,(size_t)window*stride,rx,centers,&center_count,&pt))return 5;
        if(center_count>top)center_count=top;
        memset(selected,0,frame);
        for(int c=0;c<center_count;c++){int first=centers[c]-2,last=centers[c]+2;if(first<0)first=0;if(last>=(int)frame)last=(int)frame-1;for(int epoch=first;epoch<=last;epoch++)selected[epoch]=1;}
        regional_count=0;for(size_t epoch=0;epoch<frame;epoch++)if(selected[epoch])regional_epochs[regional_count++]=(int)epoch;
        for(size_t i=0;i<probe;i++){size_t at=((size_t)window*stride+i)*4+rx*2;samples[i]=(leo_presence_complex){ci16[at],ci16[at+1]};} leo_full_search_result r; if(leo_full_search_run(w,samples,probe,&r)) return 4;
        double fused_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-fused_begin+decimation_share;
        emit(rx,window,&r,&pt,fused_cpu_ms); fflush(stdout); }
    free(selected);leo_proposal_destroy(proposal);leo_presence_destroy(w);free(samples);free(ci16);free(control);free(exact);return 0;
}
