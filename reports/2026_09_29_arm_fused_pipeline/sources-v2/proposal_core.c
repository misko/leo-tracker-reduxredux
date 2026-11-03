#define _GNU_SOURCE
#include <errno.h>
#include <float.h>
#include <fftw3.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "proposal_core.h"
#ifdef LEO_LAG_ARM_AFFINITY
#include <sched.h>
#endif
#ifdef LEO_PROPOSAL_NEON_FOLD
#include <arm_neon.h>
#endif

enum { METHODS=5, LAG_COUNT=3, TOP=32, FRAMES=16 };
static const int lags[LAG_COUNT]={1,3,5};
typedef struct {float score;int index;} ranked;
typedef struct {
    size_t n; double rate;
    fftwf_complex *time,*freq,*product,*corr,*reference_fft[METHODS];
    float reference_norm[METHODS],*scores[METHODS]; int *support; ranked *ranking,*rank_scratch;
    fftwf_plan forward,backward;
} bank;
static double now_ms(void){struct timespec t;clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return 1e3*t.tv_sec+1e-6*t.tv_nsec;}
static float power(float r,float i){return r*r+i*i;}
static __attribute__((unused)) int read_exact(const char *path,void *data,size_t size){FILE *f=fopen(path,"rb");if(!f)return -1;int ok=fread(data,1,size,f)==size&&fgetc(f)==EOF;fclose(f);return ok?0:-1;}
static void center_norm(fftwf_complex *x,size_t n,float *norm){float mr=0,mi=0;for(size_t k=0;k<n;k++){mr+=x[k][0];mi+=x[k][1];}mr/=n;mi/=n;float e=0;for(size_t k=0;k<n;k++){x[k][0]-=mr;x[k][1]-=mi;e+=power(x[k][0],x[k][1]);}*norm=sqrtf(e);}
static int bank_init(bank *b,const fftwf_complex *t,size_t n,double rate){memset(b,0,sizeof(*b));b->n=n;b->rate=rate;b->time=fftwf_alloc_complex(n);b->freq=fftwf_alloc_complex(n);b->product=fftwf_alloc_complex(n);b->corr=fftwf_alloc_complex(n);b->support=calloc(n,sizeof(*b->support));b->ranking=malloc(n*sizeof(*b->ranking));b->rank_scratch=malloc(n*sizeof(*b->rank_scratch));for(int m=0;m<METHODS;m++){b->reference_fft[m]=fftwf_alloc_complex(n);b->scores[m]=calloc(n,sizeof(*b->scores[m]));}if(!b->time||!b->freq||!b->product||!b->corr||!b->support||!b->ranking||!b->rank_scratch)return -1;b->forward=fftwf_plan_dft_1d((int)n,b->time,b->freq,FFTW_FORWARD,FFTW_ESTIMATE);b->backward=fftwf_plan_dft_1d((int)n,b->product,b->corr,FFTW_BACKWARD,FFTW_ESTIMATE);if(!b->forward||!b->backward)return -1;
    for(int m=0;m<LAG_COUNT;m++){int lag=lags[m];for(size_t k=0;k<n;k++){size_t q=(k+lag)%n;float ar=t[q][0],ai=t[q][1],br=t[k][0],bi=t[k][1];b->time[k][0]=ar*br+ai*bi;b->time[k][1]=ai*br-ar*bi;}center_norm(b->time,n,&b->reference_norm[m]);fftwf_execute(b->forward);memcpy(b->reference_fft[m],b->freq,n*sizeof(*b->freq));}
    for(size_t k=0;k<n;k++){b->time[k][0]=power(t[k][0],t[k][1]);b->time[k][1]=0;}center_norm(b->time,n,&b->reference_norm[3]);fftwf_execute(b->forward);memcpy(b->reference_fft[3],b->freq,n*sizeof(*b->freq));return 0;}
