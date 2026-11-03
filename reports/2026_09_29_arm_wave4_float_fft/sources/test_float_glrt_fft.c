static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static uint32_t state=0x17c8a42du;
static double random_value(void){state=1664525u*state+1013904223u;return ((state>>8)*0x1p-24-.5)*65536.0;}

static void check_fft(leo_presence_workspace *w,leo_fft *fft,size_t n,int final)
{
    double complex *source=calloc(n,sizeof(*source)),*expected=calloc(n,sizeof(*expected));assert(source&&expected);
    for(size_t k=0;k<n;++k)source[k]=(k&1?-32768.0:random_value())+I*(k&2?32767.0:random_value());
    leo_fft_forward(fft,source);memcpy(expected,fft->output,n*sizeof(*expected));
    assert(!glrt_float_fft_forward(w,fft,source,n,final));
    double maximum=0,scale=0;int refbest=0,gotbest=0;
    for(size_t k=0;k<n;++k){maximum=fmax(maximum,cabs(fft->output[k]-expected[k]));scale=fmax(scale,cabs(expected[k]));if(cabs(expected[k])>cabs(expected[refbest]))refbest=(int)k;if(cabs(fft->output[k])>cabs(fft->output[gotbest]))gotbest=(int)k;}
    assert(maximum<=2e-5*fmax(1.0,scale));assert(refbest==gotbest);
    free(expected);free(source);
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int r=0;r<4;++r){size_t n=(rates[r]+375)/750;leo_presence_complex *e=calloc(n,sizeof(*e)),*c=calloc(n,sizeof(*c));assert(e&&c);for(size_t k=0;k<n;++k){e[k]=(leo_presence_complex){.25,.25};c[k]=(leo_presence_complex){.25,-.25};}leo_presence_workspace*w=leo_presence_create(rates[r],e,c,n);assert(w);check_fft(w,&w->short_fft,128,0);check_fft(w,&w->glrt_fft,512,1);leo_presence_destroy(w);free(c);free(e);}
    puts("float GLRT FFT passed: 128/512, all rates, extreme inputs, peak-bin and tolerance");
}
