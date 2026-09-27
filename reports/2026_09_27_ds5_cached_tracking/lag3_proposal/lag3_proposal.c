#define _POSIX_C_SOURCE 200809L
#include "lag3_proposal.h"

#include <complex.h>
#include <fenv.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define LAG 3u
#define BINS LEO_LAG3_PROPOSAL_BINS
#define WINDOWS 6u
#define FRAME_STARTS 15u
#define TWO_PI 6.283185307179586476925286766559

struct leo_lag3_workspace {
    uint32_t rate;
    size_t n, window;
    uint32_t starts[FRAME_STARTS];
    uint32_t *support;
    int64_t *sum_real, *sum_imag;
    double complex *folded, *projected, *window_folds, *template_centered;
    double template_energy;
    float complex *roots, *fft_work, *fft_scratch, *template_fft;
};

static double clock_ms(clockid_t id)
{
    struct timespec value;
    if (clock_gettime(id,&value)) return 0.0;
    return value.tv_sec*1000.0+value.tv_nsec/1e6;
}

static void fft512(leo_lag3_workspace *w, float complex *values, int inverse)
{
    for (size_t i=0, reversed=0; i<BINS; ++i) {
        w->fft_scratch[reversed]=values[i];
        size_t bit=BINS>>1;
        while (bit && (reversed&bit)) { reversed^=bit; bit>>=1; }
        reversed^=bit;
    }
    for (size_t width=2, stride=BINS>>1; width<=BINS; width<<=1, stride>>=1) {
        size_t half=width>>1;
        for (size_t base=0; base<BINS; base+=width) {
            for (size_t k=0; k<half; ++k) {
                float complex root=inverse ? conjf(w->roots[k*stride]) : w->roots[k*stride];
                float complex even=w->fft_scratch[base+k];
                float complex odd=w->fft_scratch[base+half+k]*root;
                w->fft_scratch[base+k]=even+odd;
                w->fft_scratch[base+half+k]=even-odd;
            }
        }
    }
    float scale=inverse ? 1.0f/(float)BINS : 1.0f;
    for (size_t k=0; k<BINS; ++k) values[k]=w->fft_scratch[k]*scale;
}

static int project(leo_lag3_workspace *w)
{
    double complex mean=0.0;
    for (size_t k=0; k<BINS; ++k) {
        double position=(double)k*w->n/BINS;
        size_t left=(size_t)position;
        size_t right=left+1==w->n ? 0 : left+1;
        double fraction=position-left;
        w->projected[k]=w->folded[left]+fraction*(w->folded[right]-w->folded[left]);
        mean+=w->projected[k];
    }
    mean/=BINS;
    double energy=0.0;
    for (size_t k=0; k<BINS; ++k) {
        w->projected[k]-=mean;
        energy+=creal(w->projected[k])*creal(w->projected[k])+
            cimag(w->projected[k])*cimag(w->projected[k]);
    }
    if (!isfinite(energy) || energy<=0.0) {
        memset(w->fft_work,0,BINS*sizeof(*w->fft_work));
        return energy==0.0 ? 0 : -1;
    }
    double scale=1.0/sqrt(energy);
    if (!isfinite(scale)) return -1;
    for (size_t k=0; k<BINS; ++k)
        w->fft_work[k]=(float)(creal(w->projected[k])*scale)+
            I*(float)(cimag(w->projected[k])*scale);
    return 1;
}

static void fold(leo_lag3_workspace *w, const int16_t *raw, uint32_t receiver)
{
    memset(w->sum_real,0,w->n*sizeof(*w->sum_real));
    memset(w->sum_imag,0,w->n*sizeof(*w->sum_imag));
    for (size_t frame=0; frame<FRAME_STARTS; ++frame) {
        size_t start=w->starts[frame];
        size_t valid=w->window-start-LAG;
        if (valid>w->n) valid=w->n;
        for (size_t k=0; k<valid; ++k) {
            size_t a=4*(start+k)+2*receiver;
            size_t b=a+4*LAG;
            int64_t ar=raw[a], ai=raw[a+1], br=raw[b], bi=raw[b+1];
            w->sum_real[k]+=ar*br+ai*bi;
            w->sum_imag[k]+=ar*bi-ai*br;
        }
    }
    for (size_t k=0; k<w->n; ++k) {
        double support=w->support[k] ? w->support[k] : 1.0;
        w->folded[k]=(double)w->sum_real[k]/support+
            I*((double)w->sum_imag[k]/support);
    }
}

