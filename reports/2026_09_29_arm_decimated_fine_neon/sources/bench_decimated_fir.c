#define _POSIX_C_SOURCE 200809L
#include "decimated_fir.h"
#include <fftw3.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
static double now(void){struct timespec t;clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return t.tv_sec+1e-9*t.tv_nsec;}
static volatile float sink;
int main(void){const uint32_t rates[]={2500000,5000000,7500000,10000000};for(int q=0;q<4;q++){size_t n=rates[q]/500,m=n/5;float complex*x=fftwf_alloc_complex(n),*d=fftwf_alloc_complex(m),*full=fftwf_alloc_complex(n),*small=fftwf_alloc_complex(m);float h[24];float complex mh[24],step;for(size_t k=0;k<n;k++)x[k]=cos(.013*k)+I*sin(.017*k);leo_decimated_filter(h);leo_decimated_modulate(h,rates[q],80000,mh,&step);fftwf_plan pf=fftwf_plan_dft_1d((int)n,(fftwf_complex*)x,(fftwf_complex*)full,FFTW_FORWARD,FFTW_ESTIMATE),ps=fftwf_plan_dft_1d((int)m,(fftwf_complex*)d,(fftwf_complex*)small,FFTW_FORWARD,FFTW_ESTIMATE);int reps=200;double a=now();for(int r=0;r<reps;r++)fftwf_execute(pf);double full_s=now()-a;a=now();for(int r=0;r<reps;r++){leo_decimate_scalar(x,n,mh,step,d);fftwf_execute(ps);}double scalar_s=now()-a;a=now();for(int r=0;r<reps;r++){leo_decimate_neon(x,n,mh,step,d);fftwf_execute(ps);}double neon_s=now()-a;sink+=crealf(small[rates[q]%m]);printf("{\"rate\":%u,\"repetitions\":%d,\"full_fft_s\":%.9g,\"scalar_decimated_s\":%.9g,\"neon_decimated_s\":%.9g}\n",rates[q],reps,full_s,scalar_s,neon_s);fftwf_destroy_plan(ps);fftwf_destroy_plan(pf);fftwf_free(small);fftwf_free(full);fftwf_free(d);fftwf_free(x);}return sink==12345;}
