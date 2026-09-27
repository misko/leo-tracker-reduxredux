/* Experimental FP32 FFT backend: a numerical variant, not bit equivalence.
 * Public research FFT ABI stays FP64; conversion is charged on every call.
 * Plans, roots and all scratch are allocated once, outside streaming compute. */
#include "fft.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    float complex *roots, *input, *output, *scratch;
} fp32_plan;

const char *leo_fft_backend_identity(void) { return "research_fp32_radix2_5_v1"; }

void leo_fft_free(leo_fft *fft)
{
    fp32_plan *p=fft->backend_plan;
    if (p) {
        free(p->roots); free(p->input); free(p->output); free(p->scratch); free(p);
    }
    free(fft->output);
    memset(fft,0,sizeof(*fft));
}

int leo_fft_init(leo_fft *fft, size_t n)
{
    memset(fft,0,sizeof(*fft));
    if (n<2 || n>32768) return -1;
    size_t rest=n;
    while (!(rest%2)) rest/=2;
    while (!(rest%5)) rest/=5;
    if (rest!=1) return -1;
    fp32_plan *p=calloc(1,sizeof(*p));
    if (!p) return -1;
    fft->backend_plan=p;
    fft->size=n;
    fft->output=calloc(n,sizeof(*fft->output));
    p->roots=calloc(n,sizeof(*p->roots));
    p->input=calloc(n,sizeof(*p->input));
    p->output=calloc(n,sizeof(*p->output));
    p->scratch=calloc(n,sizeof(*p->scratch));
    if (!fft->output || !p->roots || !p->input || !p->output || !p->scratch) {
        leo_fft_free(fft); return -1;
    }
    for (size_t k=0;k<n;++k) {
        double angle=-6.283185307179586476925286766559*k/n;
        p->roots[k]=(float)cos(angle)+I*(float)sin(angle);
    }
    return 0;
}

static void recursive(const fp32_plan *p, size_t size, const float complex *input,
    size_t stride, size_t n, float complex *out, float complex *scratch)
{
    if (n==1) { out[0]=input[0]; return; }
    size_t radix=n%2 ? 5 : 2, m=n/radix;
    for (size_t j=0;j<radix;++j)
        recursive(p,size,input+j*stride,stride*radix,m,out+j*m,scratch+j*m);
    if (radix==2) {
        for (size_t k=0;k<m;++k) {
            float complex even=out[k], odd=out[m+k]*p->roots[k*stride];
            scratch[k]=even+odd; scratch[m+k]=even-odd;
        }
    } else {
        for (size_t k=0;k<m;++k) for (size_t branch=0;branch<5;++branch) {
            size_t step=(k+branch*m)*stride, twiddle=step;
            float complex value=out[k];
            for (size_t j=1;j<5;++j) {
                value+=out[j*m+k]*p->roots[twiddle];
                twiddle+=step;
                if (twiddle>=size) twiddle-=size;
            }
            scratch[branch*m+k]=value;
        }
    }
    memcpy(out,scratch,n*sizeof(*out));
}

static void radix2(fp32_plan *p, size_t n)
{
    for (size_t i=0,reversed=0;i<n;++i) {
        p->output[reversed]=p->input[i];
        size_t bit=n>>1;
        while (bit && (reversed&bit)) { reversed^=bit; bit>>=1; }
        reversed^=bit;
    }
    for (size_t width=2,stride=n>>1;width<=n;width<<=1,stride>>=1) {
        size_t half=width>>1;
        for (size_t base=0;base<n;base+=width) for (size_t k=0;k<half;++k) {
            float complex even=p->output[base+k];
            float complex odd=p->output[base+half+k]*p->roots[k*stride];
            p->output[base+k]=even+odd; p->output[base+half+k]=even-odd;
        }
    }
}

void leo_fft_forward(leo_fft *fft, const double complex *input)
{
    fp32_plan *p=fft->backend_plan;
    for (size_t k=0;k<fft->size;++k) p->input[k]=(float complex)input[k];
    if (!(fft->size&(fft->size-1))) radix2(p,fft->size);
    else recursive(p,fft->size,p->input,1,fft->size,p->output,p->scratch);
    for (size_t k=0;k<fft->size;++k) fft->output[k]=(double complex)p->output[k];
}
