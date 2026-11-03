#define _POSIX_C_SOURCE 200809L
#include <fftw3.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static double cpu(void) {
    struct timespec ts;if(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&ts))abort();
    return ts.tv_sec+ts.tv_nsec*1e-9;
}
int main(int argc,char **argv) {
    if(argc!=4)return 2;
    const int n=5000,repeats=1024;
    fftwf_complex *in[2],*out[2];fftwf_plan plans[2];
    for(int j=0;j<2;++j) {
        in[j]=fftwf_alloc_complex(n);out[j]=fftwf_alloc_complex(n);
        if(!in[j]||!out[j])return 3;
    }
    fftwf_forget_wisdom();
    plans[0]=fftwf_plan_dft_1d(n,in[0],out[0],FFTW_FORWARD,FFTW_ESTIMATE);
    fftwf_set_timelimit(1.0);
    double begin=cpu();
    plans[1]=fftwf_plan_dft_1d(n,in[1],out[1],FFTW_FORWARD,FFTW_MEASURE);
    double planning=cpu()-begin;
    if(!plans[0]||!plans[1])return 4;
    if(!fftwf_export_wisdom_to_filename(argv[1]))return 5;
    for(int j=0;j<2;++j) {
        FILE *f=fopen(argv[j+2],"w");if(!f)return 5;
        fftwf_fprint_plan(plans[j],f);fclose(f);
    }
    uint32_t seed=918273;
    for(int k=0;k<n;++k)for(int lane=0;lane<2;++lane) {
        seed=seed*1664525u+1013904223u;
        float value=(float)((int)(seed>>16)-32768)/32768.0f;
        in[0][k][lane]=in[1][k][lane]=value;
    }
    fftwf_execute(plans[0]);fftwf_execute(plans[1]);
    double error=0,scale=0;
    for(int k=0;k<n;++k)for(int lane=0;lane<2;++lane) {
        double a=out[0][k][lane],b=out[1][k][lane];
        if(!isfinite(a)||!isfinite(b))return 6;
        if(fabs(a-b)>error)error=fabs(a-b);
        if(fabs(a)>scale)scale=fabs(a);
    }
    printf("{\"planning_cpu_s\":%.17g,\"maximum_absolute_error\":%.17g,\"maximum_control_magnitude\":%.17g}\n",planning,error,scale);
    const int order[4]={0,1,1,0};
    for(int trial=0;trial<4;++trial) {
        int j=order[trial];begin=cpu();
        for(int k=0;k<repeats;++k)fftwf_execute(plans[j]);
        printf("{\"trial\":%d,\"measured_plan\":%s,\"cpu_s\":%.17g,\"repeats\":%d}\n",trial,j?"true":"false",cpu()-begin,repeats);
    }
    for(int j=0;j<2;++j){fftwf_destroy_plan(plans[j]);fftwf_free(in[j]);fftwf_free(out[j]);}
    fftwf_cleanup();return 0;
}
