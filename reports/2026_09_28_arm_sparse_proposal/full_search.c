#define _POSIX_C_SOURCE 200809L
/* Keep the reviewed source immutable while reusing its private FP64 kernels.
 * Compile this file with the frozen native_presence directory on -I and do not
 * also compile presence.c into the same program. */
#include "full_search.h"
#include "conditioned_czt.h"
#include <float.h>
#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#include "presence.c"
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

/* The goal40mag range backend is FP32 FFTW. The full-search reference build
 * uses the repository's double FFT and computes the whole transform; this
 * adapter only narrows which output cells fine_scores subsequently reads. */
#ifndef LEO_FULL_EXTERNAL_RANGE
void leo_fft_forward_range(leo_fft *fft, const double complex *input, size_t used,
    size_t first, size_t count)
{
    (void)used; (void)first; (void)count;
    leo_fft_forward(fft,input);
}
#endif

/* Bound the FP32 accumulation chain to 16 products per lane. Reducing each
 * 64-sample block in FP64 prevents error growth with the template length. */
static double complex full_blocked_dot(const float *a, const float *b, size_t n)
{
    double total_re=0, total_im=0;
    for (size_t start=0; start<n; start+=64) {
        size_t end=start+64<n ? start+64 : n, k=start;
        float re[4]={0}, im[4]={0};
#if defined(__ARM_NEON)
        float32x4_t vr=vdupq_n_f32(0), vi=vr;
        for (;k+3<end;k+=4) {
            float32x4x2_t x=vld2q_f32(a+2*k), y=vld2q_f32(b+2*k);
            vr=vaddq_f32(vr,vsubq_f32(vmulq_f32(x.val[0],y.val[0]),
                vmulq_f32(x.val[1],y.val[1])));
            vi=vaddq_f32(vi,vaddq_f32(vmulq_f32(x.val[0],y.val[1]),
                vmulq_f32(x.val[1],y.val[0])));
        }
        vst1q_f32(re,vr); vst1q_f32(im,vi);
#else
        for (;k+3<end;k+=4) for (size_t j=0;j<4;++j) {
            size_t z=2*(k+j);
            re[j]+=a[z]*b[z]-a[z+1]*b[z+1];
            im[j]+=a[z]*b[z+1]+a[z+1]*b[z];
        }
#endif
        for (;k<end;++k) {
            re[0]+=a[2*k]*b[2*k]-a[2*k+1]*b[2*k+1];
            im[0]+=a[2*k]*b[2*k+1]+a[2*k+1]*b[2*k];
        }
        for (int j=0;j<4;++j) {total_re+=re[j];total_im+=im[j];}
    }
    return total_re+I*total_im;
}

static int peak_before(const leo_full_search_peak *a, const leo_full_search_peak *b,
    const double coarse_cfo_hz[11])
{
    if (a->score != b->score) return a->score > b->score;
    double aa=fabs(coarse_cfo_hz[a->coarse_bin]);
    double ab=fabs(coarse_cfo_hz[b->coarse_bin]);
    if (aa != ab) return aa < ab;
    return a->epoch < b->epoch;
}

static void stable_sort_peaks(leo_full_search_peak *peaks,
    leo_full_search_peak *scratch, size_t begin, size_t end,
    const double coarse_cfo_hz[11])
{
    if (end-begin<2) return;
    size_t middle=begin+(end-begin)/2;
    stable_sort_peaks(peaks,scratch,begin,middle,coarse_cfo_hz);
    stable_sort_peaks(peaks,scratch,middle,end,coarse_cfo_hz);
    size_t left=begin, right=middle, out=begin;
    while (left<middle && right<end) {
        /* Select the left item when keys compare equal. Input order is the
         * frozen coarse scan order (CFO bin, then epoch), matching Python's
         * stable sort for otherwise identical tuple keys. */
        if (peak_before(&peaks[right],&peaks[left],coarse_cfo_hz))
            scratch[out++]=peaks[right++];
        else
            scratch[out++]=peaks[left++];
    }
    while (left<middle) scratch[out++]=peaks[left++];
    while (right<end) scratch[out++]=peaks[right++];
    memcpy(peaks+begin,scratch+begin,(end-begin)*sizeof(*peaks));
}

