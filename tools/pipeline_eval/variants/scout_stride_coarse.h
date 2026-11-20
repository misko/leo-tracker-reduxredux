/* Every second coarse CFO followed by native neighboring-bin rescue. */
#ifndef LEO_SCOUT_STRIDE_COARSE_H
#define LEO_SCOUT_STRIDE_COARSE_H

static void scout_stride_even_add(const float *samples,const float *real,
    const float *imag,int taps,float inverse,float *sum)
{
#if defined(__ARM_NEON)
    for (int f=0;f<12;f+=4) {
        float32x4_t r=vdupq_n_f32(0),i=r;
        for (int k=0;k<taps;++k) {
            float32x4_t xr=vdupq_n_f32(samples[2*k]),xi=vdupq_n_f32(samples[2*k+1]);
            float32x4_t rr=vld1q_f32(real+12*k+f),ri=vld1q_f32(imag+12*k+f);
            r=vaddq_f32(r,vaddq_f32(vmulq_f32(xr,rr),vmulq_f32(xi,ri)));
            i=vaddq_f32(i,vsubq_f32(vmulq_f32(xi,rr),vmulq_f32(xr,ri)));
        }
        float v[4];
        vst1q_f32(v,vmulq_n_f32(coarse_magnitude(r,i),inverse));
        for (int lane=0;lane<4;++lane) sum[2*(f+lane)]+=v[lane];
    }
#else
    float r[12]={0},i[12]={0};
    for (int k=0;k<taps;++k)
        for (int f=0;f<12;++f) {
            r[f]+=samples[2*k]*real[12*k+f]+samples[2*k+1]*imag[12*k+f];
            i[f]+=samples[2*k+1]*real[12*k+f]-samples[2*k]*imag[12*k+f];
        }
    for (int f=0;f<11;++f) sum[2*f]+=sqrtf(r[f]*r[f]+i[f]*i[f])*inverse;
#endif
}

static int scout_stride_odd(leo_presence_workspace *w,size_t count,int epoch,int bin)
{
    float sum=0;
    for (int symbol=0;symbol<12;symbol+=LEO_PRESENCE_ANCHOR_STRIDE) {
        int taps=(int)(w->stops[symbol]-w->starts[symbol]);
        const float *real=w->float_reference_real+symbol*45*CFO_COUNT+bin;
        const float *imag=w->float_reference_imag+symbol*45*CFO_COUNT+bin;
        for (int slot=0;slot<LEO_PRESENCE_COARSE_FRAMES;++slot) {
            ptrdiff_t pos=w->starts[symbol]+w->offsets[coarse_frame_index(slot)]+epoch;
            if (pos+taps>(ptrdiff_t)count) break;
            double energy=w->prefix[pos+taps]-w->prefix[pos];
            if (energy<0) energy=0;
            double denom=sqrt(w->float_reference_energy[symbol]*energy);
            if (!(denom>0)) continue;
            float inverse=(float)(1.0/denom);
            if (!isfinite(inverse)) return -1;
            const float *x=w->float_samples+2*pos;
            float r=0,i=0;
            for (int k=0;k<taps;++k) {
                float rr=real[CFO_COUNT*k],ri=imag[CFO_COUNT*k];
                r+=x[2*k]*rr+x[2*k+1]*ri;
                i+=x[2*k+1]*rr-x[2*k]*ri;
            }
#if defined(__ARM_NEON)
            sum+=vgetq_lane_f32(coarse_magnitude(vdupq_n_f32(r),vdupq_n_f32(i)),0)*inverse;
#else
            sum+=sqrtf(r*r+i*i)*inverse;
#endif
        }
    }
    if (w->support[epoch]>0) w->grid[bin*w->n+epoch]=(double)sum/w->support[epoch];
    return 0;
}

static int scout_stride_neighbors(leo_presence_workspace *w,size_t count)
{
    for (int start=0;start<w->regional_count;) {
        int end=start+1;
        while (end<w->regional_count && w->regional_epochs[end]==w->regional_epochs[end-1]+1)
            ++end;
        int best=-1;
        double maximum=0;
        for (int f=0;f<WIDE_REGIONAL_BINS;f+=2) {
            for (int i=start;i<end;++i) {
                double score=w->grid[f*w->n+w->regional_epochs[i]];
                if (score>maximum || (score==maximum && best>=0 &&
                        fabs(w->frequencies[f])<fabs(w->frequencies[best]))) {
                    maximum=score;
                    best=f;
                }
            }
        }
        if (best>=0) {
            for (int f=best-1;f<=best+1;f+=2) {
                if (f<0 || f>=WIDE_REGIONAL_BINS) continue;
                for (int i=start;i<end;++i)
                    if (scout_stride_odd(w,count,w->regional_epochs[i],f)) return -1;
            }
        }
        start=end;
    }
    return 0;
}

#endif
