/* Research-private higher-rate coarse proposal.  Include after presence.c's
 * workspace definition and coarse_fp32.h.  Any uncertain case returns to the
 * complete qualified direct grid. */
#include <fftw3.h>
#include <float.h>

enum { FFT_COARSE_CFO=11, FFT_COARSE_SYMBOLS=12 };

typedef struct {
    int n, taps, step;
    fftwf_complex *time, *spectrum, *product, *kernels;
    float *inverse_norm;
    fftwf_plan forward, inverse;
} fft_coarse_bank;

static void fft_coarse_bank_destroy(fft_coarse_bank *b)
{
    if (b->forward) fftwf_destroy_plan(b->forward);
    if (b->inverse) fftwf_destroy_plan(b->inverse);
    fftwf_free(b->inverse_norm); fftwf_free(b->kernels); fftwf_free(b->product);
    fftwf_free(b->spectrum); fftwf_free(b->time);
    memset(b,0,sizeof(*b));
}

static int fft_coarse_bank_init(fft_coarse_bank *b, leo_presence_workspace *w,
    int symbol, int fft_n)
{
    memset(b,0,sizeof(*b));
    b->n=fft_n;
    b->taps=(int)(w->stops[symbol]-w->starts[symbol]);
    b->step=fft_n-b->taps+1;
    if (b->taps<1 || b->taps>45 || b->step<1) return -1;
    b->time=fftwf_malloc(sizeof(*b->time)*(size_t)fft_n);
    b->spectrum=fftwf_malloc(sizeof(*b->spectrum)*(size_t)fft_n);
    b->product=fftwf_malloc(sizeof(*b->product)*(size_t)fft_n);
    b->kernels=fftwf_malloc(sizeof(*b->kernels)*(size_t)fft_n*FFT_COARSE_CFO);
    b->inverse_norm=fftwf_malloc(sizeof(*b->inverse_norm)*(size_t)b->step);
    if (!b->time || !b->spectrum || !b->product || !b->kernels || !b->inverse_norm) goto fail;
    b->forward=fftwf_plan_dft_1d(fft_n,b->time,b->spectrum,FFTW_FORWARD,FFTW_ESTIMATE);
    b->inverse=fftwf_plan_dft_1d(fft_n,b->product,b->time,FFTW_BACKWARD,FFTW_ESTIMATE);
    if (!b->forward || !b->inverse) goto fail;
    for (int f=0;f<FFT_COARSE_CFO;++f) {
        memset(b->time,0,sizeof(*b->time)*(size_t)fft_n);
        for (int k=0;k<b->taps;++k) {
            int source=12*(b->taps-1-k)+f;
            b->time[k]=w->float_reference_real[symbol*45*12+source]
                -I*w->float_reference_imag[symbol*45*12+source];
        }
        fftwf_execute(b->forward);
        memcpy(b->kernels+(size_t)f*fft_n,b->spectrum,sizeof(*b->spectrum)*(size_t)fft_n);
    }
    return 0;
fail:
    fft_coarse_bank_destroy(b); return -1;
}