static int better(const leo_lag3_candidate *a, const leo_lag3_candidate *b)
{
    if (a->proposal_score!=b->proposal_score)
        return a->proposal_score>b->proposal_score;
    if (a->window!=b->window) return a->window<b->window;
    return a->projected_bin<b->projected_bin;
}

static void insert_candidate(leo_lag3_result *out, const leo_lag3_candidate *candidate)
{
    uint32_t count=out->candidate_count;
    if (count<LEO_LAG3_PROPOSAL_COUNT) ++out->candidate_count;
    else if (!better(candidate,&out->candidates[count-1])) return;
    uint32_t position=count<LEO_LAG3_PROPOSAL_COUNT ? count : count-1;
    while (position>0 && better(candidate,&out->candidates[position-1])) {
        if (position<LEO_LAG3_PROPOSAL_COUNT)
            out->candidates[position]=out->candidates[position-1];
        --position;
    }
    out->candidates[position]=*candidate;
}

static void refine_phase(leo_lag3_workspace *w, leo_lag3_candidate *candidate)
{
    const double complex *observed=w->window_folds+candidate->window*w->n;
    double complex mean=0.0;
    for (size_t k=0; k<w->n; ++k) mean+=observed[k];
    mean/=w->n;
    double observed_energy=0.0;
    for (size_t k=0; k<w->n; ++k) {
        double complex value=observed[k]-mean;
        observed_energy+=creal(value)*creal(value)+cimag(value)*cimag(value);
    }
    int radius=(int)ceil((double)w->n/(2.0*BINS));
    double best=-1.0;
    double complex best_correlation=0.0;
    uint32_t best_epoch=candidate->integer_epoch;
    if (observed_energy>0.0 && isfinite(observed_energy)) {
        double normalizer=sqrt(observed_energy*w->template_energy);
        for (int offset=-radius; offset<=radius; ++offset) {
            int64_t raw_epoch=(int64_t)candidate->integer_epoch+offset;
            while (raw_epoch<0) raw_epoch+=(int64_t)w->n;
            size_t epoch=(size_t)raw_epoch%w->n;
            double complex correlation=0.0;
            size_t observed_index=epoch;
            for (size_t k=0; k<w->n; ++k) {
                correlation+=(observed[observed_index]-mean)*conj(w->template_centered[k]);
                if (++observed_index==w->n) observed_index=0;
            }
            correlation/=normalizer;
            double magnitude=cabs(correlation);
            if (magnitude>best) {
                best=magnitude; best_correlation=correlation; best_epoch=(uint32_t)epoch;
            }
        }
    }
    candidate->integer_epoch=best_epoch;
    candidate->phase_support_score=best>0.0 ? best : 0.0;
    candidate->correlation_re=creal(best_correlation);
    candidate->correlation_im=cimag(best_correlation);
    candidate->phase_valid=isfinite(candidate->correlation_re) &&
        isfinite(candidate->correlation_im) && candidate->phase_support_score>=0.05;
    candidate->phase_cfo_hz=candidate->phase_valid ?
        atan2(candidate->correlation_im,candidate->correlation_re)*w->rate/(TWO_PI*LAG) : 0.0;
    candidate->in_declared_cfo_range=candidate->phase_valid &&
        fabs(candidate->phase_cfo_hz)<=400000.0;
    candidate->supported=candidate->phase_valid && candidate->in_declared_cfo_range;
}

leo_lag3_workspace *leo_lag3_create(uint32_t rate, const leo_lag3_complex *exact,
    size_t count)
{
    size_t n=(size_t)nearbyint(rate/750.0);
    if (fegetround()!=FE_TONEAREST || (rate!=2500000 && rate!=5000000) ||
        !exact || count!=n) return NULL;
    leo_lag3_workspace *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    w->rate=rate; w->n=n; w->window=rate/50;
#define ALLOC(field, amount) do { w->field=calloc((amount),sizeof(*w->field)); \
    if (!w->field) { leo_lag3_destroy(w); return NULL; } } while (0)
    ALLOC(support,n); ALLOC(sum_real,n); ALLOC(sum_imag,n); ALLOC(folded,n);
    ALLOC(projected,BINS); ALLOC(window_folds,WINDOWS*n); ALLOC(template_centered,n);
    ALLOC(roots,BINS); ALLOC(fft_work,BINS);
    ALLOC(fft_scratch,BINS); ALLOC(template_fft,BINS);
