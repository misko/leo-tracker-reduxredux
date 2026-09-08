/* Separately qualified FP32 coarse-search experiment. Not the FP64 oracle.
 * Included only after the private workspace definition. All hypotheses and
 * support accounting match the full grid; refinement retains original IQ. */
#if defined(__ARM_NEON)
#include <arm_neon.h>

static float32x4_t coarse_magnitude(float32x4_t real, float32x4_t imag)
{
    float32x4_t squared = vaddq_f32(vmulq_f32(real, real), vmulq_f32(imag, imag));
    /* Zero must not take the 0 * infinity path of reciprocal square root. */
    float32x4_t safe = vbslq_f32(vceqq_f32(squared, vdupq_n_f32(0)),
        vdupq_n_f32(1), squared);
    float32x4_t reciprocal = vrsqrteq_f32(safe);
    reciprocal = vmulq_f32(reciprocal,
        vrsqrtsq_f32(vmulq_f32(safe, reciprocal), reciprocal));
    reciprocal = vmulq_f32(reciprocal,
        vrsqrtsq_f32(vmulq_f32(safe, reciprocal), reciprocal));
    return vmulq_f32(squared, reciprocal);
}

static void coarse_float_add(const float *samples, const float *real,
    const float *imag, int taps, float inverse_norm, float *sum)
{
    float32x4_t r0=vdupq_n_f32(0), r1=r0, r2=r0, i0=r0, i1=r0, i2=r0;
    for (int k=0; k<taps; ++k) {
        float32x4_t xr=vdupq_n_f32(samples[2*k]), xi=vdupq_n_f32(samples[2*k+1]);
#define FLOAT_LANE(lane) do { \
    float32x4_t rr=vld1q_f32(real+12*k+4*lane), ri=vld1q_f32(imag+12*k+4*lane); \
    r##lane=vaddq_f32(r##lane, vaddq_f32(vmulq_f32(xr,rr), vmulq_f32(xi,ri))); \
    i##lane=vaddq_f32(i##lane, vsubq_f32(vmulq_f32(xi,rr), vmulq_f32(xr,ri))); \
} while (0)
        FLOAT_LANE(0); FLOAT_LANE(1); FLOAT_LANE(2);
#undef FLOAT_LANE
    }
#define FLOAT_SUM(lane) vst1q_f32(sum+4*lane, vaddq_f32(vld1q_f32(sum+4*lane), \
    vmulq_n_f32(coarse_magnitude(r##lane, i##lane), inverse_norm)))
    FLOAT_SUM(0); FLOAT_SUM(1); FLOAT_SUM(2);
#undef FLOAT_SUM
}
#else
static void coarse_float_add(const float *samples, const float *real,
    const float *imag, int taps, float inverse_norm, float *sum)
{
    float r[12]={0}, i[12]={0};
    for (int k=0; k<taps; ++k)
        for (int f=0; f<12; ++f) {
            r[f] += samples[2*k]*real[12*k+f]+samples[2*k+1]*imag[12*k+f];
            i[f] += samples[2*k+1]*real[12*k+f]-samples[2*k]*imag[12*k+f];
        }
    for (int f=0; f<12; ++f) sum[f] += sqrtf(r[f]*r[f]+i[f]*i[f])*inverse_norm;
}
#endif

static int coarse_fp32(leo_presence_workspace *w, size_t count)
{
    double scale=0;
    memset(w->float_accumulated, 0, CFO_COUNT*w->n*sizeof(float));
    memset(w->support, 0, w->n*sizeof(int32_t));
    for (size_t k=0; k<count; ++k)
        scale=fmax(scale, fmax(fabs(creal(w->samples[k])), fabs(cimag(w->samples[k]))));
    if (scale==0) {
        memset(w->grid, 0, CFO_COUNT*w->n*sizeof(double));
        return 0;
    }
    w->prefix[0]=0;
    for (size_t k=0; k<count; ++k) {
        double real=creal(w->samples[k])/scale, imag=cimag(w->samples[k])/scale;
        w->float_samples[2*k]=(float)real; w->float_samples[2*k+1]=(float)imag;
        w->prefix[k+1]=w->prefix[k]+real*real+imag*imag;
    }
    for (int symbol=0; symbol<12; ++symbol) {
        int local=(int)w->starts[symbol], taps=(int)(w->stops[symbol]-w->starts[symbol]);
        float real[23*12], imag[23*12];
        double energy=0;
        for (int k=0; k<taps; ++k) {
            double complex reference=w->exact[local+k];
            energy += power(reference);
            for (int f=0; f<CFO_COUNT; ++f) {
                double angle=TAU*w->frequencies[f]*k/w->rate;
                double cosine=cos(angle), sine=sin(angle);
                real[12*k+f]=(float)(creal(reference)*cosine-cimag(reference)*sine);
                imag[12*k+f]=(float)(creal(reference)*sine+cimag(reference)*cosine);
            }
        }
        for (int frame=0; frame<16; ++frame) {
            ptrdiff_t base=local+w->offsets[frame];
            ptrdiff_t valid=(ptrdiff_t)count-taps+1-base;
            if (valid<=0) break;
            if (valid>(ptrdiff_t)w->n) valid=(ptrdiff_t)w->n;
            for (ptrdiff_t epoch=0; epoch<valid; ++epoch) {
                ptrdiff_t position=base+epoch;
                double received=fmax(0, w->prefix[position+taps]-w->prefix[position]);
                double denominator=sqrt(energy*received);
                if (denominator>0) {
                    float inverse=(float)(1.0/denominator);
                    /* Unrepresentable normalization is unsupported evidence,
                     * never a successful negative result. */
                    if (!isfinite(inverse)) return -1;
                    coarse_float_add(w->float_samples+2*position, real, imag, taps,
                        inverse, w->float_accumulated+12*epoch);
                }
                ++w->support[epoch];
            }
        }
    }
    for (int f=0; f<CFO_COUNT; ++f)
        for (size_t epoch=0; epoch<w->n; ++epoch)
            w->grid[f*w->n+epoch]=w->support[epoch]>0 ?
                (double)w->float_accumulated[12*epoch+f]/w->support[epoch] : 0;
    return 0;
}