static int fft_coarse_add_span(fft_coarse_bank *b, leo_presence_workspace *w,
    ptrdiff_t base, ptrdiff_t valid, double template_energy)
{
    for (ptrdiff_t block=0;block<valid;block+=b->step) {
        int count=(int)(valid-block); if (count>b->step) count=b->step;
        memset(b->time,0,sizeof(*b->time)*(size_t)b->n);
        int available=count+b->taps-1;
        for (int k=0;k<available;++k) {
            const float *x=w->float_samples+2*(base+block+k);
            b->time[k]=x[0]+I*x[1];
        }
        double block_energy=0;
        for (int k=0;k<available;++k)
            block_energy+=power((double complex)b->time[k]);
        for (int j=0;j<count;++j) {
            ptrdiff_t position=base+block+j;
            double received=w->prefix[position+b->taps]-w->prefix[position];
            if (received<0) received=0;
            /* A large sample elsewhere in the FFT block can contaminate a
             * weak local window before its small normalization denominator is
             * applied. The ratio is an engineering screen, so reject the
             * entire proposal rather than claim a numerical bound. */
            if (received>0 && block_energy>0 && received<block_energy*1e-6)
                return -1;
            double denominator=sqrt(template_energy*received);
            b->inverse_norm[j]=denominator>0 ? (float)(1.0/denominator) : 0;
            if (!isfinite(b->inverse_norm[j])) return -1;
        }
        fftwf_execute(b->forward);
        for (int f=0;f<FFT_COARSE_CFO;++f) {
#if defined(__ARM_NEON)
            for (int k=0;k<b->n;k+=4) {
                float32x4x2_t a=vld2q_f32((float *)(b->spectrum+k));
                float32x4x2_t z=vld2q_f32((float *)(b->kernels+(size_t)f*b->n+k));
                float32x4x2_t p;
                p.val[0]=vsubq_f32(vmulq_f32(a.val[0],z.val[0]),vmulq_f32(a.val[1],z.val[1]));
                p.val[1]=vaddq_f32(vmulq_f32(a.val[0],z.val[1]),vmulq_f32(a.val[1],z.val[0]));
                vst2q_f32((float *)(b->product+k),p);
            }
#else
            for (int k=0;k<b->n;++k)
                b->product[k]=b->spectrum[k]*b->kernels[(size_t)f*b->n+k];
#endif
            fftwf_execute(b->inverse);
            int j=0;
#if defined(__ARM_NEON)
            float32x4_t fft_scale=vdupq_n_f32(1.0f/b->n);
            for (;j+3<count;j+=4) {
                float32x4x2_t z=vld2q_f32((float *)(b->time+j+b->taps-1));
                float32x4_t mag=vmulq_f32(coarse_magnitude(z.val[0],z.val[1]),fft_scale);
                float values[4];vst1q_f32(values,mag);
                for(int lane=0;lane<4;++lane)
                    w->float_accumulated[12*(block+j+lane)+f]+=values[lane]*b->inverse_norm[j+lane];
            }
#endif
            for (;j<count;++j) {
                ptrdiff_t epoch=block+j;
                if (b->inverse_norm[j]>0) {
                    float re=crealf(b->time[j+b->taps-1])/b->n;
                    float im=cimagf(b->time[j+b->taps-1])/b->n;
                    float value=hypotf(re,im)*b->inverse_norm[j];
                    if (!isfinite(value)) return -1;
                    w->float_accumulated[12*epoch+f]+=value;
                }
            }
        }
        for (int j=0;j<count;++j) ++w->support[block+j];
    }
    return 0;
}

static int fft_coarse_full_direct(leo_presence_workspace *w,size_t count,int *fallback)
{ if (fallback) *fallback=1; return coarse_fp32(w,count); }

