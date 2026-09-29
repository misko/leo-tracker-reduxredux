#ifndef LEO_EXPERIMENTAL_FIXED_FFT_H
#define LEO_EXPERIMENTAL_FIXED_FFT_H

/* Experimental, genuine integer 2/3/5 FFT.  Each complex sample is one
 * packed pair of signed 16-bit lanes.  Butterfly products are widened before
 * accumulation.  Every stage divides by its radix, so an N point transform
 * has a known 1/N block scale and cannot grow solely because of the FFT. */
#include <complex.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifndef LEO_FIXED_FFT_BITS
#define LEO_FIXED_FFT_BITS 15
#endif
#if LEO_FIXED_FFT_BITS != 15 && LEO_FIXED_FFT_BITS != 7
#error "LEO_FIXED_FFT_BITS must be 15 or 7"
#endif

typedef uint32_t leo_qcomplex;

typedef struct {
    size_t size;
    int fraction_bits;
    int stages;
    int radices[32];
    size_t stage_sizes[33];
    uint64_t block_scale;
    uint64_t clips;
    leo_qcomplex *roots, *input, *output, *scratch;
} leo_fixed_fft;

static inline int32_t leo_qre(leo_qcomplex z) { return (int16_t)(z & 0xffffu); }
static inline int32_t leo_qim(leo_qcomplex z) { return (int16_t)(z >> 16); }
static inline leo_qcomplex leo_qpack(int32_t re, int32_t im)
{
    return (uint16_t)re | ((uint32_t)(uint16_t)im << 16);
}

static inline int32_t leo_round_divide(int64_t value, int64_t divisor)
{
    return (int32_t)(value >= 0 ? (value + divisor/2)/divisor
                               : -((-value + divisor/2)/divisor));
}

static inline int32_t leo_q15_product_round(int64_t value, int bits)
{
    int64_t bias=(int64_t)1<<(bits-1);
    return (int32_t)(value>=0?(value+bias)>>bits:-((-value+bias)>>bits));
}

/* Keep divisors compile-time constants.  Cortex-A9 has no integer divide and
 * a variable int64 divisor here would add __aeabi_ldivmod to every output. */
static inline int32_t leo_stage_scale(int32_t value,size_t radix)
{
    if(radix==2)return value>=0?(value+1)/2:-((-value+1)/2);
    if(radix==3)return value>=0?(value+1)/3:-((-value+1)/3);
    return value>=0?(value+2)/5:-((-value+2)/5);
}

static inline int32_t leo_qclip(leo_fixed_fft *fft, int32_t value)
{
    if (value > 32767) { ++fft->clips; return 32767; }
    if (value < -32768) { ++fft->clips; return -32768; }
    return value;
}

static inline void leo_packed_complex_product(leo_qcomplex x,leo_qcomplex w,
    int32_t *real_product,int32_t *imag_product)
{
#if defined(__arm__) && defined(__ARM_ARCH) && __ARM_ARCH >= 6
    /* ARM DSP dual-halfword instructions consume packed lanes directly. */
    int32_t re,im;
    __asm__("smusd %0,%1,%2" : "=r"(re) : "r"(x),"r"(w));
    __asm__("smuadx %0,%1,%2" : "=r"(im) : "r"(x),"r"(w));
    *real_product=re; *imag_product=im;
#else
    int32_t xr=leo_qre(x),xi=leo_qim(x),wr=leo_qre(w),wi=leo_qim(w);
    *real_product=xr*wr-xi*wi; *imag_product=xr*wi+xi*wr;
#endif
}

