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
#ifndef LEO_PROPOSAL_FRAME_BUDGET
#define LEO_PROPOSAL_FRAME_BUDGET FRAMES
#endif
#ifndef LEO_PROPOSAL_FFT_DIVISOR
#define LEO_PROPOSAL_FFT_DIVISOR 1
#endif
#if LEO_PROPOSAL_FRAME_BUDGET < 1 || LEO_PROPOSAL_FRAME_BUDGET > 16
#error "LEO_PROPOSAL_FRAME_BUDGET must select between one and all original frames"
#endif
static const int lags[LAG_COUNT]={1,3,5};
typedef struct {float score;int index;} ranked;
typedef struct {
    size_t n,fft_n; double rate;
    fftwf_complex *folded,*folded_extra[2],*time,*freq,*product,*corr,*reference_fft[METHODS];
    float reference_norm[METHODS],*scores[METHODS],*resample_fraction;
    size_t *resample_source,frame_offset[FRAMES],valid[METHODS-1][FRAMES];
    uint8_t *support[METHODS-1]; ranked *ranking,*rank_scratch;
    fftwf_plan forward,backward;
} bank;
static size_t next_power2(size_t n){size_t p=1;while(p<n)p<<=1;return p;}
/* Round evenly spaced selections over the original [0,15] proposal frames.
 * This leaves the downstream coarse/final frame configuration untouched. */
static int proposal_frame_selected(int frame){
    if(LEO_PROPOSAL_FRAME_BUDGET==1)return frame==0;
    for(int q=0;q<LEO_PROPOSAL_FRAME_BUDGET;q++)
        if(frame==(q*(FRAMES-1)+(LEO_PROPOSAL_FRAME_BUDGET-1)/2)/(LEO_PROPOSAL_FRAME_BUDGET-1))return 1;
    return 0;
}
static size_t map_fft_index(size_t k,size_t n,size_t fft_n){return (k*n+fft_n/2)/fft_n%n;}
static void resample_periodic(const bank *b,const fftwf_complex *src,fftwf_complex *dst){
    for(size_t k=0;k<b->fft_n;k++){size_t q=b->resample_source[k],next=q+1==b->n?0:q+1;float f=b->resample_fraction[k];dst[k][0]=src[q][0]+f*(src[next][0]-src[q][0]);dst[k][1]=src[q][1]+f*(src[next][1]-src[q][1]);}
}
static double now_ms(void){struct timespec t;clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return 1e3*t.tv_sec+1e-6*t.tv_nsec;}
static float power(float r,float i){return r*r+i*i;}
static __attribute__((unused)) int read_exact(const char *path,void *data,size_t size){FILE *f=fopen(path,"rb");if(!f)return -1;int ok=fread(data,1,size,f)==size&&fgetc(f)==EOF;fclose(f);return ok?0:-1;}
static void center_norm(fftwf_complex *x,size_t n,float *norm){float mr=0,mi=0;for(size_t k=0;k<n;k++){mr+=x[k][0];mi+=x[k][1];}mr/=n;mi/=n;float e=0;for(size_t k=0;k<n;k++){x[k][0]-=mr;x[k][1]-=mi;e+=power(x[k][0],x[k][1]);}*norm=sqrtf(e);}
static int bank_init(bank *b,const fftwf_complex *t,size_t n,double rate){memset(b,0,sizeof(*b));b->n=n;b->fft_n=next_power2(n)/LEO_PROPOSAL_FFT_DIVISOR;b->rate=rate;size_t z=b->fft_n;b->folded=fftwf_alloc_complex(n);b->folded_extra[0]=fftwf_alloc_complex(n);b->folded_extra[1]=fftwf_alloc_complex(n);b->time=fftwf_alloc_complex(z);b->freq=fftwf_alloc_complex(z);b->product=fftwf_alloc_complex(z);b->corr=fftwf_alloc_complex(z);b->resample_source=malloc(z*sizeof(*b->resample_source));b->resample_fraction=malloc(z*sizeof(*b->resample_fraction));b->ranking=malloc(z*sizeof(*b->ranking));b->rank_scratch=malloc(z*sizeof(*b->rank_scratch));for(int m=0;m<METHODS-1;m++)b->support[m]=calloc(n,sizeof(*b->support[m]));for(int m=0;m<METHODS;m++){b->reference_fft[m]=fftwf_alloc_complex(z);b->scores[m]=calloc(z,sizeof(*b->scores[m]));}if(!b->folded||!b->folded_extra[0]||!b->folded_extra[1]||!b->time||!b->freq||!b->product||!b->corr||!b->resample_source||!b->resample_fraction||!b->support[0]||!b->support[1]||!b->support[2]||!b->support[3]||!b->ranking||!b->rank_scratch)return -1;for(size_t k=0;k<z;k++){size_t scaled=k*n;b->resample_source[k]=scaled/z;b->resample_fraction[k]=(float)(scaled%z)/(float)z;}size_t count=(size_t)rate/50;for(int frame=0;frame<FRAMES;frame++){size_t off=(size_t)llround(frame*rate/750.0);b->frame_offset[frame]=off;if(!proposal_frame_selected(frame))continue;for(int m=0;m<METHODS-1;m++){size_t lag=m<LAG_COUNT?(size_t)lags[m]:0,available=off<count?count-off:0,valid=available<n?available:n;valid=available>lag?(valid<available-lag?valid:available-lag):0;b->valid[m][frame]=valid;for(size_t k=0;k<valid;k++)++b->support[m][k];}}b->forward=fftwf_plan_dft_1d((int)z,b->time,b->freq,FFTW_FORWARD,FFTW_ESTIMATE);b->backward=fftwf_plan_dft_1d((int)z,b->product,b->corr,FFTW_BACKWARD,FFTW_ESTIMATE);if(!b->forward||!b->backward)return -1;
    for(size_t rank=0;rank<z;rank++)b->scores[3][rank]=(float)rank/(float)(z-1);
    for(int m=0;m<LAG_COUNT;m++){int lag=lags[m];for(size_t k=0;k<n;k++){size_t q=(k+lag)%n;float ar=t[q][0],ai=t[q][1],br=t[k][0],bi=t[k][1];b->folded[k][0]=ar*br+ai*bi;b->folded[k][1]=ai*br-ar*bi;}resample_periodic(b,b->folded,b->time);center_norm(b->time,z,&b->reference_norm[m]);fftwf_execute(b->forward);memcpy(b->reference_fft[m],b->freq,z*sizeof(*b->freq));}
#ifndef LEO_PROPOSAL_OMIT_POWER
    for(size_t k=0;k<n;k++){b->folded[k][0]=power(t[k][0],t[k][1]);b->folded[k][1]=0;}resample_periodic(b,b->folded,b->time);center_norm(b->time,z,&b->reference_norm[3]);fftwf_execute(b->forward);memcpy(b->reference_fft[3],b->freq,z*sizeof(*b->freq));
#endif
    return 0;}
