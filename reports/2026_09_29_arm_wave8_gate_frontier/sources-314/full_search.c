#define _POSIX_C_SOURCE 200809L
/* Keep the reviewed source immutable while reusing its private FP64 kernels.
 * Compile this file with the frozen native_presence directory on -I and do not
 * also compile presence.c into the same program. */
#include "full_search.h"
#include "conditioned_czt.h"
#include <float.h>
#if defined(__ARM_NEON)
#include <arm_neon.h>
#endif
#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#include "presence.c"
#include "fine_precision.h"
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

#ifndef SKIP_CONDITIONED_RECHECK
#define SKIP_CONDITIONED_RECHECK 0
#endif
#if SKIP_CONDITIONED_RECHECK != 0 && SKIP_CONDITIONED_RECHECK != 1
#error "SKIP_CONDITIONED_RECHECK must be 0 or 1"
#endif
#ifndef LEO_FULL_DIRECT_GLRT
#define LEO_FULL_DIRECT_GLRT 0
#endif
#ifndef LEO_FULL_REFINEMENT_MODE
#define LEO_FULL_REFINEMENT_MODE LEO_FULL_DIRECT_GLRT
#endif
#if LEO_FULL_REFINEMENT_MODE < 0 || LEO_FULL_REFINEMENT_MODE > 2
#error "LEO_FULL_REFINEMENT_MODE must be 0 (full), 1 (coarse direct), or 2 (fine direct)"
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

/* A fourth-order expansion is evaluated around each 32-sample block centre.
 * At 2.5 MS/s and the largest 4 kHz offset, |omega*delta| <= 0.156.  The
 * exponential Taylor tail is below 8e-7 per product.  The screen remains an
 * approximation: the wider guard below sends close bins to the unchanged
 * FP64 dot product before selection. */
#ifndef CONDITIONED_MOMENT_BLOCK
#define CONDITIONED_MOMENT_BLOCK 32
#endif
#define CONDITIONED_MOMENT_MAX_BLOCKS 417
/* Taylor tail <=8e-7.  A 32-term FP32 moment sum has gamma_31~1.9e-6;
 * polynomial/phase rounding is covered by the remaining margin.  Block sums
 * are FP64, so their error does not grow with the number of blocks. */
#define CONDITIONED_MOMENT_GUARD (128.0*FLT_EPSILON)

typedef struct {
    size_t n, blocks;
    double rate;
    /* Block-major layout makes four adjacent frequency phases one contiguous
     * complex load. Frequency powers are rate constants, not block work. */
    float complex phase[CONDITIONED_MOMENT_MAX_BLOCKS][64];
    float omega[64], omega2[64];
} conditioned_moment_phase_cache;
static conditioned_moment_phase_cache conditioned_phase_cache;

static int conditioned_prepare_phases(size_t n, double rate)
{
    size_t blocks=(n+CONDITIONED_MOMENT_BLOCK-1)/CONDITIONED_MOMENT_BLOCK;
    if (!n || !isfinite(rate) || rate<=0 || blocks>CONDITIONED_MOMENT_MAX_BLOCKS)
        return -1;
    if (conditioned_phase_cache.n==n && conditioned_phase_cache.rate==rate) return 0;
    for (int f=0;f<64;++f) {
        double phase_omega=TAU*100.0*f/rate;
        conditioned_phase_cache.omega[f]=(float)phase_omega;
        conditioned_phase_cache.omega2[f]=conditioned_phase_cache.omega[f]*conditioned_phase_cache.omega[f];
        for (size_t block=0;block<blocks;++block) {
            size_t begin=block*CONDITIONED_MOMENT_BLOCK;
            size_t end=begin+CONDITIONED_MOMENT_BLOCK<n ? begin+CONDITIONED_MOMENT_BLOCK:n;
            double center=(double)begin+.5*(double)(end-begin-1);
            conditioned_phase_cache.phase[block][f]=(float complex)rotate(-phase_omega*center);
        }
    }
    conditioned_phase_cache.n=n; conditioned_phase_cache.rate=rate;
    conditioned_phase_cache.blocks=blocks;
    return 0;
}

