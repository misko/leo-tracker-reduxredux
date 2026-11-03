#pragma GCC push_options
#pragma GCC optimize ("no-prefetch-loop-arrays")
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

static void coarse_fp32_templates(leo_presence_workspace *w)
{
    for (int symbol=0; symbol<12; ++symbol) {
        int local=(int)w->starts[symbol], taps=(int)(w->stops[symbol]-w->starts[symbol]);
        for (int k=0; k<taps; ++k) {
            double complex reference=w->exact[local+k];
            w->float_reference_energy[symbol] += power(reference);
            for (int f=0; f<CFO_COUNT; ++f) {
                double angle=TAU*w->frequencies[f]*k/w->rate;
                double cosine=cos(angle), sine=sin(angle);
                int index=symbol*45*12+12*k+f;
                w->float_reference_real[index]=(float)(creal(reference)*cosine-cimag(reference)*sine);
                w->float_reference_imag[index]=(float)(creal(reference)*sine+cimag(reference)*cosine);
            }
        }
    }
}

static int coarse_frame_index(int slot)
{
    return slot*15/(LEO_PRESENCE_COARSE_FRAMES-1);
}

static int coarse_fp32_add(leo_presence_workspace *w, int symbol, ptrdiff_t position,
    ptrdiff_t epoch)
{
    int taps=(int)(w->stops[symbol]-w->starts[symbol]);
    double received=w->prefix[position+taps]-w->prefix[position];
    if (received<0) received=0;
    double denominator=sqrt(w->float_reference_energy[symbol]*received);
    if (denominator>0) {
        float inverse=(float)(1.0/denominator);
        if (!isfinite(inverse)) return -1;
        coarse_float_add(w->float_samples+2*position,
            w->float_reference_real+symbol*45*12, w->float_reference_imag+symbol*45*12,
            taps,inverse,w->float_accumulated+12*epoch);
    }
    ++w->support[epoch];
    return 0;
}

/* Evaluate a previously unsearched epoch around a sparse coarse proposal.
 * Normalized input/prefixes and immutable templates are already prepared. */
/* Experimental contiguous four-epoch kernel. Each lane retains tap order;
 * inverse norms are scalar FP64-derived values, matching coarse_fp32_add. */
static int coarse_fp32_add4(leo_presence_workspace *w,int symbol,ptrdiff_t position,int epochs[4])
{
    int taps=(int)(w->stops[symbol]-w->starts[symbol]);float inverse[4];
    for(int lane=0;lane<4;lane++){double received=w->prefix[position+lane+taps]-w->prefix[position+lane];if(received<0)received=0;inverse[lane]=(float)(received>0?1.0/sqrt(w->float_reference_energy[symbol]*received):0);if(!isfinite(inverse[lane]))return -1;}
#if defined(__ARM_NEON)
    for(int f=0;f<CFO_COUNT;f++){float32x4_t re=vdupq_n_f32(0),im=re;for(int k=0;k<taps;k++){float32x4x2_t x=vld2q_f32(w->float_samples+2*(position+k));float rr=w->float_reference_real[symbol*45*12+12*k+f],ii=w->float_reference_imag[symbol*45*12+12*k+f];re=vaddq_f32(re,vaddq_f32(vmulq_n_f32(x.val[0],rr),vmulq_n_f32(x.val[1],ii)));im=vaddq_f32(im,vsubq_f32(vmulq_n_f32(x.val[1],rr),vmulq_n_f32(x.val[0],ii)));}float value[4];vst1q_f32(value,coarse_magnitude(re,im));for(int lane=0;lane<4;lane++)w->float_accumulated[12*epochs[lane]+f]+=value[lane]*inverse[lane];}
#else
    for(int f=0;f<CFO_COUNT;f++)for(int lane=0;lane<4;lane++){float re=0,im=0;for(int k=0;k<taps;k++){float xr=w->float_samples[2*(position+lane+k)],xi=w->float_samples[2*(position+lane+k)+1],rr=w->float_reference_real[symbol*45*12+12*k+f],ii=w->float_reference_imag[symbol*45*12+12*k+f];re+=xr*rr+xi*ii;im+=xi*rr-xr*ii;}w->float_accumulated[12*epochs[lane]+f]+=sqrtf(re*re+im*im)*inverse[lane];}
#endif
    for(int lane=0;lane<4;lane++)++w->support[epochs[lane]];
    return 0;
}
static int coarse_fp32_cell(leo_presence_workspace *w, size_t count, int epoch)
{
    for (int symbol=0; symbol<12; symbol+=LEO_PRESENCE_ANCHOR_STRIDE) {
        int taps=(int)(w->stops[symbol]-w->starts[symbol]);
        for (int slot=0; slot<LEO_PRESENCE_COARSE_FRAMES; ++slot) {
            int frame=coarse_frame_index(slot);
            ptrdiff_t position=w->starts[symbol]+w->offsets[frame]+epoch;
            if (position+taps>(ptrdiff_t)count) break;
            if (coarse_fp32_add(w,symbol,position,epoch)) return -1;
        }
    }
    for (int f=0; f<CFO_COUNT; ++f)
        w->grid[f*w->n+epoch]=w->support[epoch]>0 ?
            (double)w->float_accumulated[12*epoch+f]/w->support[epoch] : -INFINITY;
    return 0;
}