#undef ALLOC
    for (size_t frame=0; frame<FRAME_STARTS; ++frame) {
        w->starts[frame]=(uint32_t)nearbyint(frame*(rate/750.0));
        size_t valid=w->window-w->starts[frame]-LAG;
        if (valid>n) valid=n;
        for (size_t k=0; k<valid; ++k) ++w->support[k];
    }
    for (size_t k=0; k<BINS; ++k) {
        double angle=-TWO_PI*k/BINS;
        w->roots[k]=(float)cos(angle)+I*(float)sin(angle);
    }
    for (size_t k=0; k<n; ++k) {
        size_t next=(k+LAG)%n;
        if (!isfinite(exact[k].re) || !isfinite(exact[k].im) ||
            !isfinite(exact[next].re) || !isfinite(exact[next].im)) {
            leo_lag3_destroy(w); return NULL;
        }
        w->folded[k]=(exact[next].re+I*exact[next].im)*
            (exact[k].re-I*exact[k].im);
    }
    double complex template_mean=0.0;
    for (size_t k=0; k<n; ++k) template_mean+=w->folded[k];
    template_mean/=n;
    for (size_t k=0; k<n; ++k) {
        w->template_centered[k]=w->folded[k]-template_mean;
        w->template_energy+=creal(w->template_centered[k])*creal(w->template_centered[k])+
            cimag(w->template_centered[k])*cimag(w->template_centered[k]);
    }
    if (!(w->template_energy>0.0) || !isfinite(w->template_energy)) {
        leo_lag3_destroy(w); return NULL;
    }
    if (project(w)<=0) { leo_lag3_destroy(w); return NULL; }
    fft512(w,w->fft_work,0);
    memcpy(w->template_fft,w->fft_work,BINS*sizeof(*w->template_fft));
    return w;
}

void leo_lag3_destroy(leo_lag3_workspace *w)
{
    if (!w) return;
    free(w->support); free(w->sum_real); free(w->sum_imag); free(w->folded);
    free(w->projected); free(w->window_folds); free(w->template_centered);
    free(w->roots); free(w->fft_work); free(w->fft_scratch);
    free(w->template_fft); free(w);
}

int leo_lag3_run(leo_lag3_workspace *w, const int16_t *raw, size_t count,
    uint32_t receiver, leo_lag3_result *result)
{
    if (!w || !raw || !result || receiver>1 || count!=WINDOWS*w->window ||
        fegetround()!=FE_TONEAREST) return -1;
    leo_lag3_result out={0};
    out.lag_samples=LAG; out.bins=BINS;
    double total_cpu=clock_ms(CLOCK_THREAD_CPUTIME_ID);
    double total_wall=clock_ms(CLOCK_MONOTONIC);
    for (uint32_t window=0; window<WINDOWS; ++window) {
        double started=clock_ms(CLOCK_THREAD_CPUTIME_ID);
        fold(w,raw+4*window*w->window,receiver);
        memcpy(w->window_folds+window*w->n,w->folded,w->n*sizeof(*w->folded));
        out.fold_cpu_ms+=clock_ms(CLOCK_THREAD_CPUTIME_ID)-started;
        started=clock_ms(CLOCK_THREAD_CPUTIME_ID);
        int status=project(w);
        if (status<0) return -1;
        if (status>0) {
            fft512(w,w->fft_work,0);
            for (size_t k=0; k<BINS; ++k)
                w->fft_work[k]*=conjf(w->template_fft[k]);
            fft512(w,w->fft_work,1);
            double scores[BINS];
            for (size_t k=0; k<BINS; ++k)
                scores[k]=cabsf(w->fft_work[k]);
            for (uint32_t k=0; k<BINS; ++k) {
                size_t left=k ? k-1 : BINS-1, right=k+1==BINS ? 0 : k+1;
                if (!(scores[k]>scores[left] && scores[k]>=scores[right])) continue;
                leo_lag3_candidate candidate={0};
                candidate.window=window;
                candidate.projected_bin=k;
                candidate.integer_epoch=(uint32_t)nearbyint((double)k*w->n/BINS)%w->n;
                candidate.proposal_score=scores[k];
                insert_candidate(&out,&candidate);
            }
        }
        out.correlation_cpu_ms+=clock_ms(CLOCK_THREAD_CPUTIME_ID)-started;
    }
    double phase_started=clock_ms(CLOCK_THREAD_CPUTIME_ID);
    for (uint32_t k=0; k<out.candidate_count; ++k) refine_phase(w,&out.candidates[k]);
    out.correlation_cpu_ms+=clock_ms(CLOCK_THREAD_CPUTIME_ID)-phase_started;
    out.total_cpu_ms=clock_ms(CLOCK_THREAD_CPUTIME_ID)-total_cpu;
    out.total_wall_ms=clock_ms(CLOCK_MONOTONIC)-total_wall;
    *result=out;
    return 0;
}
