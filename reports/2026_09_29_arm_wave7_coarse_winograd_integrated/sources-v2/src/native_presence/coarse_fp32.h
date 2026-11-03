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
        for (int chunk=0; chunk<taps/3; ++chunk) for (int f=0; f<CFO_COUNT; ++f) {
            int source=symbol*45*12+chunk*3*12+f;
            float ar=w->float_reference_real[source], ai=-w->float_reference_imag[source];
            float br=w->float_reference_real[source+12], bi=-w->float_reference_imag[source+12];
            float cr=w->float_reference_real[source+24], ci=-w->float_reference_imag[source+24];
            int target=(symbol*15+chunk)*6*12+f;
#define STORE_G(point,real,imag) do { w->float_winograd_real[target+(point)*12]=(real); w->float_winograd_imag[target+(point)*12]=(imag); } while(0)
            STORE_G(0,ar*.25f,ai*.25f);
            STORE_G(1,-(ar+br+cr)/6,-(ai+bi+ci)/6);
            STORE_G(2,(-ar+br-cr)/6,(-ai+bi-ci)/6);
            STORE_G(3,(ar+2*br+4*cr)/24,(ai+2*bi+4*ci)/24);
            STORE_G(4,(ar-2*br+4*cr)/24,(ai-2*bi+4*ci)/24);
            STORE_G(5,cr,ci);
#undef STORE_G
        }
    }
}

/* Four consecutive epochs, algebraically F(4,3). The direct coarse kernel
 * accumulates taps in increasing k; this intentionally changes FP32 order. */