size_t leo_full_search_retain_peaks(leo_full_search_peak *peaks, size_t peak_count,
    int32_t epoch_count, const double coarse_cfo_hz[11],
    leo_full_search_peak retained[LEO_FULL_SEARCH_MAX_CANDIDATES])
{
    if (!peaks || !coarse_cfo_hz || !retained || epoch_count<=0) return 0;
    leo_full_search_peak *scratch=malloc(peak_count*sizeof(*scratch));
    if (peak_count && !scratch) return 0;
    stable_sort_peaks(peaks,scratch,0,peak_count,coarse_cfo_hz);
    free(scratch);
    size_t nr=0;
    for (size_t i=0; i<peak_count && nr<LEO_FULL_SEARCH_MAX_CANDIDATES; ++i) {
        int separated=1;
        for (size_t j=0; j<nr; ++j) {
            int distance=abs(peaks[i].epoch-retained[j].epoch);
            if (distance>epoch_count-distance) distance=epoch_count-distance;
            if (distance<5 && fabs(coarse_cfo_hz[peaks[i].coarse_bin]-
                coarse_cfo_hz[retained[j].coarse_bin])<=10000.0) {
                separated=0; break;
            }
        }
        if (separated) retained[nr++]=peaks[i];
    }
    return nr;
}

#ifndef LEO_SPARSE_COARSE_FRAMES
#define LEO_SPARSE_COARSE_FRAMES 1
#endif
#ifndef LEO_SPARSE_COARSE_SYMBOLS
#define LEO_SPARSE_COARSE_SYMBOLS 3
#endif
#if LEO_SPARSE_COARSE_FRAMES < 1 || LEO_SPARSE_COARSE_FRAMES > 16
#error "LEO_SPARSE_COARSE_FRAMES must be 1..16"
#endif
#if LEO_SPARSE_COARSE_SYMBOLS < 1 || LEO_SPARSE_COARSE_SYMBOLS > 12
#error "LEO_SPARSE_COARSE_SYMBOLS must be 1..12"
#endif

#ifndef LEO_SPARSE_CENTERS
#define LEO_SPARSE_CENTERS 32
#endif
#if LEO_SPARSE_CENTERS < 1
#error "LEO_SPARSE_CENTERS must be positive"
#endif
enum { LEO_SPARSE_RADIUS=2 };

static int sparse_retain_centers(leo_full_search_peak *peaks,size_t count,
    int epochs,const double frequencies[11],leo_full_search_peak retained[LEO_SPARSE_CENTERS])
{
    leo_full_search_peak *scratch=malloc(count*sizeof(*scratch));
    if(count&&!scratch)return -1;
    stable_sort_peaks(peaks,scratch,0,count,frequencies);free(scratch);
    int nr=0;
    for(size_t i=0;i<count&&nr<LEO_SPARSE_CENTERS;++i) {
        int separated=1;
        for(int j=0;j<nr;++j) {
            int distance=abs(peaks[i].epoch-retained[j].epoch);
            if(distance>epochs-distance)distance=epochs-distance;
            if(distance<5&&fabs(frequencies[peaks[i].coarse_bin]-
                frequencies[retained[j].coarse_bin])<=10000.0){separated=0;break;}
        }
        if(separated)retained[nr++]=peaks[i];
    }
    return nr;
}

static void sparse_set_eligible(unsigned char *eligible,const unsigned char *repaired,size_t n)
{
    memset(eligible,0,n);
    if(!n)return;
    if(n==1){eligible[0]=repaired[0];return;}
    eligible[0]=repaired[0]&&repaired[1];
    for(size_t e=1;e+1<n;++e)
        eligible[e]=repaired[e-1]&&repaired[e]&&repaired[e+1];
    eligible[n-1]=repaired[n-2]&&repaired[n-1];
}

/* Cheap proposal followed by exact repair. `eligible` is explicit because
 * hiding unrepaired cells in the grid would manufacture boundary maxima. */
