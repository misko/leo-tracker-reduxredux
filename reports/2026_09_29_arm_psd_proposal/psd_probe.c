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
#ifdef LEO_PSD_ARM_AFFINITY
#include <sched.h>
#endif

enum { NFFT=2048, BINS=11, SEGMENTS=8 };
typedef struct { double rate,cfo[BINS],logf[BINS][NFFT],sqrtf[BINS][NFFT]; } bank_t;

static double cpu_ms(void) { struct timespec t; clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t); return 1e3*t.tv_sec+1e-6*t.tv_nsec; }
static int read_bank(const char *path,double rate,bank_t *b) {
    FILE *f=fopen(path,"rb"); char magic[8]; uint32_t nfft,bins;
    if(!f)return -1;
    int ok=fread(magic,1,8,f)==8&&fread(&nfft,4,1,f)==1&&fread(&bins,4,1,f)==1&&fread(&b->rate,8,1,f)==1
        &&!memcmp(magic,"PSD11V1\0",8)&&nfft==NFFT&&bins==BINS&&b->rate==rate
        &&fread(b->cfo,8,BINS,f)==BINS&&fread(b->logf,8,BINS*NFFT,f)==BINS*NFFT
        &&fread(b->sqrtf,8,BINS*NFFT,f)==BINS*NFFT&&fgetc(f)==EOF;
    fclose(f);return ok?0:-1;
}
static void rank(const double *score,int *order) {
    for(int i=0;i<BINS;i++)order[i]=i;
    for(int i=1;i<BINS;i++){int v=order[i],j=i;while(j&&score[v]>score[order[j-1]]){order[j]=order[j-1];j--;}order[j]=v;}
}
static void emit_array_i(const char *key,const int *x) { printf(",\"%s\":[",key);for(int i=0;i<BINS;i++)printf("%s%d",i?",":"",x[i]);putchar(']'); }
static void emit_array_d(const char *key,const double *x) { printf(",\"%s\":[",key);for(int i=0;i<BINS;i++)printf("%s%.17g",i?",":"",x[i]);putchar(']'); }

static void score_window(const int16_t *raw,size_t start,int rx,const bank_t *b,fftw_complex *in,fftw_complex *out,
                         fftw_plan plan,double *logscore,double *sqrtscore) {
    double psd[NFFT]={0},logv[NFFT],sqrtv[NFFT]; size_t count=(size_t)b->rate/50,last=count-NFFT;
    for(int s=0;s<SEGMENTS;s++){
        size_t off=(size_t)llround((double)s*last/(SEGMENTS-1));double mr=0,mi=0;
        for(int n=0;n<NFFT;n++){size_t at=(start+off+n)*4+rx*2;mr+=raw[at];mi+=raw[at+1];}mr/=NFFT;mi/=NFFT;
        for(int n=0;n<NFFT;n++){size_t at=(start+off+n)*4+rx*2;double w=.5-.5*cos(2*M_PI*n/(NFFT-1));in[n][0]=(raw[at]-mr)*w;in[n][1]=(raw[at+1]-mi)*w;}
        fftw_execute(plan);for(int j=0;j<NFFT;j++){int k=(j+NFFT/2)%NFFT;psd[j]+=out[k][0]*out[k][0]+out[k][1]*out[k][1];}
    }
    double sum=0,peak=0;for(int j=0;j<NFFT;j++){psd[j]/=SEGMENTS;sum+=psd[j];}
    if(!(sum>2.2250738585072014e-308))for(int j=0;j<NFFT;j++)psd[j]=1.0/NFFT;
    else for(int j=0;j<NFFT;j++)psd[j]/=sum;
    for(int j=0;j<NFFT;j++)if(psd[j]>peak)peak=psd[j];
    double floorv=fmax(peak*1e-9,2.2250738585072014e-308),mean=0;
    double logmin=INFINITY,logmax=-INFINITY;
    for(int j=0;j<NFFT;j++){logv[j]=log(fmax(psd[j],floorv));mean+=logv[j];sqrtv[j]=sqrt(psd[j]);if(logv[j]<logmin)logmin=logv[j];if(logv[j]>logmax)logmax=logv[j];}mean/=NFFT;
    double norm=0,snorm=0;for(int j=0;j<NFFT;j++){logv[j]-=mean;norm+=logv[j]*logv[j];snorm+=sqrtv[j]*sqrtv[j];}norm=sqrt(norm);snorm=sqrt(snorm);
    if(logmax-logmin<=16*DBL_EPSILON*fmax(fabs(logmin),1.0)||norm<=DBL_MIN)memset(logv,0,sizeof(logv));else for(int j=0;j<NFFT;j++)logv[j]/=norm;
    if(snorm>2.2250738585072014e-308)for(int j=0;j<NFFT;j++)sqrtv[j]/=snorm;
    for(int i=0;i<BINS;i++){logscore[i]=sqrtscore[i]=0;for(int j=0;j<NFFT;j++){logscore[i]+=b->logf[i][j]*logv[j];sqrtscore[i]+=b->sqrtf[i][j]*sqrtv[j];}}
}
int main(int argc,char **argv) {
#ifdef LEO_PSD_ARM_AFFINITY
    cpu_set_t set;CPU_ZERO(&set);CPU_SET(0,&set);if(sched_setaffinity(0,sizeof(set),&set))return 6;
#endif
    if(argc!=4)return 2;
    char *end;errno=0;double rate=strtod(argv[1],&end);
    if(errno||*end||(rate!=2500000&&rate!=5000000&&rate!=7500000&&rate!=10000000))return 2;
    bank_t *b=malloc(sizeof(*b));if(!b||read_bank(argv[2],rate,b))return 3;
    size_t dwell=(size_t)rate*120/1000,items=dwell*4;FILE *f=fopen(argv[3],"rb");int16_t *raw=malloc(items*sizeof(*raw));
    if(!f||!raw||fread(raw,sizeof(*raw),items,f)!=items||fgetc(f)!=EOF)return 3;
    if(fclose(f))return 3;
    fftw_complex *in=fftw_malloc(sizeof(*in)*NFFT),*out=fftw_malloc(sizeof(*out)*NFFT);if(!in||!out)return 3;
    fftw_plan plan=fftw_plan_dft_1d(NFFT,in,out,FFTW_FORWARD,FFTW_ESTIMATE);if(!plan)return 3;
    size_t stride=(size_t)rate/100;for(int window=0;window<11;window++)for(int rx=0;rx<2;rx++){
        double ls[BINS],ss[BINS],begin=cpu_ms();score_window(raw,window*stride,rx,b,in,out,plan,ls,ss);int lr[BINS],sr[BINS];rank(ls,lr);rank(ss,sr);double elapsed=cpu_ms()-begin;
        printf("{\"receiver_id\":%d,\"probe_index\":%d,\"cpu_ms\":%.17g,\"confidence\":%.17g,\"sqrt_confidence\":%.17g",rx,window,elapsed,ls[lr[0]]-ls[lr[1]],ss[sr[0]]-ss[sr[1]]);
        emit_array_i("ranking",lr);emit_array_i("sqrt_ranking",sr);emit_array_d("scores",ls);emit_array_d("sqrt_scores",ss);puts("}");fflush(stdout);
    }
    fftw_destroy_plan(plan);fftw_free(out);fftw_free(in);free(raw);free(b);return 0;
}
