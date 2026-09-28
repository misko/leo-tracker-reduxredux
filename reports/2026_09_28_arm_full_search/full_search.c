#define _POSIX_C_SOURCE 200809L
/* Keep the reviewed source immutable while reusing its private FP64 kernels.
 * Compile this file with the frozen native_presence directory on -I and do not
 * also compile presence.c into the same program. */
#include "full_search.h"
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
void leo_fft_forward_range(leo_fft *fft, const double complex *input, size_t used,
    size_t first, size_t count)
{
    (void)used; (void)first; (void)count;
    leo_fft_forward(fft,input);
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

/* The goal40mag snapshot converts the conditioned dot product to float even
 * in its nominal baseline. Restore the earlier reviewed FP64 accumulation. */
static void full_conditioned_scores(leo_presence_workspace *w, size_t count,
    int epoch, const double *frequencies, int nf, double *scores)
{
    double te=0;
    memset(scores,0,(size_t)nf*sizeof(*scores));
    for (size_t k=0; k<w->n; ++k) {
        te+=power(w->exact[k]);
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
        }
        double denom=sqrt(te*energy);
        for (int f=0; f<nf && denom>0; ++f) {
            double complex total=0;
            int regular=frequencies[f]==frequencies[0]+f*100.0;
            for (size_t k=0; k<w->n; ++k)
                total+=w->weighted[k]*(regular ? w->conditioned_offsets[f*w->n+k] :
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
    if (coarse(w,count,NULL)) return -1;
    out.coarse_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;

    size_t capacity=11*w->n;
    leo_full_search_peak *peaks=malloc(capacity*sizeof(*peaks));
    if (!peaks) return -1;
    size_t peak_count=0;
    for (int f=0; f<11; ++f) for (int e=0; e<(int)w->n; ++e) {
        double value=w->grid[f*w->n+e];
        double left=e ? w->grid[f*w->n+e-1] : -INFINITY;
        double right=e+1<(int)w->n ? w->grid[f*w->n+e+1] : -INFINITY;
        if (value>=left && value>=right && (value>left || value>right))
            peaks[peak_count++]=(leo_full_search_peak){value,e,f};
    }
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
        fine_scores(w,count,refined,frequencies[0],nf,scores);
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
        full_conditioned_scores(w,count,refined,frequencies,nf,scores);
        best=best_frequency(scores,frequencies,nf);
        leo_full_search_candidate *dst=&out.candidates[out.candidate_count];
        dst->coarse_epoch=e; dst->coarse_bin=f; dst->refined_epoch=refined;
        dst->frame_support=support; dst->coarse_cfo_hz=w->frequencies[f];
        dst->fine_cfo_hz=fine; dst->conditioned_cfo_hz=frequencies[best];
        dst->candidate.epoch=refined;
        dst->candidate.coarse_score=retained[r].score;
        dst->candidate.acquired_cfo_hz=frequencies[best];
        dst->candidate.conditioned_score=scores[best];
        dst->candidate.acquire_score=normalized_score(w,count,refined,
            frequencies[best],w->exact,2);
        dst->candidate.verify_score=normalized_score(w,count,refined,
            frequencies[best],w->exact,3);
        dst->candidate.verify_control_score=normalized_score(w,count,refined,
            frequencies[best],w->control,3);
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