static int sparse_coarse(leo_presence_workspace *w,size_t count,unsigned char *eligible)
{
    if(LEO_SPARSE_COARSE_FRAMES==16&&LEO_SPARSE_COARSE_SYMBOLS==12) {
        memset(eligible,1,w->n);return coarse_fp32(w,count);
    }
    double scale=0;memset(eligible,0,w->n);
    memset(w->float_accumulated,0,CFO_COUNT*w->n*sizeof(float));
    memset(w->support,0,w->n*sizeof(*w->support));
    for(size_t k=0;k<count;++k)
        scale=fmax(scale,fmax(fabs(creal(w->samples[k])),fabs(cimag(w->samples[k]))));
    if(scale==0) { memset(w->grid,0,CFO_COUNT*w->n*sizeof(double));memset(eligible,1,w->n);return 0; }
    w->prefix[0]=0;
    for(size_t k=0;k<count;++k) {
        double re=creal(w->samples[k])/scale,im=cimag(w->samples[k])/scale;
        w->float_samples[2*k]=(float)re;w->float_samples[2*k+1]=(float)im;
        w->prefix[k+1]=w->prefix[k]+re*re+im*im;
    }
    for(int si=0;si<LEO_SPARSE_COARSE_SYMBOLS;++si) {
        int symbol=si*12/LEO_SPARSE_COARSE_SYMBOLS;
        int taps=(int)(w->stops[symbol]-w->starts[symbol]);
        for(int fi=0;fi<LEO_SPARSE_COARSE_FRAMES;++fi) {
            int frame=fi*16/LEO_SPARSE_COARSE_FRAMES;
            ptrdiff_t base=w->starts[symbol]+w->offsets[frame];
            ptrdiff_t valid=(ptrdiff_t)count-taps+1-base;
            if(valid<=0)continue;
            if(valid>(ptrdiff_t)w->n)valid=(ptrdiff_t)w->n;
            for(ptrdiff_t epoch=0;epoch<valid;++epoch)
                if(coarse_fp32_add(w,symbol,base+epoch,epoch))return -1;
        }
    }
    for(int f=0;f<11;++f)for(size_t e=0;e<w->n;++e)
        w->grid[f*w->n+e]=w->support[e]?
            (double)w->float_accumulated[12*e+f]/w->support[e]:-INFINITY;
    size_t capacity=11*w->n,np=0;
    leo_full_search_peak *peaks=malloc(capacity*sizeof(*peaks));
    unsigned char *repaired=calloc(w->n,1);
    if(!peaks||!repaired){free(repaired);free(peaks);memset(eligible,1,w->n);return coarse_fp32(w,count);}
    for(int f=0;f<11;++f)for(int e=0;e<(int)w->n;++e) {
        double v=w->grid[f*w->n+e],left=e?w->grid[f*w->n+e-1]:-INFINITY;
        double right=e+1<(int)w->n?w->grid[f*w->n+e+1]:-INFINITY;
        if(v>=left&&v>=right&&(v>left||v>right))peaks[np++]=(leo_full_search_peak){v,e,f};
    }
    leo_full_search_peak centers[LEO_SPARSE_CENTERS];
    int nc=sparse_retain_centers(peaks,np,(int)w->n,w->frequencies,centers);
    free(peaks);
    if(nc<0){free(repaired);memset(eligible,1,w->n);return coarse_fp32(w,count);}
    for(int i=0;i<nc;++i)for(int d=-LEO_SPARSE_RADIUS;d<=LEO_SPARSE_RADIUS;++d) {
        int e=centers[i].epoch+d;if(e>=0&&e<(int)w->n)repaired[e]=1;
    }
    for(int e=0;e<(int)w->n;++e)if(repaired[e]) {
        memset(w->float_accumulated+12*e,0,12*sizeof(float));w->support[e]=0;
        if(coarse_fp32_cell(w,count,e)){free(repaired);return -1;}
    }
    sparse_set_eligible(eligible,repaired,w->n);
    free(repaired);return 0;
}

/* The goal40mag snapshot converts the conditioned dot product to float even
 * in its nominal baseline. Restore the earlier reviewed FP64 accumulation. */
