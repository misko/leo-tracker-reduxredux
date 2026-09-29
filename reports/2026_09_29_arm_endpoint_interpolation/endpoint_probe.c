#define _GNU_SOURCE
#include "endpoint.h"
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef LEO_FULL_ARM_AFFINITY
#include <sched.h>
#endif

enum mode { PAIRS_ONLY, UNION, UNION_FALLBACK };
typedef struct { double epoch,cfo,predicted_cfo; int source,left,right; } seed;
typedef struct {
    leo_presence_candidate c[LEO_ENDPOINT_SEEDS]; int count;
    double preparation_ms,association_ms,interpolation_ms,local_ms,fallback_ms;
    int local_calls,fallback_calls,seeds,positive,fallback_used;
    leo_full_search_result fallback;
} middle_result;

static double ms(void){struct timespec t;clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return t.tv_sec*1000.0+t.tv_nsec/1e6;}
static void *read_all(const char *path,size_t n,size_t item){FILE*f=fopen(path,"rb");void*p=calloc(n,item);if(!f||!p||fread(p,item,n,f)!=n||fgetc(f)!=EOF){if(f)fclose(f);free(p);return NULL;}fclose(f);return p;}

static void candidate_json(const leo_presence_candidate *c,int refined,const char *source,
    int seed_index,int seed_delta,double predicted_epoch,double predicted_cfo)
{
    printf("{\"coarse_epoch\":null,\"coarse_bin\":null,\"refined_epoch\":%d,"
      "\"frame_support\":null,\"glrt_complete\":1,\"refinement_skipped\":true,"
      "\"conditioned_fallback\":false,\"coarse_cfo_hz\":null,\"fine_cfo_hz\":null,"
      "\"conditioned_cfo_hz\":null,\"epoch\":%d,\"acquired_cfo_hz\":%.17g,"
      "\"tracking_cfo_hz\":%.17g,\"exact_score\":%.17g,\"control_score\":%.17g,"
      "\"margin\":%.17g,\"acquire_score\":null,\"verify_score\":null,"
      "\"verify_control_score\":null,\"conditioned_score\":null,\"coarse_score\":null,"
      "\"fields_valid\":{\"timing\":true,\"glrt\":true,\"full_search\":false},"
      "\"seed_source\":\"%s\",\"seed_index\":%d,\"selected_epoch_delta\":%d,"
      "\"predicted_epoch\":%.17g,\"predicted_tracking_cfo_hz\":%.17g}",
      refined,refined,c->acquired_cfo_hz,c->tracking_cfo_hz,c->exact_score,c->control_score,
      c->margin,source,seed_index,seed_delta,predicted_epoch,predicted_cfo);
}

static void full_candidate_json(const leo_full_search_candidate *v)
{
    const leo_presence_candidate*c=&v->candidate;
    printf("{\"coarse_epoch\":%d,\"coarse_bin\":%d,\"refined_epoch\":%d,"
      "\"frame_support\":%d,\"glrt_complete\":%d,\"refinement_skipped\":true,"
      "\"conditioned_fallback\":%s,\"coarse_cfo_hz\":%.17g,\"fine_cfo_hz\":%.17g,"
      "\"conditioned_cfo_hz\":",v->coarse_epoch,v->coarse_bin,v->refined_epoch,
      v->frame_support,v->glrt_complete,v->conditioned_fallback?"true":"false",
      v->coarse_cfo_hz,v->fine_cfo_hz);
    if(v->conditioned_fallback)printf("%.17g",v->conditioned_cfo_hz);else fputs("null",stdout);
    printf(",\"epoch\":%d,\"acquired_cfo_hz\":%.17g,\"tracking_cfo_hz\":%.17g,"
      "\"exact_score\":%.17g,\"control_score\":%.17g,\"margin\":%.17g,"
      "\"acquire_score\":null,\"verify_score\":null,\"verify_control_score\":null,"
      "\"conditioned_score\":",c->epoch,c->acquired_cfo_hz,c->tracking_cfo_hz,
      c->exact_score,c->control_score,c->margin);
    if(v->conditioned_fallback)printf("%.17g",c->conditioned_score);else fputs("null",stdout);
    printf(",\"coarse_score\":%.17g,\"fields_valid\":{\"timing\":true,"
      "\"glrt\":true,\"full_search\":true}}",c->coarse_score);
}