static void bank_free(bank *b){if(b->forward)fftwf_destroy_plan(b->forward);if(b->backward)fftwf_destroy_plan(b->backward);for(int m=0;m<METHODS;m++){fftwf_free(b->reference_fft[m]);free(b->scores[m]);}for(int m=0;m<METHODS-1;m++)free(b->support[m]);free(b->resample_source);free(b->resample_fraction);free(b->ranking);free(b->rank_scratch);fftwf_free(b->corr);fftwf_free(b->product);fftwf_free(b->freq);fftwf_free(b->time);fftwf_free(b->folded_extra[0]);fftwf_free(b->folded_extra[1]);fftwf_free(b->folded);}
static float rank_squared_magnitude(float re,float im,float scale){
    float scaled_re=re*scale,scaled_im=im*scale;
    return scaled_re*scaled_re+scaled_im*scaled_im;
}
static int rank_feature_flat(const float *s,size_t n){
    float lo=s[0],hi=lo;for(size_t k=1;k<n;k++){if(s[k]<lo)lo=s[k];if(s[k]>hi)hi=s[k];}
    float magnitude_lo=sqrtf(fmaxf(lo,0.0f)),magnitude_hi=sqrtf(fmaxf(hi,0.0f));
    return magnitude_hi-magnitude_lo<=16*FLT_EPSILON*fmaxf(fmaxf(fabsf(magnitude_lo),fabsf(magnitude_hi)),1.0f);
}
static void correlate(bank *b,float *score,int method){size_t z=b->fft_n;float onorm;center_norm(b->time,z,&onorm);if(!(onorm>FLT_MIN)||!(b->reference_norm[method]>FLT_MIN)){memset(score,0,z*sizeof(*score));return;}fftwf_execute(b->forward);for(size_t k=0;k<z;k++){float ar=b->freq[k][0],ai=b->freq[k][1],br=b->reference_fft[method][k][0],bi=b->reference_fft[method][k][1];b->product[k][0]=ar*br+ai*bi;b->product[k][1]=ai*br-ar*bi;}fftwf_execute(b->backward);float scale=1.0f/((float)z*onorm*b->reference_norm[method]);for(size_t k=0;k<z;k++)score[k]=method<3?rank_squared_magnitude(b->corr[k][0],b->corr[k][1],scale):b->corr[k][0]*scale;}
/* Stable float sorting. Input indices are ascending; ties retain that order.
 * Finite scores only. Both signed zeros share a key, matching the comparator. */
