#include <assert.h>
#include <complex.h>
#include <fftw3.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t state=0x7a091c3du;
static float random_float(void){state=1664525u*state+1013904223u;return ((state>>8)*0x1p-23f-1)*100.0f;}

static void check_size(int n)
{
    fftwf_complex *input=fftwf_alloc_complex((size_t)2*n);
    fftwf_complex *batched=fftwf_alloc_complex((size_t)2*n);
    fftwf_complex *separate=fftwf_alloc_complex((size_t)2*n);assert(input&&batched&&separate);
    for(int k=0;k<2*n;k++)input[k]=random_float()+I*random_float();
    int length=n;
    fftwf_plan batch=fftwf_plan_many_dft(1,&length,2,input,NULL,1,n,batched,NULL,1,n,FFTW_FORWARD,FFTW_ESTIMATE);
    fftwf_plan single=fftwf_plan_dft_1d(n,input,separate,FFTW_FORWARD,FFTW_ESTIMATE);assert(batch&&single);
    fftwf_execute(batch);
    for(int frame=0;frame<2;frame++)fftwf_execute_dft(single,input+(size_t)frame*n,separate+(size_t)frame*n);
    for(int k=0;k<2*n;k++){
        double dr=(double)crealf(batched[k])-crealf(separate[k]);
        double di=(double)cimagf(batched[k])-cimagf(separate[k]);
        double scale=fmax(1.0,cabsf(separate[k]));
        assert(hypot(dr,di)<=2e-5*scale);
    }
    fftwf_destroy_plan(single);fftwf_destroy_plan(batch);fftwf_free(separate);fftwf_free(batched);fftwf_free(input);
}

int main(void)
{
    const int sizes[]={5000,10000,15000,20000};
    for(int k=0;k<4;k++)check_size(sizes[k]);
    puts("batch2 FFT passed: two-frame plan_many parity with separate transforms at all rates");
    return 0;
}