static void full_conditioned_scores(leo_presence_workspace *w, size_t count,
    int epoch, const double *frequencies, int nf, double *scores, int approximate)
{
    double te=0;
    memset(scores,0,(size_t)nf*sizeof(*scores));
    /* Only the approximate regular-grid screen uses factored phasors.
     * Re-anchor every 32 samples; exact near-max rechecks retain the original
     * per-sample rotation below. No samples or hypotheses are removed. */
    int block_screen=approximate && nf>0 && nf<=64;
    for (int f=0;f<nf && block_screen;++f)
        block_screen=frequencies[f]==frequencies[0]+f*100.0;
    double complex basis[32], anchor=1;
    if (block_screen) for (size_t j=0;j<32;++j)
        basis[j]=rotate(-TAU*frequencies[0]*j/w->rate);
    for (size_t k=0; k<w->n; ++k) {
        te+=power(w->exact[k]);
        if (block_screen) {
            if (!(k&31)) anchor=rotate(-TAU*frequencies[0]*k/w->rate);
            w->base[k]=conj(w->exact[k])*(anchor*basis[k&31]);
        } else
            w->base[k]=conj(w->exact[k])*rotate(-TAU*frequencies[0]*k/w->rate);
    }
    int frames=0;
    for (int frame=0; frame<16; ++frame) {
        int start=frame_start(w,epoch,frame);
        if ((size_t)start+w->n>count) break;
        double energy=0;
        for (size_t k=0; k<w->n; ++k) {
            energy+=power(w->samples[start+k]);
            w->weighted[k]=w->samples[start+k]*w->base[k];
            if (approximate) {
                w->opt_weighted[2*k]=(float)creal(w->weighted[k]);
                w->opt_weighted[2*k+1]=(float)cimag(w->weighted[k]);
            }
        }
        double denom=sqrt(te*energy);
        float czt_magnitudes[64];
        int regular=nf>0 && nf<=64;
        for (int f=0; f<nf && regular; ++f)
            regular=frequencies[f]==frequencies[0]+f*100.0;
        int czt_ok=approximate && denom>0 && regular &&
            !leo_conditioned_czt_magnitudes(w->opt_weighted,w->n,w->rate,nf,
                czt_magnitudes);
        for (int f=0; f<nf && denom>0; ++f) {
            double complex total=0;
            int bin_regular=frequencies[f]==frequencies[0]+f*100.0;
            if (czt_ok) {
                scores[f]+=czt_magnitudes[f]/denom;
                continue;
            } else if (approximate && bin_regular)
                total=full_blocked_dot(w->opt_weighted,
                    w->opt_conditioned_offsets+2*f*w->n,w->n);
            else for (size_t k=0; k<w->n; ++k)
                total+=w->weighted[k]*(bin_regular ? w->conditioned_offsets[f*w->n+k] :
                    rotate(-TAU*(frequencies[f]-frequencies[0])*k/w->rate));
            scores[f]+=magnitude(total)/denom;
        }
        ++frames;
    }
    if (frames) for (int f=0; f<nf; ++f) scores[f]/=frames;
}

static int full_candidate_before(const leo_full_search_candidate *a,
    const leo_full_search_candidate *b)
{
    return candidate_before(&a->candidate,&b->candidate);
}

/* Compute the three final-ranking scores together. Each result retains the
 * original symbol/sample/frame accumulation order. Rotations are evaluated
 * once per used sample; odd-symbol received energy is shared by exact and
 * control, whose separate totals and template energies retain their original
 * arithmetic sequences. Stored template products preserve the rounding point
 * of normalized_score's w->base assignment. */