static int make_seeds(uint32_t rate,int window,enum mode mode,
    const leo_full_search_result *a,const leo_full_search_result *b,
    const leo_endpoint_association *as,seed out[16])
{
    int n=0;
    for(int k=0;k<as->pair_count;k++) { const leo_endpoint_pair*p=&as->pairs[k];
        const leo_presence_candidate*l=&a->candidates[p->left].candidate,*r=&b->candidates[p->right].candidate;
        double predicted=l->tracking_cfo_hz+(window/10.0)*(r->tracking_cfo_hz-l->tracking_cfo_hz);
        out[n++]=(seed){leo_endpoint_interpolate_epoch(rate,l->epoch,r->epoch,window),
            leo_endpoint_acquisition_anchor(predicted),predicted,0,p->left,p->right};
    }
    if(mode!=PAIRS_ONLY) {
        for(int k=0;k<as->left_unmatched_count&&n<16;k++) {int i=as->left_unmatched[k];
            double predicted=a->candidates[i].candidate.tracking_cfo_hz;
            out[n++]=(seed){leo_endpoint_project_constant(rate,a->candidates[i].candidate.epoch,window),
                leo_endpoint_acquisition_anchor(predicted),predicted,1,i,-1};}
        for(int k=0;k<as->right_unmatched_count&&n<16;k++) {int i=as->right_unmatched[k];
            double predicted=b->candidates[i].candidate.tracking_cfo_hz;
            out[n++]=(seed){leo_endpoint_project_constant(rate,b->candidates[i].candidate.epoch,window),
                leo_endpoint_acquisition_anchor(predicted),predicted,2,-1,i};}
    }
    return n;
}

static int local_run(uint32_t rate,leo_presence_workspace*w,const leo_presence_complex*x,size_t count,
    const seed*s,leo_presence_candidate*out,int *chosen,int *attempts)
{
    int center=(int)nearbyint(s->epoch),valid=0,best_delta=0,best_epoch=0;double best[3]={0};
    *attempts=0;if(!isfinite(s->cfo))return 0;
    int frame=(rate+375)/750;
    for(int d=-1;d<=1;d++) {double score[3];int epoch=(int)nearbyint(leo_endpoint_wrap(rate,center+d));if(epoch>=frame)epoch=0;
        ++*attempts;if(leo_presence_glrt(w,x,count,epoch,s->cfo,0,score))continue;
        if(!valid||score[0]-score[1]>best[0]-best[1]||
          (score[0]-score[1]==best[0]-best[1]&&score[0]>best[0])) {
            memcpy(best,score,sizeof(best));best_delta=d;best_epoch=epoch;valid=1;
        }
    }
    if(!valid)return 0;
    memset(out,0,sizeof(*out));out->epoch=best_epoch;
    out->acquired_cfo_hz=s->cfo;out->tracking_cfo_hz=s->cfo+best[2];
    out->exact_score=best[0];out->control_score=best[1];out->margin=best[0]-best[1];
    *chosen=best_delta;return 1;
}