static int coarse_fp32(leo_presence_workspace *w, size_t count)
{
    /* CI16 ingestion produces finite integral components in [-32768,32767].
     * For that bounded workload, a fixed divisor removes the max scan while
     * retaining the conversion and FP32 accumulation order below. */
#if LEO_PRESENCE_COARSE_CI16_FIXED_SCALE
    const double scale=32768.0;
#else
    double scale=0;
#endif
    memset(w->float_accumulated, 0, CFO_COUNT*w->n*sizeof(float));
    memset(w->support, 0, w->n*sizeof(int32_t));
#if !LEO_PRESENCE_COARSE_CI16_FIXED_SCALE
    for (size_t k=0; k<count; ++k)
        scale=fmax(scale, fmax(fabs(creal(w->samples[k])), fabs(cimag(w->samples[k]))));
#endif
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
    for (int symbol=0; symbol<12; symbol+=LEO_PRESENCE_ANCHOR_STRIDE) {
        int local=(int)w->starts[symbol], taps=(int)(w->stops[symbol]-w->starts[symbol]);
        for (int slot=0; slot<LEO_PRESENCE_COARSE_FRAMES; ++slot) {
            int frame=coarse_frame_index(slot);
            ptrdiff_t base=local+w->offsets[frame];
            ptrdiff_t valid=(ptrdiff_t)count-taps+1-base;
            if (valid<=0) break;
            if (valid>(ptrdiff_t)w->n) valid=(ptrdiff_t)w->n;
            for (int active=0; active<regional_count;) {
                ptrdiff_t epoch=regional_epochs[active];
                if (epoch>=valid) {++active;continue;}
                if (active+3<regional_count && regional_epochs[active+1]==epoch+1 &&
                    regional_epochs[active+2]==epoch+2 && regional_epochs[active+3]==epoch+3 && epoch+3<valid) {
                    int epochs[4]={(int)epoch,(int)epoch+1,(int)epoch+2,(int)epoch+3};
                    if(coarse_fp32_add4(w,symbol,base+epoch,epochs))return -1;
                    active+=4;continue;
                }
                ptrdiff_t position=base+epoch;
                if (coarse_fp32_add(w,symbol,position,epoch)) return -1;
                ++active;
            }
        }
    }
    for (int f=0; f<CFO_COUNT; ++f)
        for (size_t epoch=0; epoch<w->n; ++epoch)
            w->grid[f*w->n+epoch]=w->support[epoch]>0 ?
                (double)w->float_accumulated[12*epoch+f]/w->support[epoch] : -INFINITY;
    return 0;
}

#pragma GCC pop_options