static __attribute__((unused)) int conditioned_moment_magnitudes_reference(const float *weighted, size_t n,
    double rate, int nf, float magnitudes[64])
{
    if (!weighted || !magnitudes || nf<1 || nf>64 || conditioned_prepare_phases(n,rate)) return -1;
    double complex total[64]; float complex q[64];
    for (int f=0;f<nf;++f) {
        float omega=(float)(TAU*100.0*f/rate);
        q[f]=-I*omega; total[f]=0;
    }
    for (size_t begin=0,block=0;begin<n;begin+=CONDITIONED_MOMENT_BLOCK,++block) {
        size_t end=begin+CONDITIONED_MOMENT_BLOCK<n ? begin+CONDITIONED_MOMENT_BLOCK:n;
        float center=(float)begin+.5f*(float)(end-begin-1);
        float complex moment[3]={0};
        for (size_t k=begin;k<end;++k) {
            float delta=(float)k-center, power_delta=1;
            float complex sample=weighted[2*k]+I*weighted[2*k+1];
            for (int order=0;order<3;++order) {
                moment[order]+=sample*power_delta;
                power_delta*=delta;
            }
        }
        for (int f=0;f<nf;++f) {
            float complex polynomial=moment[0]+q[f]*(moment[1]+q[f]*(.5f*moment[2]));
            total[f]+=(double complex)conditioned_phase_cache.phase[block][f]*(double complex)polynomial;
        }
    }
    for (int f=0;f<nf;++f) magnitudes[f]=(float)magnitude(total[f]);
    return 0;
}

/* This is the approximate regular-grid screen only.  It retains all 16
 * frames, all 41 bins, and every moment.  Four adjacent 100 Hz frequencies
 * share a vector polynomial evaluation and FP32 complex block accumulator.
 * The exact FP64 rechecks and final GLRT remain on their reviewed paths. */
static int conditioned_moment_magnitudes_four_frequency(const float *weighted, size_t n,
    double rate, int nf, float magnitudes[64])
{
    if (!weighted || !magnitudes || nf<1 || nf>64 || conditioned_prepare_phases(n,rate)) return -1;
    float totals_re[64]={0},totals_im[64]={0};
    for (size_t begin=0,block=0;begin<n;begin+=CONDITIONED_MOMENT_BLOCK,++block) {
        size_t end=begin+CONDITIONED_MOMENT_BLOCK<n ? begin+CONDITIONED_MOMENT_BLOCK:n;
        float center=(float)begin+.5f*(float)(end-begin-1);
        float complex moment[3]={0};
        for (size_t k=begin;k<end;++k) {
            float delta=(float)k-center,power_delta=1;
            float complex sample=weighted[2*k]+I*weighted[2*k+1];
            for (int order=0;order<3;++order) { moment[order]+=sample*power_delta; power_delta*=delta; }
        }
        int f=0;
#if defined(__ARM_NEON)
        for (;f+3<nf;f+=4) {
            float32x4_t omega=vld1q_f32(conditioned_phase_cache.omega+f);
            float32x4_t omega2=vld1q_f32(conditioned_phase_cache.omega2+f);
            float32x4_t pr=vdupq_n_f32(crealf(moment[0])),pi=vdupq_n_f32(cimagf(moment[0]));
            pr=vaddq_f32(pr,vmulq_n_f32(omega,cimagf(moment[1])));
            pi=vsubq_f32(pi,vmulq_n_f32(omega,crealf(moment[1])));
            pr=vsubq_f32(pr,vmulq_n_f32(omega2,.5f*crealf(moment[2])));
            pi=vsubq_f32(pi,vmulq_n_f32(omega2,.5f*cimagf(moment[2])));
            float32x4x2_t phase=vld2q_f32((const float *)(conditioned_phase_cache.phase[block]+f));
            float32x4_t ar=phase.val[0],ai=phase.val[1];
            float32x4_t tr=vaddq_f32(vld1q_f32(totals_re+f),vsubq_f32(vmulq_f32(ar,pr),vmulq_f32(ai,pi)));
            float32x4_t ti=vaddq_f32(vld1q_f32(totals_im+f),vaddq_f32(vmulq_f32(ar,pi),vmulq_f32(ai,pr)));
            vst1q_f32(totals_re+f,tr); vst1q_f32(totals_im+f,ti);
        }
#endif
        for (;f<nf;++f) {
            float omega=conditioned_phase_cache.omega[f],omega2=conditioned_phase_cache.omega2[f];
            float pr=crealf(moment[0])+omega*cimagf(moment[1])-.5f*omega2*crealf(moment[2]);
            float pi=cimagf(moment[0])-omega*crealf(moment[1])-.5f*omega2*cimagf(moment[2]);
            float complex phase=conditioned_phase_cache.phase[block][f];
            totals_re[f]+=crealf(phase)*pr-cimagf(phase)*pi;
            totals_im[f]+=crealf(phase)*pi+cimagf(phase)*pr;
        }
    }
    for (int f=0;f<nf;++f) magnitudes[f]=hypotf(totals_re[f],totals_im[f]);
    return 0;
}