static void emit_full(int rx,int win,const leo_full_search_result*r,const char*mode,
    int pair_count,int endpoint_calls,double preparation_ms)
{
    printf("{\"receiver_id\":%d,\"probe_index\":%d,\"refinement_mode\":\"endpoint_interpolation\","
      "\"interpolation_mode\":\"%s\",\"candidate_count\":%d,\"retained_peak_count\":%d,"
      "\"timings_ms\":{\"total_cpu\":%.17g,\"sample_preparation\":%.17g,"
      "\"endpoint_discovery\":%.17g,\"interpolation\":0,\"local_glrt\":0,"
      "\"fallback\":0,\"glrt\":%.17g},"
      "\"instrumentation\":{\"kernel_calls\":%d,\"endpoint_glrt_kernel_attempts\":%d,"
      "\"middle_glrt_kernel_attempts\":0,\"local_delta_glrt_kernel_attempts\":0,"
      "\"fallback_glrt_kernel_attempts\":0,\"anchor_search_count\":1,"
      "\"association_pair_count\":%d,\"seed_count\":0},\"candidates\":[",
      rx,win,mode,r->candidate_count,r->retained_peak_count,r->total_cpu_ms+preparation_ms,
      preparation_ms,r->total_cpu_ms,
      r->glrt_cpu_ms,endpoint_calls,endpoint_calls,pair_count);
    for(int i=0;i<r->candidate_count;i++){if(i)putchar(',');full_candidate_json(&r->candidates[i]);}
    puts("]}");
}

static void emit_middle(int rx,int win,const middle_result*m,const char*mode,int pairs,
    const seed seeds[16],const int chosen[16])
{
    int count=m->fallback_used?m->fallback.candidate_count:m->count;
    double total=m->preparation_ms+m->association_ms+m->interpolation_ms+m->local_ms+m->fallback_ms;
    printf("{\"receiver_id\":%d,\"probe_index\":%d,\"refinement_mode\":\"endpoint_interpolation\","
      "\"interpolation_mode\":\"%s\",\"candidate_count\":%d,\"retained_peak_count\":%d,"
      "\"timings_ms\":{\"total_cpu\":%.17g,\"sample_preparation\":%.17g,\"endpoint_discovery\":0,"
      "\"association\":%.17g,\"interpolation\":%.17g,\"local_glrt\":%.17g,\"fallback\":%.17g,"
      "\"glrt\":%.17g},\"instrumentation\":{\"kernel_calls\":%d,"
      "\"endpoint_glrt_kernel_attempts\":0,\"middle_glrt_kernel_attempts\":%d,"
      "\"local_delta_glrt_kernel_attempts\":%d,\"fallback_glrt_kernel_attempts\":%d,"
      "\"anchor_search_count\":0,\"association_pair_count\":%d,\"seed_count\":%d,"
      "\"positive_local_count\":%d,\"fallback_used\":%s},\"candidates\":[",
      rx,win,mode,count,m->fallback_used?m->fallback.retained_peak_count:0,total,
      m->preparation_ms,m->association_ms,m->interpolation_ms,m->local_ms,m->fallback_ms,
      m->fallback_used?m->fallback.glrt_cpu_ms:m->local_ms,m->local_calls+m->fallback_calls,
      m->local_calls,m->local_calls,m->fallback_calls,pairs,m->seeds,m->positive,
      m->fallback_used?"true":"false");
    if(m->fallback_used) for(int i=0;i<count;i++){if(i)putchar(',');full_candidate_json(&m->fallback.candidates[i]);}
    else for(int i=0;i<count;i++){if(i)putchar(',');const char*src=seeds[i].source==0?"paired":seeds[i].source==1?"left_nearest":"right_nearest";candidate_json(&m->c[i],m->c[i].epoch,src,i,chosen[i],seeds[i].epoch,seeds[i].predicted_cfo);}
    puts("]}");
}