static void full_verification_scores(leo_presence_workspace *w,size_t count,
    int epoch,double cfo,double result[3])
{
    double te_even=0,te_exact_odd=0,te_control_odd=0;
    for(int symbol=2;symbol<302;++symbol) {
        int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
        for(int k=begin;k<end;++k) {
            w->input[k]=rotate(-TAU*cfo*k/w->rate);
            if(!(symbol&1)) {
                te_even+=power(w->exact[k]);
                w->base[k]=conj(w->exact[k])*w->input[k];
            } else {
                te_exact_odd+=power(w->exact[k]);
                te_control_odd+=power(w->control[k]);
                w->base[k]=conj(w->exact[k])*w->input[k];
                w->weighted[k]=conj(w->control[k])*w->input[k];
            }
        }
    }
    double scores[3]={0};int even_frames=0,odd_frames=0;
    size_t even_last=(size_t)symbol_start(w,301)-1;
    size_t odd_last=(size_t)symbol_start(w,302)-1;
    for(int frame=0;frame<LEO_PRESENCE_FINE_FRAMES;++frame) {
        int start=frame_start(w,epoch,frame+w->acquisition_first_frame);
        if((size_t)start+even_last<count) {
            double energy=0;double complex total=0;
            for(int symbol=2;symbol<302;symbol+=2) {
                int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
                for(int k=begin;k<end;++k) {
                    total+=w->samples[start+k]*w->base[k];
                    energy+=power(w->samples[start+k]);
                }
            }
            double denom=sqrt(te_even*energy);
            if(denom>0)scores[0]+=magnitude(total)/denom;
            ++even_frames;
        }
        if((size_t)start+odd_last<count) {
            double energy=0;double complex exact=0,control=0;
            for(int symbol=3;symbol<302;symbol+=2) {
                int begin=symbol_start(w,symbol),end=symbol_start(w,symbol+1);
                for(int k=begin;k<end;++k) {
                    exact+=w->samples[start+k]*w->base[k];
                    control+=w->samples[start+k]*w->weighted[k];
                    energy+=power(w->samples[start+k]);
                }
            }
            double exact_denom=sqrt(te_exact_odd*energy);
            double control_denom=sqrt(te_control_odd*energy);
            if(exact_denom>0)scores[1]+=magnitude(exact)/exact_denom;
            if(control_denom>0)scores[2]+=magnitude(control)/control_denom;
            ++odd_frames;
        }
    }
    result[0]=even_frames?scores[0]/even_frames:0;
    result[1]=odd_frames?scores[1]/odd_frames:0;
    result[2]=odd_frames?scores[2]/odd_frames:0;
}

static int full_frame_support(const leo_presence_workspace *w, size_t count, int epoch)
{
    int support=0;
    for (int frame=0; frame<16; ++frame) {
        int start=frame_start(w,epoch,frame);
        if (start<0 || start+symbol_start(w,302)>(int)count) break;
        ++support;
    }
    return support;
}