static void bank_free(bank *b){if(b->forward)fftwf_destroy_plan(b->forward);if(b->backward)fftwf_destroy_plan(b->backward);for(int m=0;m<METHODS;m++){fftwf_free(b->reference_fft[m]);free(b->scores[m]);}free(b->ranking);free(b->rank_scratch);free(b->support);fftwf_free(b->corr);fftwf_free(b->product);fftwf_free(b->freq);fftwf_free(b->time);}
static void correlate(bank *b,float *score,int method){float onorm;center_norm(b->time,b->n,&onorm);if(!(onorm>FLT_MIN)||!(b->reference_norm[method]>FLT_MIN)){memset(score,0,b->n*sizeof(*score));return;}fftwf_execute(b->forward);for(size_t k=0;k<b->n;k++){float ar=b->freq[k][0],ai=b->freq[k][1],br=b->reference_fft[method][k][0],bi=b->reference_fft[method][k][1];b->product[k][0]=ar*br+ai*bi;b->product[k][1]=ai*br-ar*bi;}fftwf_execute(b->backward);float scale=1.0f/((float)b->n*onorm*b->reference_norm[method]);for(size_t k=0;k<b->n;k++)score[k]=method<3?hypotf(b->corr[k][0],b->corr[k][1])*scale:b->corr[k][0]*scale;}
/* Stable float sorting. Input indices are ascending; ties retain that order.
 * Finite scores only. Both signed zeros share a key, matching the comparator. */
static uint32_t score_key(float value) {
    uint32_t bits; if(value==0) value=0;
    memcpy(&bits,&value,sizeof(bits));
    return bits&0x80000000u ? ~bits : bits^0x80000000u;
}
static void rank_radix(ranked *data, ranked *scratch, size_t n) {
    ranked *src=data,*dst=scratch;
    for(unsigned shift=0;shift<32;shift+=8) {
        size_t counts[256]={0},positions[256],sum=0;
        for(size_t i=0;i<n;i++)++counts[(score_key(src[i].score)>>shift)&255];
        for(unsigned k=0;k<256;k++){positions[k]=sum;sum+=counts[k];}
        for(size_t i=0;i<n;i++)dst[positions[(score_key(src[i].score)>>shift)&255]++]=src[i];
        ranked *tmp=src;src=dst;dst=tmp;
    }
}

static int descending(const void *a,const void *b){const ranked *x=a,*y=b;if(x->score>y->score)return -1;if(x->score<y->score)return 1;return (x->index>y->index)-(x->index<y->index);}
static int peaks(const float *s,size_t n,int out[TOP],ranked *workspace){size_t candidates=0;for(size_t k=0;k<n;k++){size_t left=k?k-1:n-1,right=k+1==n?0:k+1;if(s[k]>0&&s[k]>=s[left]&&s[k]>=s[right]&&(s[k]>s[left]||s[k]>s[right]))workspace[candidates++]=(ranked){s[k],(int)k};}qsort(workspace,candidates,sizeof(*workspace),descending);int used=0;for(size_t q=0;q<candidates&&used<TOP;q++){int v=workspace[q].index,near=0;for(int j=0;j<used;j++){int d=abs(v-out[j]);if(d>(int)n-d)d=(int)n-d;if(d<5){near=1;break;}}if(!near)out[used++]=v;}return used;}
static int top4_linear(const float *s,size_t n,int out[4]){int used=0;while(used<4){int best=-1;for(size_t k=0;k<n;k++){size_t left=k?k-1:n-1,right=k+1==n?0:k+1;if(!(s[k]>0&&s[k]>=s[left]&&s[k]>=s[right]&&(s[k]>s[left]||s[k]>s[right])))continue;int near=0;for(int j=0;j<used;j++){int d=abs((int)k-out[j]);if(d>(int)n-d)d=(int)n-d;if(d<5){near=1;break;}}if(!near&&(best<0||s[k]>s[best]||(s[k]==s[best]&&(int)k<best)))best=(int)k;}if(best<0)break;out[used++]=best;}return used;}
static void emit_ints(const char *name,const int *x,int n){printf("\"%s\":[",name);for(int k=0;k<n;k++)printf("%s%d",k?",":"",x[k]);putchar(']');}