int main(int argc,char**argv)
{
#ifdef LEO_FULL_ARM_AFFINITY
    cpu_set_t allowed;CPU_ZERO(&allowed);CPU_SET(0,&allowed);if(sched_setaffinity(0,sizeof(allowed),&allowed))return 6;
#endif
    if(argc!=6)return 2;
    char*end;errno=0;unsigned long rate=strtoul(argv[1],&end,10);
    if(errno||*end||(rate!=2500000&&rate!=5000000&&rate!=7500000&&rate!=10000000))return 2;
    enum mode mode; if(!strcmp(argv[5],"pairs-only"))mode=PAIRS_ONLY;else if(!strcmp(argv[5],"union"))mode=UNION;else if(!strcmp(argv[5],"union-fallback"))mode=UNION_FALLBACK;else return 2;
    size_t frame=(rate+375)/750,dwell=rate*120/1000,probe=rate/50,stride=rate/100;
    leo_presence_complex*exact=read_all(argv[2],frame,sizeof(*exact)),*control=read_all(argv[3],frame,sizeof(*control));
    short*iq=read_all(argv[4],dwell*4,sizeof(*iq));if(!exact||!control||!iq)return 2;
    leo_presence_workspace*w=leo_presence_create(rate,exact,control,frame);leo_presence_complex*x=calloc(probe,sizeof(*x));if(!w||!x)return 3;
    leo_full_search_result endpoints[2][2];double endpoint_prep[2][2];leo_endpoint_association assoc[2];middle_result middle[2][9];seed seeds[2][9][16];int chosen[2][9][16];
    memset(middle,0,sizeof(middle));memset(chosen,0,sizeof(chosen));
    /* Discovery order is deliberately first then last, after the complete
     * 120 ms dwell is available. No middle result is computed before both. */
    for(int anchor=0;anchor<2;anchor++){int win=leo_endpoint_execution_window(anchor);for(int rx=0;rx<2;rx++){
        double prep=ms();
        for(size_t i=0;i<probe;i++){size_t at=((size_t)win*stride+i)*4+rx*2;x[i]=(leo_presence_complex){iq[at],iq[at+1]};}
        endpoint_prep[rx][anchor]=ms()-prep;
        if(leo_full_search_run(w,x,probe,&endpoints[rx][anchor]))return 4;
    }}
    double association_ms[2];for(int rx=0;rx<2;rx++){double t=ms();if(leo_endpoint_associate(rate,&endpoints[rx][0],&endpoints[rx][1],&assoc[rx]))return 4;association_ms[rx]=ms()-t;}
    for(int win=1;win<10;win++)for(int rx=0;rx<2;rx++){
        middle_result*m=&middle[rx][win-1];if(win==1)m->association_ms=association_ms[rx];double t=ms();m->seeds=make_seeds(rate,win,mode,&endpoints[rx][0],&endpoints[rx][1],&assoc[rx],seeds[rx][win-1]);m->interpolation_ms=ms()-t;
        t=ms();for(size_t i=0;i<probe;i++){size_t at=((size_t)win*stride+i)*4+rx*2;x[i]=(leo_presence_complex){iq[at],iq[at+1]};}m->preparation_ms=ms()-t;
        t=ms();for(int s=0;s<m->seeds;s++){int attempts=0;seed attempted=seeds[rx][win-1][s];if(local_run(rate,w,x,probe,&attempted,&m->c[m->count],&chosen[rx][win-1][m->count],&attempts)){seeds[rx][win-1][m->count]=attempted;if(m->c[m->count].margin>=.025)m->positive++;m->count++;}m->local_calls+=attempts;}m->local_ms=ms()-t;
        if(mode==UNION_FALLBACK&&!m->positive){t=ms();if(leo_full_search_run(w,x,probe,&m->fallback))return 4;m->fallback_ms=ms()-t;m->fallback_used=1;m->fallback_calls=m->fallback.candidate_count+m->fallback.conditioned_fallback_count;}
    }
    const char*names[]={"pairs-only","union","union-fallback"};
    for(int win=0;win<11;win++)for(int rx=0;rx<2;rx++)if(win==0||win==10){int a=win==10;leo_full_search_result*r=&endpoints[rx][a];emit_full(rx,win,r,names[mode],assoc[rx].pair_count,r->candidate_count+r->conditioned_fallback_count,endpoint_prep[rx][a]);}else emit_middle(rx,win,&middle[rx][win-1],names[mode],assoc[rx].pair_count,seeds[rx][win-1],chosen[rx][win-1]);
    leo_presence_destroy(w);free(x);free(iq);free(control);free(exact);return 0;
}