static uint32_t score_key(float value) {
    uint32_t bits;memcpy(&bits,&value,sizeof(bits));
    if((bits&0x7fffffffu)==0)bits=0;
    return bits&0x80000000u ? ~bits : bits^0x80000000u;
}
static uint32_t score_key_reference(float value) {
    uint32_t bits; if(value==0) value=0;
    memcpy(&bits,&value,sizeof(bits));
    return bits&0x80000000u ? ~bits : bits^0x80000000u;
}
static __attribute__((unused)) ranked *rank_radix_reference(ranked *data, ranked *scratch, size_t n) {
    ranked *src=data,*dst=scratch;uint32_t positions[2048];
    static const unsigned shifts[3]={0,11,22},bits[3]={11,11,10};
    for(unsigned pass=0;pass<3;pass++){
        unsigned buckets=1u<<bits[pass],mask=buckets-1;uint32_t sum=0;
        memset(positions,0,buckets*sizeof(*positions));
        for(size_t i=0;i<n;i++)++positions[(score_key_reference(src[i].score)>>shifts[pass])&mask];
        for(unsigned k=0;k<buckets;k++){uint32_t count=positions[k];positions[k]=sum;sum+=count;}
        for(size_t i=0;i<n;i++)dst[positions[(score_key_reference(src[i].score)>>shifts[pass])&mask]++]=src[i];
        ranked *tmp=src;src=dst;dst=tmp;
    }
    return src;
}
/* A permutation leaves every digit histogram unchanged. */
static ranked *rank_radix(ranked *data,ranked *scratch,size_t n){
    uint32_t positions[5120]={0};
    uint32_t *p0=positions,*p1=positions+2048,*p2=positions+4096;
    for(size_t i=0;i<n;i++){
        uint32_t key=score_key(data[i].score);
        ++p0[key&2047];++p1[(key>>11)&2047];++p2[key>>22];
    }
    uint32_t sum0=0,sum1=0,sum2=0;
    for(unsigned k=0;k<2048;k++){
        uint32_t c0=p0[k],c1=p1[k];p0[k]=sum0;p1[k]=sum1;sum0+=c0;sum1+=c1;
    }
    for(unsigned k=0;k<1024;k++){uint32_t count=p2[k];p2[k]=sum2;sum2+=count;}
    for(size_t i=0;i<n;i++)scratch[p0[score_key(data[i].score)&2047]++]=data[i];
    for(size_t i=0;i<n;i++)data[p1[(score_key(scratch[i].score)>>11)&2047]++]=scratch[i];
    for(size_t i=0;i<n;i++)scratch[p2[score_key(data[i].score)>>22]++]=data[i];
    return scratch;
}