static int fft_coarse_proposal(leo_presence_workspace *w,size_t count,
    int *repaired_epochs,int *fallback)
{
    if (repaired_epochs) *repaired_epochs=0;
    if (fallback) *fallback=0;
    if (w->rate==2500000) return coarse_fp32(w,count);
    if (epoch_stride(w)!=1) return fft_coarse_full_direct(w,count,fallback);
    if (getenv("LEO_FFT_COARSE_FORCE_FALLBACK"))
        return fft_coarse_full_direct(w,count,fallback);
    int fft_n=(w->rate==5000000 || w->rate==7500000) ? 128 :
        (w->rate==10000000 ? 256 : 0);
    if (!fft_n) return fft_coarse_full_direct(w,count,fallback);
    double scale=0;
    memset(w->float_accumulated,0,12*w->n*sizeof(float));
    memset(w->support,0,w->n*sizeof(*w->support));
    for (size_t k=0;k<count;++k)
        scale=fmax(scale,fmax(fabs(creal(w->samples[k])),fabs(cimag(w->samples[k]))));
    if (scale==0) { memset(w->grid,0,CFO_COUNT*w->n*sizeof(double)); return 0; }
    w->prefix[0]=0;
    for (size_t k=0;k<count;++k) {
        double re=creal(w->samples[k])/scale, im=cimag(w->samples[k])/scale;
        w->float_samples[2*k]=(float)re; w->float_samples[2*k+1]=(float)im;
        w->prefix[k+1]=w->prefix[k]+re*re+im*im;
    }
    for (int symbol=0;symbol<12;symbol+=LEO_PRESENCE_ANCHOR_STRIDE) {
        fft_coarse_bank b;
        if (fft_coarse_bank_init(&b,w,symbol,fft_n))
            return fft_coarse_full_direct(w,count,fallback);
        for (int frame=0;frame<LEO_PRESENCE_COARSE_FRAMES;++frame) {
            ptrdiff_t base=w->starts[symbol]+w->offsets[frame];
            ptrdiff_t valid=(ptrdiff_t)count-b.taps+1-base;
            if (valid<=0) break;
            if (valid>(ptrdiff_t)w->n) valid=(ptrdiff_t)w->n;
            if (fft_coarse_add_span(&b,w,base,valid,w->float_reference_energy[symbol])) {
                fft_coarse_bank_destroy(&b);
                return fft_coarse_full_direct(w,count,fallback);
            }
        }
        fft_coarse_bank_destroy(&b);
    }
    for (int f=0;f<11;++f) for (size_t e=0;e<w->n;++e) {
        w->grid[f*w->n+e]=w->support[e] ?
            (double)w->float_accumulated[12*e+f]/w->support[e] : -INFINITY;
        if (w->support[e] && !isfinite(w->grid[f*w->n+e]))
            return fft_coarse_full_direct(w,count,fallback);
    }

    /* Engineering guard, deliberately conservative: iteratively repair all
     * epochs capable of crossing the current eighth separated peak, plus
     * their linear neighbours. If an unrepaired upper bound still touches
     * the retained boundary, the complete direct grid is cheaper to trust. */
    unsigned char *done=calloc(w->n,1), *mark=calloc(w->n,1);
    leo_full_search_peak *peaks=malloc(11*w->n*sizeof(*peaks));
    if (!done || !mark || !peaks) { free(peaks);free(mark);free(done); return fft_coarse_full_direct(w,count,fallback); }
    const double guard=128.0*FLT_EPSILON;
    int converged=0;
    for (int pass=0;pass<4;++pass) {
        size_t np=0;
        for(int f=0;f<11;++f) for(int e=0;e<(int)w->n;++e) {
            double v=w->grid[f*w->n+e],l=e?w->grid[f*w->n+e-1]:-INFINITY,r=e+1<(int)w->n?w->grid[f*w->n+e+1]:-INFINITY;
            if(v>=l&&v>=r&&(v>l||v>r)) peaks[np++]=(leo_full_search_peak){v,e,f};
        }
        leo_full_search_peak kept[LEO_FULL_SEARCH_MAX_CANDIDATES];
        size_t nk=leo_full_search_retain_peaks(peaks,np,(int32_t)w->n,w->frequencies,kept);
        if (np && !nk) { free(peaks);free(mark);free(done); return fft_coarse_full_direct(w,count,fallback); }
        double cutoff=nk==LEO_FULL_SEARCH_MAX_CANDIDATES ? kept[nk-1].score-2*guard : -INFINITY;
        memset(mark,0,w->n);
        for(int e=0;e<(int)w->n;++e) for(int f=0;f<11;++f)
            if(w->grid[f*w->n+e]>=cutoff) for(int d=-1;d<=1;++d) if(e+d>=0&&e+d<(int)w->n) mark[e+d]=1;
        int changed=0;
        for(int e=0;e<(int)w->n;++e) if(mark[e]&&!done[e]) {
            memset(w->float_accumulated+12*e,0,12*sizeof(float)); w->support[e]=0;
            if(coarse_fp32_cell(w,count,e)) { free(peaks);free(mark);free(done); return fft_coarse_full_direct(w,count,fallback); }
            done[e]=1;changed=1;if(repaired_epochs)++*repaired_epochs;
        }
        if(!changed) { converged=1; break; }
    }
    if (!converged) {
        free(peaks);free(mark);free(done);
        return fft_coarse_full_direct(w,count,fallback);
    }
    /* Engineering acceptance requires every unrepaired proposal cell to stay
     * more than the empirical guard below the repaired eighth score. This is
     * not a formal bound; ambiguous windows use the complete direct grid. */
    size_t np=0; double upper=-INFINITY;
    for(int f=0;f<11;++f) for(int e=0;e<(int)w->n;++e) {
        if(!done[e]&&isfinite(w->grid[f*w->n+e])) upper=fmax(upper,w->grid[f*w->n+e]+guard);
        double v=w->grid[f*w->n+e],l=e?w->grid[f*w->n+e-1]:-INFINITY,r=e+1<(int)w->n?w->grid[f*w->n+e+1]:-INFINITY;
        if(v>=l&&v>=r&&(v>l||v>r)) peaks[np++]=(leo_full_search_peak){v,e,f};
    }
    leo_full_search_peak kept[LEO_FULL_SEARCH_MAX_CANDIDATES];
    size_t nk=leo_full_search_retain_peaks(peaks,np,(int32_t)w->n,w->frequencies,kept);
    int ambiguous=(np&&!nk)||(nk==LEO_FULL_SEARCH_MAX_CANDIDATES && kept[nk-1].score<=upper);
    free(peaks);free(mark);free(done);
    return ambiguous ? fft_coarse_full_direct(w,count,fallback) : 0;
}