static int conditioned_moment_magnitudes(const float *weighted, size_t n,
    double rate, int nf, float magnitudes[64])
{
#if defined(LEO_NEON_CONDITIONED_MOMENTS)
    return conditioned_moment_magnitudes_four_frequency(weighted,n,rate,nf,magnitudes);
#else
    return conditioned_moment_magnitudes_reference(weighted,n,rate,nf,magnitudes);
#endif
}

static __attribute__((unused)) double conditioned_screen_guard(void)
{
    return CONDITIONED_MOMENT_GUARD;
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
        float moment_magnitudes[64];
        int regular=nf>0 && nf<=64;
        for (int f=0; f<nf && regular; ++f)
            regular=frequencies[f]==frequencies[0]+f*100.0;
        int moment_ok=approximate && denom>0 && regular;
        if (moment_ok) moment_ok=!conditioned_moment_magnitudes(w->opt_weighted,w->n,w->rate,nf,
            moment_magnitudes);
        for (int f=0; f<nf && denom>0; ++f) {
            double complex total=0;
            int bin_regular=frequencies[f]==frequencies[0]+f*100.0;
            if (moment_ok) {
                scores[f]+=moment_magnitudes[f]/denom;
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

#if LEO_FULL_REFINEMENT_MODE == 0
static int full_candidate_before(const leo_full_search_candidate *a,
    const leo_full_search_candidate *b)
{
    return candidate_before(&a->candidate,&b->candidate);
}
#endif

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

static int boundary_margin_allowed(double exact, double control)
{
    double margin=exact-control;
    return !isfinite(margin) || margin >= 0.1;
}

static int boundary_fallback_required(double residual)
{
    const double boundary=1.0/(2.0*SYMBOL_S);
    return isfinite(residual)&&fabs(fabs(residual)-boundary)<=1000.0;
}

/* Exploratory thresholds selected on the frozen Wave4 cohort.  This helper
 * depends solely on sample rate and the already-computed coarse score. */
static double coarse_score_threshold(uint32_t rate)
{
    switch (rate) {
    case 2500000: return 0.314;
    case 5000000: return 0.150;
    case 7500000: return 0.175;
    case 10000000: return 0.152;
    default: return INFINITY;
    }
}

static int coarse_score_allowed(uint32_t rate, double score)
{
    return isfinite(score) && score >= coarse_score_threshold(rate);
}

typedef struct {
    int count;
    struct {int epoch;size_t sample_count;uint64_t cfo_bits;double score[3];} entries[16];
} final_glrt_cache;

typedef struct {
    int count;
    struct {
        int epoch;size_t sample_count;uint64_t cfo_bits;
        double winner,winner_score;
        int bins_screened,bins_rechecked;
    } entries[LEO_FULL_SEARCH_MAX_CANDIDATES];
} final_conditioned_cache;

static uint64_t final_cfo_bits(double cfo)
{
    uint64_t bits;memcpy(&bits,&cfo,sizeof(bits));return bits;
}

static int final_cached_glrt(final_glrt_cache *cache,leo_presence_workspace *w,
    size_t count,int epoch,double cfo,double result[3],leo_full_search_result *out)
{
    uint64_t bits=final_cfo_bits(cfo);
    for(int i=0;i<cache->count;++i) if(cache->entries[i].epoch==epoch&&
        cache->entries[i].sample_count==count&&cache->entries[i].cfo_bits==bits) {
        memcpy(result,cache->entries[i].score,sizeof(cache->entries[i].score));
        ++out->glrt_cache_hits;return 0;
    }
    double stage=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    if(glrt(w,count,epoch,cfo,0,16,1,result))return -1;
    out->glrt_cpu_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage;
    ++out->actual_executed_glrt_calls;
    if(cache->count<(int)(sizeof(cache->entries)/sizeof(cache->entries[0]))) {
        int slot=cache->count++;cache->entries[slot].epoch=epoch;
        cache->entries[slot].sample_count=count;cache->entries[slot].cfo_bits=bits;
        memcpy(cache->entries[slot].score,result,sizeof(cache->entries[slot].score));
    }
    return 0;
}

static void boundary_conditioned(leo_presence_workspace *w,size_t count,int epoch,
    double center,double *winner,double *winner_score,leo_full_search_result *out)
{
    double frequencies[64],scores[64];
    int nf=grid(fmax(-400000,center-2000),fmin(400000,center+2000),100,frequencies);
    double stage=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    full_conditioned_scores(w,count,epoch,frequencies,nf,scores,1);
    double maximum=scores[best_frequency(scores,frequencies,nf)];
    out->conditioned_bins_screened+=nf;
#if !SKIP_CONDITIONED_RECHECK
    const double guard=conditioned_screen_guard();
    for(int q=0;q<nf;++q) {
        if(!isfinite(scores[q])||scores[q]>=maximum-2*guard) {
            full_conditioned_scores(w,count,epoch,frequencies+q,1,scores+q,0);
            ++out->conditioned_bins_rechecked;
        } else scores[q]=-INFINITY;
    }
#else
    (void)maximum;
#endif
    out->conditioned_cpu_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage;
    int best=best_frequency(scores,frequencies,nf);
    *winner=frequencies[best];*winner_score=scores[best];
}

static void final_cached_boundary(final_conditioned_cache *cache,
    leo_presence_workspace *w,size_t count,int epoch,double center,
    double *winner,double *winner_score,leo_full_search_result *out)
{
    uint64_t bits=final_cfo_bits(center);
    for(int i=0;i<cache->count;++i) if(cache->entries[i].epoch==epoch&&
        cache->entries[i].sample_count==count&&cache->entries[i].cfo_bits==bits) {
        *winner=cache->entries[i].winner;*winner_score=cache->entries[i].winner_score;
        out->conditioned_bins_screened+=cache->entries[i].bins_screened;
        out->conditioned_bins_rechecked+=cache->entries[i].bins_rechecked;
        ++out->conditioned_cache_hits;return;
    }
    int screened=out->conditioned_bins_screened,rechecked=out->conditioned_bins_rechecked;
    boundary_conditioned(w,count,epoch,center,winner,winner_score,out);
    if(cache->count<(int)(sizeof(cache->entries)/sizeof(cache->entries[0]))) {
        int slot=cache->count++;cache->entries[slot].epoch=epoch;
        cache->entries[slot].sample_count=count;cache->entries[slot].cfo_bits=bits;
        cache->entries[slot].winner=*winner;cache->entries[slot].winner_score=*winner_score;
        cache->entries[slot].bins_screened=out->conditioned_bins_screened-screened;
        cache->entries[slot].bins_rechecked=out->conditioned_bins_rechecked-rechecked;
    }
}

static size_t collect_active_peaks(const leo_presence_workspace *w,
    const int *epochs,int epoch_count,leo_full_search_peak *peaks)
{
    size_t count=0;
    for(int f=0;f<11;++f)for(int i=0;i<epoch_count;++i){int e=epochs[i];double value=w->grid[f*w->n+e];double left=e?w->grid[f*w->n+e-1]:-INFINITY;double right=e+1<(int)w->n?w->grid[f*w->n+e+1]:-INFINITY;if(value>=left&&value>=right&&(value>left||value>right))peaks[count++]=(leo_full_search_peak){value,e,f};}
    return count;
}

static int leo_full_search_run_ingested(leo_presence_workspace *w,size_t count,
    leo_full_search_result *result,double cpu,double wall,double conversion_cpu_ms)
{
    if (!result) return -1;
    leo_full_search_result out={0};
    /* Frozen acquisition always starts at the first complete frame. Clear
     * experimental support state in case this workspace was previously used
     * by another research entry point. */
    w->acquisition_first_frame=0;
    w->acquisition_regions[0]=w->acquisition_regions[1]=0;
    out.conversion_cpu_ms=conversion_cpu_ms;
    double started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    if (coarse(w,count,NULL)) return -1;
    out.coarse_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;

    size_t capacity=11*(size_t)regional_count;
    leo_full_search_peak *peaks=capacity?malloc(capacity*sizeof(*peaks)):NULL;
    if(capacity&&!peaks)return -1;
    size_t peak_count=collect_active_peaks(w,regional_epochs,regional_count,peaks);
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
    leo_fine_precision_cache fine_cache;
    if (leo_fine_precision_init(&fine_cache,w->fine_fft.size)) return -1;
    for (size_t r=0; r<nr; ++r) {
        int e=retained[r].epoch, f=retained[r].coarse_bin, refined=e;
        for (int local=e-1; local<=e+1; ++local)
            if (local>=0 && local<(int)w->n &&
                (w->grid[f*w->n+local]>w->grid[f*w->n+refined] ||
                (w->grid[f*w->n+local]==w->grid[f*w->n+refined] && local<refined)))
                refined=local;
        int support=full_frame_support(w,count,refined);
        if (support<2) continue;
        if (!coarse_score_allowed((uint32_t)w->rate,retained[r].score)) {
            ++out.coarse_gate_skipped_count;
            continue;
        }
        leo_full_search_candidate *dst=&out.candidates[out.candidate_count];
        dst->coarse_epoch=e; dst->coarse_bin=f; dst->refined_epoch=refined;
        dst->frame_support=support; dst->coarse_cfo_hz=w->frequencies[f];
        dst->candidate.epoch=refined;
        dst->candidate.coarse_score=retained[r].score;
#if LEO_FULL_REFINEMENT_MODE == 1
        /* Bounded approximate experiment: GLRT itself searches residual CFO.
         * Keep every retained hypothesis but do not fabricate skipped
         * refinement scores or CFOs. */
        dst->refinement_skipped=1;
        dst->candidate.acquired_cfo_hz=w->frequencies[f];
        ++out.candidate_count;
        continue;
#endif
        double frequencies[2048], scores[2048];
        double lower=fmax(-400000,w->frequencies[f]-80000);
        double upper=fmin(400000,w->frequencies[f]+80000);
        int nf=grid(lower,upper,w->fine_step_hz,frequencies);
        double stage=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        if (leo_fine_precision_scores(w,count,refined,frequencies[0],nf,scores,&fine_cache)) {
            leo_fine_precision_free(&fine_cache); return -1;
        }
        out.fine_fft_cpu_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage;
        int best=best_frequency(scores,frequencies,nf);
        double fine=frequencies[best], interpolated=fine;
        if (best>0 && best+1<nf) {
            double curve=scores[best-1]-2*scores[best]+scores[best+1];
            if (isfinite(curve) && curve<-1e-15)
                interpolated+=fmax(-w->fine_step_hz,fmin(w->fine_step_hz,
                    .5*(scores[best-1]-scores[best+1])/curve*w->fine_step_hz));
        }
#if LEO_FULL_REFINEMENT_MODE == 2
        /* Bounded approximate experiment: retain the original fine FFT and
         * interpolation, then give its CFO directly to final GLRT. */
        dst->refinement_skipped=1;
        dst->fine_cfo_hz=fine;
        dst->candidate.acquired_cfo_hz=interpolated;
        ++out.candidate_count;
        continue;
#endif
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
        out.conditioned_bins_screened+=nf;
#if !SKIP_CONDITIONED_RECHECK
        const double guard=conditioned_screen_guard();
        for (int q=0;q<nf;++q) {
            if (!isfinite(scores[q]) || scores[q]>=maximum-2*guard) {
                full_conditioned_scores(w,count,refined,frequencies+q,1,scores+q,0);
                ++out.conditioned_bins_rechecked;
            } else scores[q]=-INFINITY;
        }
#else
        (void)maximum;
#endif
#else
        full_conditioned_scores(w,count,refined,frequencies,nf,scores,0);
        out.conditioned_bins_rechecked+=nf;
#endif
        out.conditioned_cpu_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage;
        best=best_frequency(scores,frequencies,nf);
        dst->fine_cfo_hz=fine; dst->conditioned_cfo_hz=frequencies[best];
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
#if LEO_FULL_REFINEMENT_MODE == 0
    for (int i=1; i<out.candidate_count; ++i) {
        leo_full_search_candidate value=out.candidates[i]; int j=i;
        while (j && full_candidate_before(&value,&out.candidates[j-1])) {
            out.candidates[j]=out.candidates[j-1]; --j;
        }
        out.candidates[j]=value;
    }
#endif
    out.fine_fft_cache_entries=fine_cache.count;
    out.fine_fft_cache_hits=fine_cache.hits;
    out.fine_precision_calls=fine_cache.calls;
    out.fine_precision_guard_checks=fine_cache.guard_checks;
    out.fine_precision_fallbacks=fine_cache.fallbacks;
    out.fine_precision_nonfinite_fallbacks=fine_cache.nonfinite_fallbacks;
    out.fine_precision_near_tie_fallbacks=fine_cache.near_tie_fallbacks;
    out.fine_precision_interpolation_fallbacks=fine_cache.interpolation_fallbacks;
    leo_fine_precision_free(&fine_cache);
    out.acquisition_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;

    final_glrt_cache glrt_cache={0};
    final_conditioned_cache conditioned_cache={0};
    for (int i=0; i<out.candidate_count; ++i) {
        leo_full_search_candidate *dst=&out.candidates[i];
        double score[3];
        if (final_cached_glrt(&glrt_cache,w,count,dst->refined_epoch,
            dst->candidate.acquired_cfo_hz,score,&out)) return -1;
        dst->glrt_complete=1;
        dst->candidate.fractional_complete=0;
        dst->candidate.fractional_offset_samples=0;
        dst->candidate.exact_score=score[0];
        dst->candidate.control_score=score[1];
        dst->candidate.margin=score[0]-score[1];
        dst->candidate.tracking_cfo_hz=dst->candidate.acquired_cfo_hz+score[2];
#if LEO_FULL_REFINEMENT_MODE == 2
        if(boundary_fallback_required(score[2]) && boundary_margin_allowed(score[0],score[1])) {
            double conditioned_cfo,conditioned_score;
            final_cached_boundary(&conditioned_cache,w,count,dst->refined_epoch,
                dst->candidate.acquired_cfo_hz,&conditioned_cfo,&conditioned_score,&out);
            dst->conditioned_fallback=1;
            dst->conditioned_cfo_hz=conditioned_cfo;
            dst->candidate.conditioned_score=conditioned_score;
            dst->candidate.acquired_cfo_hz=conditioned_cfo;
            ++out.conditioned_fallback_count;
            if(final_cached_glrt(&glrt_cache,w,count,dst->refined_epoch,
                conditioned_cfo,score,&out))return -1;
            dst->candidate.exact_score=score[0];dst->candidate.control_score=score[1];
            dst->candidate.margin=score[0]-score[1];
            dst->candidate.tracking_cfo_hz=conditioned_cfo+score[2];
        }
#endif
    }
    out.total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out.total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    *result=out;
    return 0;
}

int leo_full_search_run(leo_presence_workspace *w,const leo_presence_complex *samples,
    size_t count,leo_full_search_result *result)
{double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID),wall=clock_ms(CLOCK_MONOTONIC);if(ingest(w,samples,count))return -1;return leo_full_search_run_ingested(w,count,result,cpu,wall,clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu);}

int leo_full_search_run_ci16(leo_presence_workspace *w,const int16_t *samples,size_t scalar_stride,size_t count,leo_full_search_result *result)
{double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID),wall=clock_ms(CLOCK_MONOTONIC);if(w){w->coarse_input_prepared=0;w->coarse_prepared_count=0;}if(!w||!samples||!result||scalar_stride<2||fegetround()!=FE_TONEAREST||count<(size_t)ceil(w->rate/375.0)||count>w->max_samples||(count&&(count-1)>(SIZE_MAX-1)/scalar_stride))return -1;w->prefix[0]=0;for(size_t k=0;k<count;k++){double real=(double)samples[k*scalar_stride],imag=(double)samples[k*scalar_stride+1];w->samples[k]=real+I*imag;real/=32768.0;imag/=32768.0;w->float_samples[2*k]=(float)real;w->float_samples[2*k+1]=(float)imag;w->prefix[k+1]=w->prefix[k]+real*real+imag*imag;}w->coarse_input_prepared=1;w->coarse_prepared_count=count;return leo_full_search_run_ingested(w,count,result,cpu,wall,clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu);}

int leo_full_search_run_prepared(leo_presence_workspace *w,
    const double complex *raw,const float *normalized,const double *prefix,
    size_t count,leo_full_search_result *result)
{
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID),wall=clock_ms(CLOCK_MONOTONIC);
    if(w){w->coarse_input_prepared=0;w->coarse_prepared_count=0;}
    if(!w||!raw||!normalized||!prefix||!result||fegetround()!=FE_TONEAREST||
       count<(size_t)ceil(w->rate/375.0)||count>w->max_samples)return -1;
    double complex *owned_samples=w->samples;
    float *owned_float_samples=w->float_samples;
    double *owned_prefix=w->prefix;
    w->samples=(double complex *)raw;
    w->float_samples=(float *)normalized;
    w->prefix=(double *)prefix;
    w->coarse_input_prepared=1;w->coarse_prepared_count=count;
    int status=leo_full_search_run_ingested(w,count,result,cpu,wall,0);
    w->samples=owned_samples;w->float_samples=owned_float_samples;
    w->prefix=owned_prefix;w->coarse_input_prepared=0;w->coarse_prepared_count=0;
    return status;
}
