#include "fixed_fft.h"
#include <assert.h>
#include <stdio.h>

static uint32_t state=1;
static double random_sample(void){state=1664525u*state+1013904223u;return ((state>>8)*0x1p-24-.5)*1.8;}

static void test_widened_products(void)
{
    const int16_t lanes[]={-32768,-32767,32767};
    leo_fixed_fft fft; assert(!leo_fixed_fft_init(&fft,8));
    for(size_t a=0;a<3;++a)for(size_t b=0;b<3;++b)for(size_t k=0;k<8;++k) {
        leo_qcomplex x=leo_qpack(lanes[a],lanes[b]),w=fft.roots[k]; int32_t re,im;
        int64_t expected_re=(int64_t)leo_qre(x)*leo_qre(w)-(int64_t)leo_qim(x)*leo_qim(w);
        int64_t expected_im=(int64_t)leo_qre(x)*leo_qim(w)+(int64_t)leo_qim(x)*leo_qre(w);
        assert(expected_re>=INT32_MIN&&expected_re<=INT32_MAX);
        assert(expected_im>=INT32_MIN&&expected_im<=INT32_MAX);
        leo_packed_complex_product(x,w,&re,&im);
        assert(re==(int32_t)expected_re&&im==(int32_t)expected_im);
    }
    leo_fixed_fft_free(&fft);
}

static void run(size_t n)
{
    leo_fixed_fft fft; assert(!leo_fixed_fft_init(&fft,n));
    double complex *x=calloc(n,sizeof(*x)); assert(x);
    for(size_t k=0;k<n;++k)x[k]=random_sample()+I*random_sample();
    double conversion=leo_fixed_fft_pack(&fft,x); leo_fixed_fft_forward(&fft);
    assert(!fft.clips);
    /* Check selected bins against direct FP64 DFT.  The Q15 bound includes
     * input, twiddle, and per-stage rounding error. */
    for(size_t b=0;b<n;b+=n/7+1) {
        double complex expected=0;
        for(size_t k=0;k<n;++k)expected+=x[k]*cexp(-I*6.2831853071795864769*b*k/n);
        double complex got=conversion*(leo_qre(fft.output[b])+I*leo_qim(fft.output[b]));
        assert(cabs(got-expected)<=0.0035*n);
    }
    free(x); leo_fixed_fft_free(&fft);
}

int main(void)
{
    test_widened_products();
    const size_t sizes[]={2,3,5,30,5000,10000,15000,20000};
    for(size_t i=0;i<sizeof(sizes)/sizeof(*sizes);++i)run(sizes[i]);
    puts("fixed FFT passed: radix 2/3/5, Q15 block scaling, no overflow, all fine lengths");
}