static void fold_scalar(fftwf_complex *time,int *support,const int16_t *raw,
    size_t start,size_t off,size_t valid,int rx,int lag)
{
    for(size_t k=0;k<valid;k++) {
        size_t a=4*(start+off+k)+2*(size_t)rx;
        float ar=(float)raw[a],ai=(float)raw[a+1];
        if(lag) {
            size_t q=a+4*(size_t)lag;
            float qr=(float)raw[q],qi=(float)raw[q+1];
            float rr=qr*ar, ri=qi*ai, ir=qi*ar, ii=qr*ai;
            time[k][0]+=rr+ri;
            time[k][1]+=ir-ii;
        } else {
            float rr=ar*ar, ii=ai*ai;
            time[k][0]+=rr+ii;
        }
        ++support[k];
    }
}

#ifdef LEO_PROPOSAL_NEON_FOLD
static void fold_neon(fftwf_complex *time,int *support,const int16_t *raw,
    size_t start,size_t off,size_t valid,int rx,int lag)
{
    size_t k=0;
    for(;k+4<=valid;k+=4) {
        const int16_t *at=raw+4*(start+off+k);
        int16x4x4_t deinterleaved=vld4_s16(at);
        float32x4_t ar=vcvtq_f32_s32(vmovl_s16(deinterleaved.val[2*rx]));
        float32x4_t ai=vcvtq_f32_s32(vmovl_s16(deinterleaved.val[2*rx+1]));
        float32x4_t real,imag=vdupq_n_f32(0.0f);
        if(lag) {
            int16x4x4_t delayed=vld4_s16(at+4*(size_t)lag);
            float32x4_t qr=vcvtq_f32_s32(vmovl_s16(delayed.val[2*rx]));
            float32x4_t qi=vcvtq_f32_s32(vmovl_s16(delayed.val[2*rx+1]));
            float32x4_t rr=vmulq_f32(qr,ar),ri=vmulq_f32(qi,ai);
            float32x4_t ir=vmulq_f32(qi,ar),ii=vmulq_f32(qr,ai);
            real=vaddq_f32(rr,ri);
            imag=vsubq_f32(ir,ii);
        } else {
            float32x4_t rr=vmulq_f32(ar,ar),ii=vmulq_f32(ai,ai);
            real=vaddq_f32(rr,ii);
        }
        float32x4x2_t accumulated=vld2q_f32((const float *)(time+k));
        accumulated.val[0]=vaddq_f32(accumulated.val[0],real);
        accumulated.val[1]=vaddq_f32(accumulated.val[1],imag);
        vst2q_f32((float *)(time+k),accumulated);
        int32x4_t counts=vld1q_s32((const int32_t *)(support+k));
        vst1q_s32((int32_t *)(support+k),vaddq_s32(counts,vdupq_n_s32(1)));
    }
    fold_scalar(time+k,support+k,raw,start,off+k,valid-k,rx,lag);
}
#endif

static void fold_selected(fftwf_complex *time,int *support,const int16_t *raw,
    size_t start,size_t off,size_t valid,int rx,int lag)
{
#ifdef LEO_PROPOSAL_NEON_FOLD
    fold_neon(time,support,raw,start,off,valid,rx,lag);
#else
    fold_scalar(time,support,raw,start,off,valid,rx,lag);
#endif
}

