#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include "proposal_core.c"
static unsigned state=17;
static float sample(void){state=state*1664525u+1013904223u;return (float)((int)(state%65536)-32768)/16.0f;}
int main(void){
    const size_t sizes[]={1,2,3,4,5,15,16,17,3333,4096,8192,16384};
    for(size_t t=0;t<sizeof(sizes)/sizeof(*sizes);t++){
        size_t n=sizes[t];fftwf_complex *a=fftwf_alloc_complex(n),*b=fftwf_alloc_complex(n),*v=fftwf_alloc_complex(n);
        float *s=malloc(n*sizeof(*s));assert(a&&b&&v&&s);
        for(size_t k=0;k<n;k++){a[k][0]=sample();a[k][1]=sample();b[k][0]=sample();b[k][1]=sample();}
        a[0][0]=a[0][1]=0;
        proposal_product(a,b,v,n);
        for(size_t k=0;k<n;k++){
            volatile float ar=a[k][0],ai=a[k][1],br=b[k][0],bi=b[k][1];
            float re=ar*br+ai*bi,im=ai*br-ar*bi;
            assert(v[k][0]==re&&v[k][1]==im);
        }
        for(int method=0;method<4;method++){
            proposal_scores(v,s,n,0x1p-20f,method);
            for(size_t k=0;k<n;k++){
                volatile float re=v[k][0]*0x1p-20f,im=v[k][1]*0x1p-20f;
                float expected=method<3?re*re+im*im:re;assert(s[k]==expected);
            }
        }
        free(s);fftwf_free(v);fftwf_free(b);fftwf_free(a);
    }
    puts("proposal SIMD: zero, normal input range, all grid sizes and vector tails pass");return 0;
}