static int coarse_fp32_add_four(leo_presence_workspace *w,int symbol,
    ptrdiff_t position,ptrdiff_t epoch)
{
#if defined(__ARM_NEON)
    int taps=(int)(w->stops[symbol]-w->starts[symbol]),chunks=taps/3;
    float final_r[4][12],final_i[4][12];
    for(int f=0;f<12;f+=4){
        float32x4_t r0=vdupq_n_f32(0),r1=r0,r2=r0,r3=r0,i0=r0,i1=r0,i2=r0,i3=r0;
        for(int chunk=0;chunk<chunks;++chunk){const float *s=w->float_samples+2*(position+3*chunk);float xr[6],xi[6],ur[6],ui[6];for(int q=0;q<6;++q){xr[q]=s[2*q];xi[q]=s[2*q+1];}
#define BT(dst,z) do {dst[0]=4*z[0]-5*z[2]+z[4];dst[1]=-4*z[1]-4*z[2]+z[3]+z[4];dst[2]=4*z[1]-4*z[2]-z[3]+z[4];dst[3]=-2*z[1]-z[2]+2*z[3]+z[4];dst[4]=2*z[1]-z[2]-2*z[3]+z[4];dst[5]=4*z[1]-5*z[3]+z[5];}while(0)
            BT(ur,xr);BT(ui,xi);
#undef BT
            int base=(symbol*15+chunk)*6*12;
            for(int q=0;q<6;++q){float32x4_t ar=vld1q_f32(w->float_winograd_real+base+q*12+f),ai=vld1q_f32(w->float_winograd_imag+base+q*12+f),mr=vsubq_f32(vmulq_n_f32(ar,ur[q]),vmulq_n_f32(ai,ui[q])),mi=vaddq_f32(vmulq_n_f32(ai,ur[q]),vmulq_n_f32(ar,ui[q]));
#define APPLY(a0,a1,a2,a3,m) do{a0=vaddq_f32(a0,m);if(q==1){a1=vaddq_f32(a1,m);a2=vaddq_f32(a2,m);a3=vaddq_f32(a3,m);}else if(q==2){a1=vsubq_f32(a1,m);a2=vaddq_f32(a2,m);a3=vsubq_f32(a3,m);}else if(q==3){a1=vaddq_f32(a1,vmulq_n_f32(m,2));a2=vaddq_f32(a2,vmulq_n_f32(m,4));a3=vaddq_f32(a3,vmulq_n_f32(m,8));}else if(q==4){a1=vsubq_f32(a1,vmulq_n_f32(m,2));a2=vaddq_f32(a2,vmulq_n_f32(m,4));a3=vsubq_f32(a3,vmulq_n_f32(m,8));}}while(0)
                if(q<5){APPLY(r0,r1,r2,r3,mr);APPLY(i0,i1,i2,i3,mi);}else{r3=vaddq_f32(r3,mr);i3=vaddq_f32(i3,mi);}
#undef APPLY
            }
        }
        for(int tail=3*chunks;tail<taps;++tail)for(int j=0;j<4;++j){float xr=w->float_samples[2*(position+j+tail)],xi=w->float_samples[2*(position+j+tail)+1];float32x4_t tr=vld1q_f32(w->float_reference_real+symbol*45*12+tail*12+f),ti=vld1q_f32(w->float_reference_imag+symbol*45*12+tail*12+f),mr=vaddq_f32(vmulq_n_f32(tr,xr),vmulq_n_f32(ti,xi)),mi=vsubq_f32(vmulq_n_f32(tr,xi),vmulq_n_f32(ti,xr));if(j==0){r0=vaddq_f32(r0,mr);i0=vaddq_f32(i0,mi);}else if(j==1){r1=vaddq_f32(r1,mr);i1=vaddq_f32(i1,mi);}else if(j==2){r2=vaddq_f32(r2,mr);i2=vaddq_f32(i2,mi);}else{r3=vaddq_f32(r3,mr);i3=vaddq_f32(i3,mi);}}
        vst1q_f32(final_r[0]+f,r0);vst1q_f32(final_r[1]+f,r1);vst1q_f32(final_r[2]+f,r2);vst1q_f32(final_r[3]+f,r3);vst1q_f32(final_i[0]+f,i0);vst1q_f32(final_i[1]+f,i1);vst1q_f32(final_i[2]+f,i2);vst1q_f32(final_i[3]+f,i3);
    }
    for(int j=0;j<4;++j){double received=w->prefix[position+j+taps]-w->prefix[position+j];if(received<0)received=0;double denominator=sqrt(w->float_reference_energy[symbol]*received);if(denominator>0){float inverse=(float)(1.0/denominator);if(!isfinite(inverse))return -1;for(int f=0;f<12;f+=4){float32x4_t re=vld1q_f32(final_r[j]+f),im=vld1q_f32(final_i[j]+f),sum=vld1q_f32(w->float_accumulated+12*(epoch+j)+f);vst1q_f32(w->float_accumulated+12*(epoch+j)+f,vaddq_f32(sum,vmulq_n_f32(coarse_magnitude(re,im),inverse)));}}++w->support[epoch+j];}return 0;
#else
    int taps=(int)(w->stops[symbol]-w->starts[symbol]), chunks=taps/3;
    float out_r[4][12]={{0}},out_i[4][12]={{0}};
    for(int chunk=0;chunk<chunks;++chunk){
        const float *s=w->float_samples+2*(position+3*chunk);
        float ur[6],ui[6],xr[6],xi[6];for(int q=0;q<6;++q){xr[q]=s[2*q];xi[q]=s[2*q+1];}
#define BT(dst,z) do { dst[0]=4*z[0]-5*z[2]+z[4];dst[1]=-4*z[1]-4*z[2]+z[3]+z[4];dst[2]=4*z[1]-4*z[2]-z[3]+z[4];dst[3]=-2*z[1]-z[2]+2*z[3]+z[4];dst[4]=2*z[1]-z[2]-2*z[3]+z[4];dst[5]=4*z[1]-5*z[3]+z[5];}while(0)
        BT(ur,xr);BT(ui,xi);
#undef BT
        int base=(symbol*15+chunk)*6*12;
        for(int f=0;f<12;f+=4){
#if defined(__ARM_NEON)
            float32x4_t mr[6],mi[6];for(int q=0;q<6;++q){float32x4_t ar=vld1q_f32(w->float_winograd_real+base+q*12+f),ai=vld1q_f32(w->float_winograd_imag+base+q*12+f);mr[q]=vsubq_f32(vmulq_n_f32(ar,ur[q]),vmulq_n_f32(ai,ui[q]));mi[q]=vaddq_f32(vmulq_n_f32(ai,ur[q]),vmulq_n_f32(ar,ui[q]));}
#define ADD_A(dst,m) do {float32x4_t old;old=vld1q_f32(dst[0]+f);vst1q_f32(dst[0]+f,vaddq_f32(old,vaddq_f32(vaddq_f32(m[0],m[1]),vaddq_f32(m[2],vaddq_f32(m[3],m[4])))));old=vld1q_f32(dst[1]+f);vst1q_f32(dst[1]+f,vaddq_f32(old,vaddq_f32(vsubq_f32(m[1],m[2]),vmulq_n_f32(vsubq_f32(m[3],m[4]),2))));old=vld1q_f32(dst[2]+f);vst1q_f32(dst[2]+f,vaddq_f32(old,vaddq_f32(vaddq_f32(m[1],m[2]),vmulq_n_f32(vaddq_f32(m[3],m[4]),4))));old=vld1q_f32(dst[3]+f);vst1q_f32(dst[3]+f,vaddq_f32(old,vaddq_f32(vaddq_f32(vsubq_f32(m[1],m[2]),vmulq_n_f32(vsubq_f32(m[3],m[4]),8)),m[5])));}while(0)
            ADD_A(out_r,mr);ADD_A(out_i,mi);
#undef ADD_A
#else
            for(int lane=0;lane<4;++lane){int ff=f+lane;float mr[6],mi[6];for(int q=0;q<6;++q){float ar=w->float_winograd_real[base+q*12+ff],ai=w->float_winograd_imag[base+q*12+ff];mr[q]=ur[q]*ar-ui[q]*ai;mi[q]=ur[q]*ai+ui[q]*ar;}out_r[0][ff]+=mr[0]+mr[1]+mr[2]+mr[3]+mr[4];out_r[1][ff]+=mr[1]-mr[2]+2*mr[3]-2*mr[4];out_r[2][ff]+=mr[1]+mr[2]+4*mr[3]+4*mr[4];out_r[3][ff]+=mr[1]-mr[2]+8*mr[3]-8*mr[4]+mr[5];out_i[0][ff]+=mi[0]+mi[1]+mi[2]+mi[3]+mi[4];out_i[1][ff]+=mi[1]-mi[2]+2*mi[3]-2*mi[4];out_i[2][ff]+=mi[1]+mi[2]+4*mi[3]+4*mi[4];out_i[3][ff]+=mi[1]-mi[2]+8*mi[3]-8*mi[4]+mi[5];}
#endif
        }
    }
    for(int tail=3*chunks;tail<taps;++tail)for(int j=0;j<4;++j)for(int f=0;f<12;++f){float xr=w->float_samples[2*(position+j+tail)],xi=w->float_samples[2*(position+j+tail)+1],rr=w->float_reference_real[symbol*45*12+tail*12+f],ri=w->float_reference_imag[symbol*45*12+tail*12+f];out_r[j][f]+=xr*rr+xi*ri;out_i[j][f]+=xi*rr-xr*ri;}
    for(int j=0;j<4;++j){double received=w->prefix[position+j+taps]-w->prefix[position+j];if(received<0)received=0;double denominator=sqrt(w->float_reference_energy[symbol]*received);if(denominator>0){float inverse=(float)(1.0/denominator);if(!isfinite(inverse))return -1;for(int f=0;f<12;++f)w->float_accumulated[12*(epoch+j)+f]+=sqrtf(out_r[j][f]*out_r[j][f]+out_i[j][f]*out_i[j][f])*inverse;}++w->support[epoch+j];}
    return 0;
#endif
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
    if(!w->coarse_input_prepared||w->coarse_prepared_count!=count) {
        w->prefix[0]=0;
        for (size_t k=0; k<count; ++k) {
            double real=creal(w->samples[k])/scale, imag=cimag(w->samples[k])/scale;
            w->float_samples[2*k]=(float)real; w->float_samples[2*k+1]=(float)imag;
            w->prefix[k+1]=w->prefix[k]+real*real+imag*imag;
        }
    }
    w->coarse_input_prepared=0;w->coarse_prepared_count=0;
    for (int symbol=0; symbol<12; symbol+=LEO_PRESENCE_ANCHOR_STRIDE) {
        int local=(int)w->starts[symbol], taps=(int)(w->stops[symbol]-w->starts[symbol]);
        for (int slot=0; slot<LEO_PRESENCE_COARSE_FRAMES; ++slot) {
            int frame=coarse_frame_index(slot);
            ptrdiff_t base=local+w->offsets[frame];
            ptrdiff_t valid=(ptrdiff_t)count-taps+1-base;
            if (valid<=0) break;
            if (valid>(ptrdiff_t)w->n) valid=(ptrdiff_t)w->n;
            int active=0;
            for (; active<regional_count;) {
                ptrdiff_t epoch=regional_epochs[active];
                if (epoch>=valid) {++active;continue;}
                ptrdiff_t position=base+epoch;
                if(active+3<regional_count&&regional_epochs[active+1]==epoch+1&&regional_epochs[active+2]==epoch+2&&regional_epochs[active+3]==epoch+3&&epoch+3<valid){if(coarse_fp32_add_four(w,symbol,position,epoch))return -1;active+=4;continue;}
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
