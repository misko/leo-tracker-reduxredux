/* Experimental FP32 FFTW backend. Planning is outside timed execution. */
#include "fft.h"
#include <fftw3.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    fftwf_complex *input, *output;
    fftwf_plan plan;
} float_fftw_plan;

const char *leo_fft_backend_identity(void) { return fftwf_version; }

void leo_fft_free(leo_fft *fft)
{
    float_fftw_plan *p=fft->backend_plan;
    if (p) {
        if (p->plan) fftwf_destroy_plan(p->plan);
        fftwf_free(p->input); fftwf_free(p->output); free(p);
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
    float_fftw_plan *p=calloc(1,sizeof(*p));
    if (!p) return -1;
    fft->backend_plan=p;
    fft->size=n;
    fft->output=calloc(n,sizeof(*fft->output));
    p->input=fftwf_alloc_complex(n);
    p->output=fftwf_alloc_complex(n);
    if (p->input && p->output)
        p->plan=fftwf_plan_dft_1d((int)n,p->input,p->output,FFTW_FORWARD,FFTW_ESTIMATE);
    if (!fft->output || !p->plan) { leo_fft_free(fft); return -1; }
    return 0;
}

void leo_fft_forward(leo_fft *fft, const double complex *input)
{
    float_fftw_plan *p=fft->backend_plan;
    for (size_t k=0;k<fft->size;++k) p->input[k]=(float complex)input[k];
    fftwf_execute(p->plan);
    for (size_t k=0;k<fft->size;++k) fft->output[k]=(double complex)p->output[k];
}