static __attribute__((unused)) void run_window(bank *b,const int16_t *raw,size_t start,int rx,int full_scores,int combined_only){size_t n=b->n,count=(size_t)b->rate/50;float **scores=b->scores;int *support=b->support;ranked *ranking=b->ranking;int top[METHODS][TOP],topn[METHODS]={0};double begin=now_ms(),fold_ms=0,corr_ms=0;for(int m=0;m<METHODS;m++)memset(scores[m],0,n*sizeof(*scores[m]));
    for(int m=0;m<4;m++){double stage=now_ms();memset(b->time,0,n*sizeof(*b->time));memset(support,0,n*sizeof(*support));int lag=m<3?lags[m]:0;for(int frame=0;frame<FRAMES;frame++){size_t off=(size_t)llround(frame*b->rate/750.0);if(off>=count)break;size_t available=count-off,valid=available;if(valid>n)valid=n;if(lag)valid=available>(size_t)lag?fmin(valid,available-(size_t)lag):0;fold_selected(b->time,support,raw,start,off,valid,rx,lag);}for(size_t k=0;k<n;k++)if(support[k]){b->time[k][0]/=support[k];b->time[k][1]/=support[k];}fold_ms+=now_ms()-stage;stage=now_ms();correlate(b,scores[m],m);corr_ms+=now_ms()-stage;}
    double rank_begin=now_ms();for(int m=0;m<4;m++){float lo=scores[m][0],hi=lo;for(size_t k=1;k<n;k++){if(scores[m][k]<lo)lo=scores[m][k];if(scores[m][k]>hi)hi=scores[m][k];}if(hi-lo<=16*FLT_EPSILON*fmaxf(fmaxf(fabsf(lo),fabsf(hi)),1.0f))continue;for(size_t k=0;k<n;k++)ranking[k]=(ranked){scores[m][k],(int)k};rank_radix(ranking,b->rank_scratch,n);for(size_t rank=0;rank<n;rank++)scores[4][ranking[rank].index]+=(float)rank/(float)(n-1);}
    if(combined_only)topn[4]=top4_linear(scores[4],n,top[4]);else for(int m=0;m<METHODS;m++)topn[m]=peaks(scores[m],n,top[m],ranking);
    double ranked=now_ms();const char *names[METHODS]={"lag1","lag3","lag5","power","combined"};printf("{\"receiver_id\":%d,\"probe_index\":%zu,\"timings_ms\":{\"fold_and_convert\":%.17g,\"correlation\":%.17g,\"ranking\":%.17g,\"total\":%.17g},",rx,start/((size_t)b->rate/100),fold_ms,corr_ms,ranked-rank_begin,ranked-begin);if(combined_only){printf("\"top4\":{");emit_ints("combined",top[4],topn[4]);putchar('}');}else{printf("\"top32\":{");for(int m=0;m<METHODS;m++){if(m)putchar(',');emit_ints(names[m],top[m],topn[m]);}putchar('}');}if(full_scores){printf(",\"scores\":{");for(int m=0;m<METHODS;m++){if(m)putchar(',');printf("\"%s\":[",names[m]);for(size_t k=0;k<n;k++)printf("%s%.17g",k?",":"",scores[m][k]);putchar(']');}putchar('}');}puts("}");}
