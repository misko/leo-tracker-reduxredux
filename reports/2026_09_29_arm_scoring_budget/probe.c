/* Oracle-seeded COST DIAGNOSTIC, never a deployable detector. */
#define _GNU_SOURCE
#include "full_search.c"
#include <sched.h>
#include <stdio.h>
#include <ctype.h>

static void *read_exact(const char *path, size_t bytes) {
    FILE *f=fopen(path,"rb"); void *p=malloc(bytes);
    if (!f || !p || fread(p,1,bytes,f)!=bytes || fgetc(f)!=EOF) exit(2);
    fclose(f); return p;
}
int main(int argc, char **argv) {
    if(argc!=6) return 2;
#ifdef LEO_FULL_ARM_AFFINITY
    cpu_set_t set; CPU_ZERO(&set); CPU_SET(0,&set);
    if(sched_setaffinity(0,sizeof(set),&set)) return 3;
#endif
    unsigned rate=(unsigned)strtoul(argv[1],NULL,10);
    if(rate!=2500000 && rate!=5000000 && rate!=7500000 && rate!=10000000) return 2;
    size_t n=(rate+375)/750, count=rate/50, stride=rate/100, dwell=rate*120/1000;
    leo_presence_complex *exact=read_exact(argv[2],n*sizeof(*exact));
    leo_presence_complex *control=read_exact(argv[3],n*sizeof(*control));
    int16_t *iq=read_exact(argv[4],dwell*4*sizeof(*iq));
    FILE *seeds=fopen(argv[5],"r"); if(!seeds) return 2;
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);
    leo_presence_complex *samples=calloc(count,sizeof(*samples));
    if(!w || !samples) return 3;
    double dwell_convert_ms=0;
#ifdef SHARED_DWELL
    double complex *owned_samples=w->samples;
    double complex *converted=malloc(2*dwell*sizeof(*converted));
    if(!converted) return 3;
    double convert_start=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    for(int rx=0;rx<2;++rx) for(size_t k=0;k<dwell;++k)
        converted[rx*dwell+k]=iq[4*k+2*rx]+I*(double)iq[4*k+2*rx+1];
    dwell_convert_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-convert_start;
#endif
    for(int window=0;window<11;++window) for(int rx=0;rx<2;++rx) {
        double begin=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
#ifdef SHARED_DWELL
        w->samples=converted+rx*dwell+(size_t)window*stride;
#else
        for(size_t k=0;k<count;++k) {
            size_t at=((size_t)window*stride+k)*4+rx*2;
#ifdef DIRECT_CI16
            /* CI16 is finite and exactly representable in FP64. Keep the
             * original workspace ownership; avoid the second copy/check. */
            w->samples[k]=iq[at]+I*(double)iq[at+1];
#else
            samples[k]=(leo_presence_complex){iq[at],iq[at+1]};
#endif
        }
#ifndef DIRECT_CI16
        if(ingest(w,samples,count)) return 4;
#endif
#endif
        w->acquisition_first_frame=0;
        w->acquisition_regions[0]=w->acquisition_regions[1]=0;
        double ingest_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-begin;
        for(int rank=0;rank<8;++rank) {
            int sw,sr,sk,epoch; double cfo,score[3];
            if(fscanf(seeds,"%d %d %d %d %lf",&sw,&sr,&sk,&epoch,&cfo)!=5 ||
               sw!=window || sr!=rx || sk!=rank || epoch<0 || epoch>=(int)n ||
               !isfinite(cfo) || fabs(cfo)>400000) return 5;
            begin=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
            if(glrt(w,count,epoch,cfo,0,16,1,score)) return 6;
            double ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-begin;
            printf("{\"window\":%d,\"rx\":%d,\"rank\":%d,\"epoch\":%d,\"cfo\":%.17g,\"exact\":%.17g,\"control\":%.17g,\"tracking_cfo\":%.17g,\"cpu_ms\":%.17g,\"window_ingest_ms\":%.17g,\"dwell_convert_ms\":%.17g}\n",window,rx,rank,epoch,cfo,score[0],score[1],cfo+score[2],ms,ingest_ms,dwell_convert_ms);
        }
    }
    int c; do {c=fgetc(seeds);} while(c!=EOF && isspace(c));
    if(c!=EOF) return 5;
#ifdef SHARED_DWELL
    w->samples=owned_samples; free(converted);
#endif
    fclose(seeds); leo_presence_destroy(w);free(samples);free(iq);free(control);free(exact);
    return 0;
}