static int leo_fixed_fft_init(leo_fixed_fft *fft, size_t size)
{
    memset(fft, 0, sizeof(*fft));
    if (size < 2 || size > 32768) return -1;
    size_t rest=size; fft->stage_sizes[0]=size;
    while (rest>1) {
        int radix=rest%2==0?2:rest%3==0?3:rest%5==0?5:0;
        if (!radix || fft->stages==(int)(sizeof(fft->radices)/sizeof(*fft->radices))) return -1;
        fft->radices[fft->stages++]=radix;
        rest/=(size_t)radix;
        fft->stage_sizes[fft->stages]=rest;
    }
    fft->size=size; fft->fraction_bits=LEO_FIXED_FFT_BITS; fft->block_scale=size;
    fft->roots=calloc(size,sizeof(*fft->roots));
    fft->input=calloc(size,sizeof(*fft->input));
    fft->output=calloc(size,sizeof(*fft->output));
    fft->scratch=calloc(size,sizeof(*fft->scratch));
    if (!fft->roots || !fft->input || !fft->output || !fft->scratch) return -1;
    const int32_t qscale=1<<fft->fraction_bits;
    for (size_t k=0;k<size;++k) {
        double angle=-6.283185307179586476925286766559*(double)k/(double)size;
        int32_t re=(int32_t)llround(cos(angle)*qscale),im=(int32_t)llround(sin(angle)*qscale);
        if(re>32767)re=32767;
        if(im>32767)im=32767;
        fft->roots[k]=leo_qpack(re,im);
    }
    return 0;
}

static void leo_fixed_fft_free(leo_fixed_fft *fft)
{
    free(fft->roots); free(fft->input); free(fft->output); free(fft->scratch);
    memset(fft,0,sizeof(*fft));
}

static void leo_fixed_transform(leo_fixed_fft *fft,const leo_qcomplex *input,
    size_t stride,int stage,leo_qcomplex *output,leo_qcomplex *scratch)
{
    size_t n=fft->stage_sizes[stage];
    if (n==1) { output[0]=input[0]; return; }
    size_t radix=(size_t)fft->radices[stage],m=fft->stage_sizes[stage+1];
    for(size_t j=0;j<radix;++j)
        leo_fixed_transform(fft,input+j*stride,stride*radix,stage+1,
                            output+j*m,scratch+j*m);
    const int64_t qscale=(int64_t)1<<fft->fraction_bits;
    for(size_t k=0;k<m;++k) for(size_t branch=0;branch<radix;++branch) {
        int64_t ar=(int64_t)leo_qre(output[k])*qscale;
        int64_t ai=(int64_t)leo_qim(output[k])*qscale;
        size_t step=(k+branch*m)*stride,twiddle=step;
        for(size_t j=1;j<radix;++j) {
            int32_t pr,pi;
            leo_packed_complex_product(output[j*m+k],fft->roots[twiddle],&pr,&pi);
            ar+=pr; ai+=pi;
            twiddle+=step; while(twiddle>=fft->size) twiddle-=fft->size;
        }
        int32_t re=leo_stage_scale(leo_q15_product_round(ar,fft->fraction_bits),radix);
        int32_t im=leo_stage_scale(leo_q15_product_round(ai,fft->fraction_bits),radix);
        scratch[branch*m+k]=leo_qpack(leo_qclip(fft,re),leo_qclip(fft,im));
    }
    memcpy(output,scratch,n*sizeof(*output));
}

static void leo_fixed_fft_forward(leo_fixed_fft *fft)
{
    leo_fixed_transform(fft,fft->input,1,0,fft->output,fft->scratch);
}

/* Choose one common scale per transform.  This preserves phase and relative
 * amplitude.  The returned factor converts integer FFT lanes back to the
 * unnormalised floating FFT convention: output * N / input_scale. */
static double leo_fixed_fft_pack(leo_fixed_fft *fft,const double complex *input)
{
    double peak=0;
    for(size_t k=0;k<fft->size;++k) {
        peak=fmax(peak,fabs(creal(input[k]))); peak=fmax(peak,fabs(cimag(input[k])));
    }
    const double qmax=(double)((1<<fft->fraction_bits)-1);
    double scale=peak>0?qmax/peak:1.0;
    for(size_t k=0;k<fft->size;++k) {
        int32_t re=(int32_t)llround(creal(input[k])*scale);
        int32_t im=(int32_t)llround(cimag(input[k])*scale);
        fft->input[k]=leo_qpack(leo_qclip(fft,re),leo_qclip(fft,im));
    }
    return (double)fft->block_scale/scale;
}

#endif