static int descending(const void *a,const void *b){const ranked *x=a,*y=b;if(x->score>y->score)return -1;if(x->score<y->score)return 1;return (x->index>y->index)-(x->index<y->index);}
static int peaks(const float *s,size_t fft_n,size_t n,int out[TOP],ranked *workspace){size_t candidates=0;for(size_t k=0;k<fft_n;k++){size_t left=k?k-1:fft_n-1,right=k+1==fft_n?0:k+1;if(s[k]>0&&s[k]>=s[left]&&s[k]>=s[right]&&(s[k]>s[left]||s[k]>s[right]))workspace[candidates++]=(ranked){s[k],(int)k};}qsort(workspace,candidates,sizeof(*workspace),descending);int used=0;for(size_t q=0;q<candidates&&used<TOP;q++){int v=(int)map_fft_index((size_t)workspace[q].index,n,fft_n),near=0;for(int j=0;j<used;j++){int d=abs(v-out[j]);if(d>(int)n-d)d=(int)n-d;if(d<5){near=1;break;}}if(!near)out[used++]=v;}return used;}
static __attribute__((unused)) int top4_sort_reference(const float *s,size_t fft_n,size_t n,int out[4],ranked *workspace){int all[TOP],used=peaks(s,fft_n,n,all,workspace);if(used>4)used=4;for(int k=0;k<used;k++)out[k]=all[k];return used;}
static int top4_linear(const float *s,size_t fft_n,size_t n,int out[4],ranked *workspace){(void)workspace;int used=0;for(int pass=0;pass<4;pass++){int best=-1;for(size_t k=0;k<fft_n;k++){size_t left=k?k-1:fft_n-1,right=k+1==fft_n?0:k+1;if(!(s[k]>0&&s[k]>=s[left]&&s[k]>=s[right]&&(s[k]>s[left]||s[k]>s[right])))continue;if(best>=0&&s[k]<=s[best])continue;int v=(int)map_fft_index(k,n,fft_n),near=0;for(int j=0;j<used;j++){int d=abs(v-out[j]);if(d>(int)n-d)d=(int)n-d;if(d<5){near=1;break;}}if(near)continue;if(best<0||s[k]>s[best]||(s[k]==s[best]&&k<(size_t)best))best=(int)k;}if(best<0)break;out[used++]=(int)map_fft_index((size_t)best,n,fft_n);}return used;}
static void emit_ints(const char *name,const int *x,int n){printf("\"%s\":[",name);for(int k=0;k<n;k++)printf("%s%d",k?",":"",x[k]);putchar(']');}

static void fold_scalar(fftwf_complex *time,const int16_t *raw,
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
    }
}

#ifdef LEO_PROPOSAL_NEON_FOLD
static void fold_neon(fftwf_complex *time,const int16_t *raw,
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
    }
    fold_scalar(time+k,raw,start,off+k,valid-k,rx,lag);
}
#endif

static void fold_selected(fftwf_complex *time,const int16_t *raw,
    size_t start,size_t off,size_t valid,int rx,int lag)
{
#ifdef LEO_PROPOSAL_NEON_FOLD
    fold_neon(time,raw,start,off,valid,rx,lag);
#else
    fold_scalar(time,raw,start,off,valid,rx,lag);
#endif
}

/* Frame-major fused lag pass: each lag keeps its original frame then sample
 * accumulation order, while the common base sample is decoded once. */
static __attribute__((unused)) void fold_three_scalar(fftwf_complex *out[3],const int16_t *raw,size_t start,
    size_t off,size_t valid[3],int rx)
{
    size_t limit=valid[0];if(valid[1]>limit)limit=valid[1];if(valid[2]>limit)limit=valid[2];
    for(size_t k=0;k<limit;k++){size_t a=4*(start+off+k)+2*(size_t)rx;float ar=raw[a],ai=raw[a+1];
        for(int m=0;m<3;m++)if(k<valid[m]){size_t q=a+4*(size_t)lags[m];float qr=raw[q],qi=raw[q+1];
            out[m][k][0]+=qr*ar+qi*ai;out[m][k][1]+=qi*ar-qr*ai;}}
}

#ifdef LEO_PROPOSAL_NEON_FOLD
static void fold_three_neon(fftwf_complex *out[3],const int16_t *raw,size_t start,
    size_t off,size_t valid[3],int rx)
{
    size_t common=valid[0];
    if(valid[1]<common)common=valid[1];
    if(valid[2]<common)common=valid[2];
    size_t k=0;
    for(;k+4<=common;k+=4) {
        const int16_t *at=raw+4*(start+off+k);
        int16x4x4_t base=vld4_s16(at);
        float32x4_t ar=vcvtq_f32_s32(vmovl_s16(base.val[2*rx]));
        float32x4_t ai=vcvtq_f32_s32(vmovl_s16(base.val[2*rx+1]));
        for(int m=0;m<3;m++) {
            int16x4x4_t delayed=vld4_s16(at+4*(size_t)lags[m]);
            float32x4_t qr=vcvtq_f32_s32(vmovl_s16(delayed.val[2*rx]));
            float32x4_t qi=vcvtq_f32_s32(vmovl_s16(delayed.val[2*rx+1]));
            float32x4_t rr=vmulq_f32(qr,ar),ri=vmulq_f32(qi,ai);
            float32x4_t ir=vmulq_f32(qi,ar),ii=vmulq_f32(qr,ai);
            float32x4x2_t accumulated=vld2q_f32((const float *)(out[m]+k));
            accumulated.val[0]=vaddq_f32(accumulated.val[0],vaddq_f32(rr,ri));
            accumulated.val[1]=vaddq_f32(accumulated.val[1],vsubq_f32(ir,ii));
            vst2q_f32((float *)(out[m]+k),accumulated);
        }
    }
    /* Let each lag use its established vector/tail path after the shared part. */
    for(int m=0;m<3;m++)fold_neon(out[m]+k,raw,start,off+k,valid[m]-k,rx,lags[m]);
}
#endif