int leo_full_search_run(leo_presence_workspace *w,
    const leo_presence_complex *samples, size_t count, leo_full_search_result *result)
{
    if (!result) return -1;
    leo_full_search_result out={0};
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID), wall=clock_ms(CLOCK_MONOTONIC);
    if (ingest(w,samples,count)) return -1;
    /* Frozen acquisition always starts at the first complete frame. Clear
     * experimental support state in case this workspace was previously used
     * by another research entry point. */
    w->acquisition_first_frame=0;
    w->acquisition_regions[0]=w->acquisition_regions[1]=0;
    out.conversion_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    double started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    unsigned char *coarse_eligible=malloc(w->n);
    if(!coarse_eligible)return -1;
    if(sparse_coarse(w,count,coarse_eligible)){free(coarse_eligible);return -1;}
    out.coarse_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;

    size_t capacity=11*w->n;
    leo_full_search_peak *peaks=malloc(capacity*sizeof(*peaks));
    if (!peaks) return -1;
    size_t peak_count=0;
    for (int f=0; f<11; ++f) for (int e=0; e<(int)w->n; ++e) {
        if(!coarse_eligible[e])continue;
        double value=w->grid[f*w->n+e];
        double left=e ? w->grid[f*w->n+e-1] : -INFINITY;
        double right=e+1<(int)w->n ? w->grid[f*w->n+e+1] : -INFINITY;
        if (value>=left && value>=right && (value>left || value>right))
            peaks[peak_count++]=(leo_full_search_peak){value,e,f};
    }
    free(coarse_eligible);
    leo_full_search_peak retained[LEO_FULL_SEARCH_MAX_CANDIDATES];
    size_t nr=leo_full_search_retain_peaks(peaks,peak_count,(int32_t)w->n,
        w->frequencies,retained);
    free(peaks);
    /* A nonempty peak inventory always retains its first member. Preserve the
     * detector's error/absence distinction if the sort workspace allocation
     * failed inside the pure helper. */
    if (peak_count && !nr) return -1;
    if (!nr || retained[0].score<=0) {
        out.total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
        out.total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
        *result=out; return 0;
    }
    out.retained_peak_count=(int32_t)nr;

    started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    for (size_t r=0; r<nr; ++r) {
        int e=retained[r].epoch, f=retained[r].coarse_bin, refined=e;
        for (int local=e-1; local<=e+1; ++local)
            if (local>=0 && local<(int)w->n &&
                (w->grid[f*w->n+local]>w->grid[f*w->n+refined] ||
                (w->grid[f*w->n+local]==w->grid[f*w->n+refined] && local<refined)))
                refined=local;
        int support=full_frame_support(w,count,refined);
        if (support<2) continue;
        double frequencies[2048], scores[2048];
        double lower=fmax(-400000,w->frequencies[f]-80000);
        double upper=fmin(400000,w->frequencies[f]+80000);
        int nf=grid(lower,upper,w->fine_step_hz,frequencies);
        double stage=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        fine_scores(w,count,refined,frequencies[0],nf,scores);
        out.fine_fft_cpu_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage;
        int best=best_frequency(scores,frequencies,nf);
        double fine=frequencies[best], interpolated=fine;
        if (best>0 && best+1<nf) {
            double curve=scores[best-1]-2*scores[best]+scores[best+1];
            if (isfinite(curve) && curve<-1e-15)
                interpolated+=fmax(-w->fine_step_hz,fmin(w->fine_step_hz,
                    .5*(scores[best-1]-scores[best+1])/curve*w->fine_step_hz));
        }
        nf=grid(fmax(-400000,interpolated-2000),
            fmin(400000,interpolated+2000),100,frequencies);
        stage=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
#if defined(LEO_FULL_CONDITIONED_SCREEN)
        full_conditioned_scores(w,count,refined,frequencies,nf,scores,1);
        double maximum=scores[best_frequency(scores,frequencies,nf)];
        /* Conservative engineering guard for blocked FP32 dot errors in
         * normalized scores. This is a qualification candidate, not a claim
         * of universally proven equivalence. Every bin is screened, and near
         * maxima are recomputed in FP64 before selecting the final CFO. */
        const double guard=128.0*FLT_EPSILON;
        out.conditioned_bins_screened+=nf;
        for (int q=0;q<nf;++q) {
            if (!isfinite(scores[q]) || scores[q]>=maximum-2*guard) {
                full_conditioned_scores(w,count,refined,frequencies+q,1,scores+q,0);
                ++out.conditioned_bins_rechecked;
            } else scores[q]=-INFINITY;
        }
#else
        full_conditioned_scores(w,count,refined,frequencies,nf,scores,0);
        out.conditioned_bins_rechecked+=nf;
#endif
        out.conditioned_cpu_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage;
        best=best_frequency(scores,frequencies,nf);
        leo_full_search_candidate *dst=&out.candidates[out.candidate_count];
        dst->coarse_epoch=e; dst->coarse_bin=f; dst->refined_epoch=refined;
        dst->frame_support=support; dst->coarse_cfo_hz=w->frequencies[f];
        dst->fine_cfo_hz=fine; dst->conditioned_cfo_hz=frequencies[best];
        dst->candidate.epoch=refined;
        dst->candidate.coarse_score=retained[r].score;
        dst->candidate.acquired_cfo_hz=frequencies[best];
        dst->candidate.conditioned_score=scores[best];
        stage=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        double verification[3];
        full_verification_scores(w,count,refined,frequencies[best],verification);
        dst->candidate.acquire_score=verification[0];
        dst->candidate.verify_score=verification[1];
        dst->candidate.verify_control_score=verification[2];
        out.verification_cpu_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage;
        ++out.candidate_count;
    }
    for (int i=1; i<out.candidate_count; ++i) {
        leo_full_search_candidate value=out.candidates[i]; int j=i;
        while (j && full_candidate_before(&value,&out.candidates[j-1])) {
            out.candidates[j]=out.candidates[j-1]; --j;
        }
        out.candidates[j]=value;
    }
    out.acquisition_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;

    started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    for (int i=0; i<out.candidate_count; ++i) {
        leo_full_search_candidate *dst=&out.candidates[i];
        double score[3];
        if (glrt(w,count,dst->refined_epoch,dst->candidate.acquired_cfo_hz,
            0,16,1,score)) return -1;
        dst->glrt_complete=1;
        dst->candidate.fractional_complete=0;
        dst->candidate.fractional_offset_samples=0;
        dst->candidate.exact_score=score[0];
        dst->candidate.control_score=score[1];
        dst->candidate.margin=score[0]-score[1];
        dst->candidate.tracking_cfo_hz=dst->candidate.acquired_cfo_hz+score[2];
    }
    out.glrt_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
    out.total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out.total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    *result=out;
    return 0;
}
