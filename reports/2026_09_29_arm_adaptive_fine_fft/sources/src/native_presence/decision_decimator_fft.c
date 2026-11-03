#include "decision_decimator_fft.h"
#include <fftw3.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif
#define FFT_SIZE 1024
#define OUT_SIZE (FFT_SIZE/4)
struct leo_decimator_fft {
    size_t count;
    unsigned prefix;
    fftwf_complex *input, *spectrum, *response, *folded, *output;
    fftwf_plan forward, inverse;
};

void leo_decimator_fft_destroy(leo_decimator_fft *w)
{
    if (!w) return;
    if (w->forward) fftwf_destroy_plan(w->forward);
    if (w->inverse) fftwf_destroy_plan(w->inverse);
    fftwf_free(w->input); fftwf_free(w->spectrum); fftwf_free(w->response);
    fftwf_free(w->folded); fftwf_free(w->output); free(w);
}

leo_decimator_fft *leo_decimator_fft_create(const int16_t *h, unsigned taps, size_t count)
{
    if (!h || !taps || taps>257 || !(taps&1) || !count || count%4 || count>1200000)
        return NULL;
    int sum=0,absolute=0;
    for (unsigned k=0;k<taps;++k) {
        if (h[k]!=h[taps-1-k]) return NULL;
        sum+=h[k]; absolute+=abs(h[k]);
    }
    if (sum!=32768 || absolute>=65536) return NULL;
    leo_decimator_fft *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    w->count=count; w->prefix=((taps-1+3)/4)*4;
    w->input=fftwf_alloc_complex(FFT_SIZE); w->spectrum=fftwf_alloc_complex(FFT_SIZE);
    w->response=fftwf_alloc_complex(FFT_SIZE); w->folded=fftwf_alloc_complex(OUT_SIZE);
    w->output=fftwf_alloc_complex(OUT_SIZE);
    if (!w->input || !w->spectrum || !w->response || !w->folded || !w->output) goto fail;
    w->forward=fftwf_plan_dft_1d(FFT_SIZE,w->input,w->spectrum,FFTW_FORWARD,FFTW_ESTIMATE);
    w->inverse=fftwf_plan_dft_1d(OUT_SIZE,w->folded,w->output,FFTW_BACKWARD,FFTW_ESTIMATE);
    if (!w->forward || !w->inverse) goto fail;
    memset(w->input,0,FFT_SIZE*sizeof(*w->input));
    for (unsigned k=0;k<taps;++k) w->input[k][0]=h[k]/32768.0f;
    fftwf_execute(w->forward);
    for (unsigned k=0;k<FFT_SIZE;++k) for (unsigned c=0;c<2;++c)
        w->response[k][c]=w->spectrum[k][c]/FFT_SIZE;
    return w;
fail:
    leo_decimator_fft_destroy(w); return NULL;
}

int leo_decimator_fft_run(leo_decimator_fft *w, const int16_t *iq, size_t count, int16_t *out)
{
    if (!w || !iq || !out || count!=w->count) return -1;
    for (size_t offset=0;offset<count;offset+=FFT_SIZE-w->prefix) {
        size_t valid=count-offset<FFT_SIZE-w->prefix ? count-offset : FFT_SIZE-w->prefix;
        memset(w->input,0,FFT_SIZE*sizeof(*w->input));
        size_t first=offset<w->prefix ? w->prefix-offset : 0;
        size_t end=w->prefix+valid, k=first;
#if defined(__ARM_NEON)
        for (;k+4<=end;k+=4) {
            int16x8_t x=vld1q_s16(iq+2*(offset+k-w->prefix));
            vst1q_f32(w->input[k],vcvtq_f32_s32(vmovl_s16(vget_low_s16(x))));
            vst1q_f32(w->input[k+2],vcvtq_f32_s32(vmovl_s16(vget_high_s16(x))));
        }
#endif
        for (;k<end;++k) for (unsigned c=0;c<2;++c)
            w->input[k][c]=iq[2*(offset+k-w->prefix)+c];
        fftwf_execute(w->forward);
        /* Folding four spectral bands is exactly time-domain downsampling.
         * Include every band after multiplication by the same FIR response. */
        k=0;
#if defined(__ARM_NEON)
        for (;k+4<=OUT_SIZE;k+=4) {
            float32x4_t re=vdupq_n_f32(0),im=re;
            for (unsigned band=0;band<4;++band) {
                unsigned bin=k+band*OUT_SIZE;
                float32x4x2_t x=vld2q_f32(w->spectrum[bin]);
                float32x4x2_t h=vld2q_f32(w->response[bin]);
                re=vmlaq_f32(re,x.val[0],h.val[0]); re=vmlsq_f32(re,x.val[1],h.val[1]);
                im=vmlaq_f32(im,x.val[0],h.val[1]); im=vmlaq_f32(im,x.val[1],h.val[0]);
            }
            float32x4x2_t y={{re,im}}; vst2q_f32(w->folded[k],y);
        }
#endif
        for (;k<OUT_SIZE;++k) {
            float re=0,im=0;
            for (unsigned band=0;band<4;++band) {
                unsigned bin=k+band*OUT_SIZE;
                float *x=w->spectrum[bin], *h=w->response[bin];
                re+=x[0]*h[0]-x[1]*h[1]; im+=x[0]*h[1]+x[1]*h[0];
            }
            w->folded[k][0]=re; w->folded[k][1]=im;
        }
        fftwf_execute(w->inverse);
        k=0;
#if defined(__ARM_NEON)
        for (;k+2<=valid/4;k+=2) {
            float32x4_t x=vld1q_f32(w->output[w->prefix/4+k]);
            x=vminq_f32(vmaxq_f32(x,vdupq_n_f32(-32768)),vdupq_n_f32(32767));
            x=vaddq_f32(x,vdupq_n_f32(.5f));
            int32x4_t q=vcvtq_s32_f32(x);
            q=vaddq_s32(q,vreinterpretq_s32_u32(vcltq_f32(x,vcvtq_f32_s32(q))));
            vst1_s16(out+offset/2+2*k,vqmovn_s32(q));
        }
#endif
        for (;k<valid/4;++k) for (unsigned c=0;c<2;++c) {
            float x=floorf(w->output[w->prefix/4+k][c]+.5f);
            out[offset/2+2*k+c]=x>32767 ? 32767 : x< -32768 ? -32768 : (int16_t)x;
        }
    }
    return 0;
}
