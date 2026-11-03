#include "conditioned_czt.h"

#include <fftw3.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define CZT_KERNEL_BINS 64
#define CZT_TAU 6.283185307179586476925286766559

typedef struct {
    size_t n, length;
    double rate;
    fftwf_complex *work, *kernel, *chirp;
    fftwf_plan forward, inverse;
} czt_cache;

static czt_cache cache;
static int cleanup_registered;

static void czt_cleanup(void)
{
    if (cache.forward) fftwf_destroy_plan(cache.forward);
    if (cache.inverse) fftwf_destroy_plan(cache.inverse);
    if (cache.work) fftwf_free(cache.work);
    if (cache.kernel) fftwf_free(cache.kernel);
    if (cache.chirp) fftwf_free(cache.chirp);
    memset(&cache,0,sizeof(cache));
}

static int prepare(size_t n, double rate)
{
    if (cache.n==n && cache.rate==rate) return 0;
    czt_cleanup();
    if (!n || !isfinite(rate) || rate<=0 || n>SIZE_MAX-CZT_KERNEL_BINS+1)
        return -1;
    size_t need=n+CZT_KERNEL_BINS-1, length=1;
    while (length<need) {
        if (length>SIZE_MAX/2) return -1;
        length*=2;
    }
    if (length>(size_t)INT32_MAX) return -1;
    cache.work=fftwf_alloc_complex(length);
    cache.kernel=fftwf_alloc_complex(length);
    cache.chirp=fftwf_alloc_complex(n);
    if (!cache.work || !cache.kernel || !cache.chirp) { czt_cleanup(); return -1; }
    cache.forward=fftwf_plan_dft_1d((int)length,cache.work,cache.work,
        FFTW_FORWARD,FFTW_ESTIMATE);
    cache.inverse=fftwf_plan_dft_1d((int)length,cache.work,cache.work,
        FFTW_BACKWARD,FFTW_ESTIMATE);
    if (!cache.forward || !cache.inverse) { czt_cleanup(); return -1; }
    memset(cache.kernel,0,length*sizeof(*cache.kernel));
    double theta=CZT_TAU*100.0/rate;
    for (size_t k=0;k<n;++k) {
        double phase=-.5*theta*(double)k*(double)k;
        cache.chirp[k][0]=(float)cos(phase);
        cache.chirp[k][1]=(float)sin(phase);
    }
    for (ptrdiff_t d=-(ptrdiff_t)(n-1); d<CZT_KERNEL_BINS; ++d) {
        double phase=.5*theta*(double)d*(double)d;
        size_t q=(size_t)(d+(ptrdiff_t)n-1);
        cache.kernel[q][0]=(float)cos(phase);
        cache.kernel[q][1]=(float)sin(phase);
    }
    fftwf_execute_dft(cache.forward,cache.kernel,cache.kernel);
    cache.n=n; cache.length=length; cache.rate=rate;
    if (!cleanup_registered) { atexit(czt_cleanup); cleanup_registered=1; }
    return 0;
}

int leo_conditioned_czt_magnitudes(const float *weighted, size_t n,
    double rate, int nf, float *magnitudes)
{
    if (!weighted || !magnitudes || nf<1 || nf>CZT_KERNEL_BINS || prepare(n,rate))
        return -1;
    memset(cache.work,0,cache.length*sizeof(*cache.work));
    for (size_t k=0;k<n;++k) {
        float cr=cache.chirp[k][0], ci=cache.chirp[k][1];
        float xr=weighted[2*k], xi=weighted[2*k+1];
        cache.work[k][0]=xr*cr-xi*ci;
        cache.work[k][1]=xr*ci+xi*cr;
    }
    fftwf_execute(cache.forward);
    for (size_t q=0;q<cache.length;++q) {
        float ar=cache.work[q][0], ai=cache.work[q][1];
        float br=cache.kernel[q][0], bi=cache.kernel[q][1];
        cache.work[q][0]=ar*br-ai*bi;
        cache.work[q][1]=ar*bi+ai*br;
    }
    fftwf_execute(cache.inverse);
    float scale=1.0f/(float)cache.length;
    for (int j=0;j<nf;++j) {
        size_t q=n-1+(size_t)j;
        float re=cache.work[q][0]*scale, im=cache.work[q][1]*scale;
        magnitudes[j]=hypotf(re,im);
    }
    return 0;
}