static void fold_three(fftwf_complex *out[3],const int16_t *raw,size_t start,
    size_t off,size_t valid[3],int rx)
{
#ifdef LEO_PROPOSAL_NEON_FOLD
    fold_three_neon(out,raw,start,off,valid,rx);
#else
    fold_three_scalar(out,raw,start,off,valid,rx);
#endif
}

static __attribute__((unused)) void run_window(bank *b,const int16_t *raw,size_t start,int rx,int full_scores,int combined_only){size_t n=b->n,z=b->fft_n;float **scores=b->scores;ranked *ranking=b->ranking;int top[METHODS][TOP],topn[METHODS]={0};double begin=now_ms(),fold_ms=0,corr_ms=0;for(int m=0;m<METHODS;m++)memset(scores[m],0,z*sizeof(*scores[m]));
    for(int m=0;m<4;m++){double stage=now_ms();memset(b->folded,0,n*sizeof(*b->folded));int lag=m<3?lags[m]:0;for(int frame=0;frame<FRAMES;frame++)if(proposal_frame_selected(frame))fold_selected(b->folded,raw,start,b->frame_offset[frame],b->valid[m][frame],rx,lag);for(size_t k=0;k<n;k++)if(b->support[m][k]){b->folded[k][0]/=b->support[m][k];b->folded[k][1]/=b->support[m][k];}resample_periodic(b,b->folded,b->time);fold_ms+=now_ms()-stage;stage=now_ms();correlate(b,scores[m],m);corr_ms+=now_ms()-stage;}
    double rank_begin=now_ms();for(int m=0;m<4;m++){if(rank_feature_flat(scores[m],z))continue;for(size_t k=0;k<z;k++)ranking[k]=(ranked){scores[m][k],(int)k};ranked *ordered=rank_radix(ranking,b->rank_scratch,z);for(size_t rank=0;rank<z;rank++)scores[4][ordered[rank].index]+=(float)rank/(float)(z-1);}
    if(combined_only)topn[4]=top4_linear(scores[4],z,n,top[4],ranking);else for(int m=0;m<METHODS;m++)topn[m]=peaks(scores[m],z,n,top[m],ranking);
    double ranked=now_ms();const char *names[METHODS]={"lag1","lag3","lag5","power","combined"};printf("{\"receiver_id\":%d,\"probe_index\":%zu,\"proposal_transform\":\"periodic-linear-power2\",\"proposal_original_length\":%zu,\"proposal_fft_length\":%zu,\"proposal_resample_factor\":%.9g,\"proposal_peak_grid\":\"original-round\",\"proposal_min_peak_distance\":5,\"timings_ms\":{\"fold_and_convert\":%.17g,\"correlation\":%.17g,\"ranking\":%.17g,\"total\":%.17g},",rx,start/((size_t)b->rate/100),n,z,(double)z/(double)n,fold_ms,corr_ms,ranked-rank_begin,ranked-begin);if(combined_only){printf("\"top4\":{");emit_ints("combined",top[4],topn[4]);putchar('}');}else{printf("\"top32\":{");for(int m=0;m<METHODS;m++){if(m)putchar(',');emit_ints(names[m],top[m],topn[m]);}putchar('}');}if(full_scores){printf(",\"scores\":{");for(int m=0;m<METHODS;m++){if(m)putchar(',');printf("\"%s\":[",names[m]);for(size_t k=0;k<z;k++)printf("%s%.17g",k?",":"",scores[m][k]);putchar(']');}putchar('}');}puts("}");}
#ifdef LEO_PROPOSAL_LIBRARY
struct leo_proposal_workspace { bank bank; };