#ifdef LEO_PROPOSAL_LIBRARY
struct leo_proposal_workspace { bank value; };
leo_proposal_workspace *leo_proposal_create(const double (*input)[2],size_t n,double rate){
    leo_proposal_workspace *w=calloc(1,sizeof(*w)); fftwf_complex *t=fftwf_alloc_complex(n);
    if(!w||!t){free(w);fftwf_free(t);return NULL;}
    for(size_t k=0;k<n;k++){t[k][0]=(float)input[k][0];t[k][1]=(float)input[k][1];}
    if(bank_init(&w->value,t,n,rate)){fftwf_free(t);free(w);return NULL;}
    fftwf_free(t); return w;
}
void leo_proposal_destroy(leo_proposal_workspace *w){if(w){bank_free(&w->value);free(w);}}
int leo_proposal_top4(leo_proposal_workspace *w,const int16_t *raw,size_t start,int rx,
    int centers[4],int *center_count,leo_proposal_timing *timing){
    if(!w||!raw||!centers||!center_count||!timing||rx<0||rx>1)return -1;
    bank *b=&w->value;size_t n=b->n,count=(size_t)b->rate/50;double begin=now_ms(),fold_ms=0,corr_ms=0;
    for(int m=0;m<METHODS;m++)memset(b->scores[m],0,n*sizeof(*b->scores[m]));
    for(int m=0;m<4;m++){double stage=now_ms();memset(b->time,0,n*sizeof(*b->time));memset(b->support,0,n*sizeof(*b->support));int lag=m<3?lags[m]:0;
        for(int frame=0;frame<FRAMES;frame++){size_t off=(size_t)llround(frame*b->rate/750.0);if(off>=count)break;size_t available=count-off,valid=available;if(valid>n)valid=n;if(lag)valid=available>(size_t)lag?fmin(valid,available-(size_t)lag):0;fold_selected(b->time,b->support,raw,start,off,valid,rx,lag);}
        for(size_t k=0;k<n;k++)if(b->support[k]){b->time[k][0]/=b->support[k];b->time[k][1]/=b->support[k];}
        fold_ms+=now_ms()-stage;stage=now_ms();correlate(b,b->scores[m],m);corr_ms+=now_ms()-stage;}
    double rank_begin=now_ms();for(int m=0;m<4;m++){float lo=b->scores[m][0],hi=lo;for(size_t k=1;k<n;k++){if(b->scores[m][k]<lo)lo=b->scores[m][k];if(b->scores[m][k]>hi)hi=b->scores[m][k];}if(hi-lo<=16*FLT_EPSILON*fmaxf(fmaxf(fabsf(lo),fabsf(hi)),1.0f))continue;for(size_t k=0;k<n;k++)b->ranking[k]=(ranked){b->scores[m][k],(int)k};rank_radix(b->ranking,b->rank_scratch,n);for(size_t rank=0;rank<n;rank++)b->scores[4][b->ranking[rank].index]+=(float)rank/(float)(n-1);}
    *center_count=top4_linear(b->scores[4],n,centers);double end=now_ms();*timing=(leo_proposal_timing){fold_ms,corr_ms,end-rank_begin,end-begin};return 0;
}
#else
int main(int argc,char **argv){
#ifdef LEO_LAG_ARM_AFFINITY
    cpu_set_t set;CPU_ZERO(&set);CPU_SET(0,&set);if(sched_setaffinity(0,sizeof(set),&set))return 6;
#endif
    int full=argc==5&&!strcmp(argv[4],"--scores"),combined=argc==5&&!strcmp(argv[4],"--combined-only");if(argc!=4&&!full&&!combined)return 2;char *end;errno=0;double rate=strtod(argv[1],&end);if(errno||*end||(rate!=2500000&&rate!=5000000&&rate!=7500000&&rate!=10000000))return 2;size_t n=(size_t)llround(rate/750.0),dwell=(size_t)rate*120/1000;double (*input)[2]=malloc(n*sizeof(*input));fftwf_complex *t=fftwf_alloc_complex(n);int16_t *raw=malloc(dwell*4*sizeof(*raw));if(!input||!t||!raw||read_exact(argv[2],input,n*sizeof(*input))||read_exact(argv[3],raw,dwell*4*sizeof(*raw)))return 3;for(size_t k=0;k<n;k++){t[k][0]=(float)input[k][0];t[k][1]=(float)input[k][1];}free(input);bank b;if(bank_init(&b,t,n,rate))return 3;size_t stride=(size_t)rate/100;for(int w=0;w<11;w++)for(int rx=0;rx<2;rx++){run_window(&b,raw,w*stride,rx,full,combined);fflush(stdout);}bank_free(&b);free(raw);fftwf_free(t);return 0;}
#endif