leo_proposal_workspace *leo_proposal_create(const double (*input)[2],size_t n,double rate){
    leo_proposal_workspace *w=calloc(1,sizeof(*w));
    fftwf_complex *t=fftwf_alloc_complex(n);
    if(!w||!t){free(w);fftwf_free(t);return NULL;}
    for(size_t k=0;k<n;k++){t[k][0]=(float)input[k][0];t[k][1]=(float)input[k][1];}
    if(bank_init(&w->bank,t,n,rate)){fftwf_free(t);free(w);return NULL;}
    fftwf_free(t);return w;
}
void leo_proposal_destroy(leo_proposal_workspace *w){if(w){bank_free(&w->bank);free(w);}}
int leo_proposal_top4(leo_proposal_workspace *w,const int16_t *raw,size_t start,int rx,
    int centers[4],int *center_count,leo_proposal_timing *timing){
    if(!w||!raw||!centers||!center_count)return -1;
    bank *b=&w->bank;size_t n=b->n,z=b->fft_n;
    double begin=now_ms(),fold_ms=0,corr_ms=0;
    memset(b->scores[4],0,z*sizeof(*b->scores[4]));
    fftwf_complex *lag_fold[3]={b->folded,b->folded_extra[0],b->folded_extra[1]};
    double fold_stage=now_ms();for(int m=0;m<3;m++)memset(lag_fold[m],0,n*sizeof(*lag_fold[m]));
    for(int frame=0;frame<FRAMES;frame++)if(proposal_frame_selected(frame)){
        size_t valid[3]={b->valid[0][frame],b->valid[1][frame],b->valid[2][frame]};
        fold_three(lag_fold,raw,start,b->frame_offset[frame],valid,rx);
    }
    fold_ms+=now_ms()-fold_stage;
    for(int m=0;m<3;m++){
        double stage=now_ms();b->folded=lag_fold[m];
        for(size_t k=0;k<n;k++)if(b->support[m][k]){b->folded[k][0]/=b->support[m][k];b->folded[k][1]/=b->support[m][k];}
        resample_periodic(b,b->folded,b->time);fold_ms+=now_ms()-stage;
        stage=now_ms();correlate(b,b->scores[m],m);corr_ms+=now_ms()-stage;
    }
    b->folded=lag_fold[0];
    double rank_begin=now_ms();
    for(int m=0;m<3;m++){if(rank_feature_flat(b->scores[m],z))continue;for(size_t k=0;k<z;k++)b->ranking[k]=(ranked){b->scores[m][k],(int)k};ranked *ordered=rank_radix(b->ranking,b->rank_scratch,z);for(size_t rank=0;rank<z;rank++)b->scores[4][ordered[rank].index]+=b->scores[3][rank];}
    *center_count=top4_linear(b->scores[4],z,n,centers,b->ranking);
    double end=now_ms();if(timing)*timing=(leo_proposal_timing){fold_ms,corr_ms,end-rank_begin,end-begin};return 0;
}
#else
int main(int argc,char **argv){
#ifdef LEO_LAG_ARM_AFFINITY
    cpu_set_t set;CPU_ZERO(&set);CPU_SET(0,&set);if(sched_setaffinity(0,sizeof(set),&set))return 6;
#endif
    int full=argc==5&&!strcmp(argv[4],"--scores"),combined=argc==5&&!strcmp(argv[4],"--combined-only");if(argc!=4&&!full&&!combined)return 2;char *end;errno=0;double rate=strtod(argv[1],&end);if(errno||*end||(rate!=2500000&&rate!=5000000&&rate!=7500000&&rate!=10000000))return 2;size_t n=(size_t)llround(rate/750.0),dwell=(size_t)rate*120/1000;double (*input)[2]=malloc(n*sizeof(*input));fftwf_complex *t=fftwf_alloc_complex(n);int16_t *raw=malloc(dwell*4*sizeof(*raw));if(!input||!t||!raw||read_exact(argv[2],input,n*sizeof(*input))||read_exact(argv[3],raw,dwell*4*sizeof(*raw)))return 3;for(size_t k=0;k<n;k++){t[k][0]=(float)input[k][0];t[k][1]=(float)input[k][1];}free(input);bank b;if(bank_init(&b,t,n,rate))return 3;size_t stride=(size_t)rate/100;for(int w=0;w<11;w++)for(int rx=0;rx<2;rx++){run_window(&b,raw,w*stride,rx,full,combined);fflush(stdout);}bank_free(&b);free(raw);fftwf_free(t);return 0;}
#endif
