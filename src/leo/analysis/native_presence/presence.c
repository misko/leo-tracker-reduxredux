#define _POSIX_C_SOURCE 200809L
#include "presence.h"
#include "fft.h"
#include <complex.h>
#include <float.h>
#include <fenv.h>
#include <math.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define TAU 6.283185307179586476925286766559
#define SYMBOL_S 4.4e-6
#define CFO_COUNT 12

/* The exact existing acquisition kernel, with platform-independent C types. */
typedef double complex npy_cdouble;
typedef ptrdiff_t npy_intp;
typedef int32_t npy_int32;
typedef struct {
    const npy_cdouble *samples, *references;
    const double *frequencies;
    const npy_intp *starts, *stops, *offsets;
    const double *prefix;
    double *scores, *accumulated;
    npy_int32 *support;
    double *correlation_real, *correlation_imag, *rotated_real, *rotated_imag;
    npy_intp sample_count, cfo_count, symbol_count, offset_count;
    double sample_rate_hz;
    int epoch_count, fast_magnitude, invalid_geometry;
} FoldedAnchorGridKernel;

/* Four frequency lanes fit in scalar ARM FP registers. The generic kernel's
 * tap-major array updates otherwise repeatedly spill all twelve complex sums.
 * Arithmetic and per-frequency summation order remain unchanged. */
static void correlate_registers(const double complex *restrict samples,
    const double *restrict real, const double *restrict imag, ptrdiff_t count,
    double *restrict out_real, double *restrict out_imag)
{
    for (int f = 0; f < CFO_COUNT; f += 4) {
        double r0=0, i0=0, r1=0, i1=0, r2=0, i2=0, r3=0, i3=0;
        for (ptrdiff_t k = 0; k < count; ++k) {
            double xr=creal(samples[k]), xi=cimag(samples[k]);
            ptrdiff_t base=k*CFO_COUNT+f;
#define ACCUMULATE(lane) do { \
    double rr=real[base+lane], ri=imag[base+lane]; \
    r##lane += xr*rr+xi*ri; \
    i##lane += xi*rr-xr*ri; \
} while (0)
            ACCUMULATE(0); ACCUMULATE(1); ACCUMULATE(2); ACCUMULATE(3);
#undef ACCUMULATE
        }
        out_real[f]=r0; out_imag[f]=i0;
        out_real[f+1]=r1; out_imag[f+1]=i1;
        out_real[f+2]=r2; out_imag[f+2]=i2;
        out_real[f+3]=r3; out_imag[f+3]=i3;
    }
}

#define LEO_GRID_FUNCTION presence_grid_portable
#define LEO_GRID_TARGET
#define LEO_GRID_CORRELATE correlate_registers
#include "../starlink/_native_acquisition_grid.inc"
#undef LEO_GRID_FUNCTION
#undef LEO_GRID_TARGET
#undef LEO_GRID_CORRELATE
#if defined(__GNUC__) && (defined(__x86_64__) || defined(__i386__)) && !defined(LEO_PRESENCE_FORCE_PORTABLE)
#define LEO_GRID_FUNCTION presence_grid_avx2
#define LEO_GRID_TARGET __attribute__((target("avx2,fma,tune=haswell")))
#include "../starlink/_native_acquisition_grid.inc"
#undef LEO_GRID_FUNCTION
#undef LEO_GRID_TARGET
#endif

struct leo_presence_workspace {
    uint32_t rate;
    size_t n, max_samples;
    double complex *exact, *control, *samples, *input, *weighted, *base;
    double complex *conditioned_offsets;
    double *prefix, *grid, *accumulated, *rotated_real, *rotated_imag;
    int32_t *support;
    npy_intp starts[12], stops[12], offsets[16];
    double frequencies[12], correlation_real[12], correlation_imag[12];
    leo_fft fine_fft, short_fft, glrt_fft;
};

static double clock_ms(clockid_t id)
{
    struct timespec ts;
    if (clock_gettime(id, &ts)) return 0.0;
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}
static double power(double complex x) { return creal(x)*creal(x) + cimag(x)*cimag(x); }
static double complex rotate(double angle) { return cos(angle) + I * sin(angle); }
static int frame_start(const leo_presence_workspace *w, int epoch, int frame)
{ return epoch + (int)nearbyint(frame * (w->rate / 750.0)); }

void leo_presence_destroy(leo_presence_workspace *w)
{
    if (!w) return;
    free(w->exact); free(w->control); free(w->samples); free(w->input);
    free(w->weighted); free(w->base); free(w->conditioned_offsets);
    free(w->prefix); free(w->grid); free(w->accumulated); free(w->support);
    free(w->rotated_real); free(w->rotated_imag);
    leo_fft_free(&w->fine_fft); leo_fft_free(&w->short_fft); leo_fft_free(&w->glrt_fft);
    free(w);
}

leo_presence_workspace *leo_presence_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control, size_t n)
{
    if (fegetround() != FE_TONEAREST || (rate != 2500000 && rate != 5000000) || !exact || !control ||
        n != (size_t)nearbyint(rate / 750.0)) return NULL;
    leo_presence_workspace *w = calloc(1, sizeof(*w));
    if (!w) return NULL;
    w->rate = rate; w->n = n; w->max_samples = rate / 50;
#define ALLOC(field, count) do { \
    w->field = calloc((count), sizeof(*w->field)); \
    if (!w->field) { leo_presence_destroy(w); return NULL; } \
} while (0)
    ALLOC(exact, n); ALLOC(control, n); ALLOC(samples, w->max_samples);
    ALLOC(input, rate / 500); ALLOC(weighted, n); ALLOC(base, n);
    ALLOC(conditioned_offsets, 42 * n); ALLOC(prefix, w->max_samples + 1);
    ALLOC(grid, CFO_COUNT * n); ALLOC(accumulated, CFO_COUNT * n); ALLOC(support, n);
    ALLOC(rotated_real, CFO_COUNT * 23); ALLOC(rotated_imag, CFO_COUNT * 23);
#undef ALLOC
    if (leo_fft_init(&w->fine_fft, rate / 500) ||
        leo_fft_init(&w->short_fft, 128) || leo_fft_init(&w->glrt_fft, 512)) {
        leo_presence_destroy(w); return NULL;
    }
    for (size_t k = 0; k < n; ++k) {
        if (!isfinite(exact[k].re) || !isfinite(exact[k].im) ||
            !isfinite(control[k].re) || !isfinite(control[k].im)) {
            leo_presence_destroy(w); return NULL;
        }
        w->exact[k] = exact[k].re + I * exact[k].im;
        w->control[k] = control[k].re + I * control[k].im;
        for (size_t f = 0; f < 42; ++f)
            w->conditioned_offsets[f*n+k] = rotate(-TAU * (f * 100.0) * k / rate);
    }
    for (int k = 0; k < 12; ++k) {
        w->starts[k] = (npy_intp)nearbyint((2 + k * 26) * rate * SYMBOL_S);
        w->stops[k] = (npy_intp)nearbyint((3 + k * 26) * rate * SYMBOL_S);
        w->frequencies[k] = -400000.0 + k * 80000.0;
    }
    for (int k = 0; k < 16; ++k) w->offsets[k] = frame_start(w, 0, k);
    return w;
}

static int ingest(leo_presence_workspace *w, const leo_presence_complex *x, size_t count)
{
    if (!w || !x || count < (size_t)ceil(w->rate / 375.0) || count > w->max_samples)
        return -1;
    for (size_t k = 0; k < count; ++k) {
        if (!isfinite(x[k].re) || !isfinite(x[k].im) ||
            fabs(x[k].re) > 1e12 || fabs(x[k].im) > 1e12) return -1;
        w->samples[k] = x[k].re + I*x[k].im;
    }
    return 0;
}

static void coarse(leo_presence_workspace *w, size_t count)
{
    w->prefix[0] = 0.0;
    for (size_t k = 0; k < count; ++k) w->prefix[k+1] = w->prefix[k] + power(w->samples[k]);
    memset(w->accumulated, 0, CFO_COUNT * w->n * sizeof(double));
    memset(w->support, 0, w->n * sizeof(int32_t));
    int frames = 0;
    while (frames < 16 && w->offsets[frames] < (ptrdiff_t)count) ++frames;
    FoldedAnchorGridKernel kernel = {
        .samples=w->samples, .references=w->exact, .frequencies=w->frequencies,
        .starts=w->starts, .stops=w->stops, .offsets=w->offsets, .prefix=w->prefix,
        .scores=w->grid, .accumulated=w->accumulated, .support=w->support,
        .correlation_real=w->correlation_real, .correlation_imag=w->correlation_imag,
        .rotated_real=w->rotated_real, .rotated_imag=w->rotated_imag,
        .sample_count=(ptrdiff_t)count, .cfo_count=CFO_COUNT, .symbol_count=12,
        .offset_count=frames, .sample_rate_hz=w->rate, .epoch_count=(int)w->n,
        .fast_magnitude=1
    };
#if defined(__GNUC__) && (defined(__x86_64__) || defined(__i386__)) && !defined(LEO_PRESENCE_FORCE_PORTABLE)
    __builtin_cpu_init();
    if (__builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma"))
        presence_grid_avx2(&kernel);
    else
#endif
        presence_grid_portable(&kernel);
}

int leo_presence_coarse(leo_presence_workspace *w, const leo_presence_complex *x,
    size_t count, double *scores)
{
    if (!scores || ingest(w, x, count)) return -1;
    coarse(w, count);
    memcpy(scores, w->grid, 11 * w->n * sizeof(double));
    return 0;
}

static int grid(double start, double stop, double step, double *out)
{
    int n = (int)floor((stop-start)/step + 1e-12) + 1;
    for (int k = 0; k < n; ++k) out[k] = start + k*step;
    if (fabs(out[n-1]-stop) > 1e-9) out[n++] = stop;
    return n;
}
static int best_frequency(const double *scores, const double *frequencies, int n)
{
    int best = 0;
    for (int k = 1; k < n; ++k)
        if (scores[k] > scores[best] || (scores[k] == scores[best] &&
            (fabs(frequencies[k]) < fabs(frequencies[best]) ||
             (fabs(frequencies[k]) == fabs(frequencies[best]) && frequencies[k] < frequencies[best]))))
            best = k;
    return best;
}

/* Normalized coherent even-symbol fine acquisition, evaluated by sparse FFT. */
static void fine_scores(leo_presence_workspace *w, size_t count, int epoch,
    double first_frequency, int frequency_count, double *scores)
{
    size_t last = (size_t)nearbyint(301 * w->rate * SYMBOL_S) - 1;
    double template_energy = 0;
    memset(w->base, 0, w->n * sizeof(*w->base));
    memset(scores, 0, frequency_count * sizeof(*scores));
    for (int symbol = 2; symbol < 302; symbol += 2) {
        int begin = (int)nearbyint(symbol * w->rate * SYMBOL_S);
        int end = (int)nearbyint((symbol+1) * w->rate * SYMBOL_S);
        for (int k = begin; k < end; ++k) {
            template_energy += power(w->exact[k]);
            w->base[k] = conj(w->exact[k]) * rotate(-TAU*first_frequency*k/w->rate);
        }
    }
    int frames = 0;
    for (int frame = 0; ; ++frame) {
        int start = frame_start(w, epoch, frame);
        if ((size_t)start + last >= count) break;
        memset(w->input, 0, w->fine_fft.size * sizeof(*w->input));
        double energy = 0;
        for (int symbol = 2; symbol < 302; symbol += 2) {
            int begin = (int)nearbyint(symbol * w->rate * SYMBOL_S);
            int end = (int)nearbyint((symbol+1) * w->rate * SYMBOL_S);
            for (int k = begin; k < end; ++k) {
                energy += power(w->samples[start+k]);
                w->input[k] = w->samples[start+k] * w->base[k];
            }
        }
        leo_fft_forward(&w->fine_fft, w->input);
        double denom = sqrt(template_energy * energy);
        if (denom > 0)
            for (int f = 0; f < frequency_count; ++f) scores[f] += cabs(w->fine_fft.output[f])/denom;
        ++frames;
    }
    if (frames) for (int f = 0; f < frequency_count; ++f) scores[f] /= frames;
}

static void conditioned_scores(leo_presence_workspace *w, size_t count, int epoch,
    const double *frequencies, int nf, double *scores)
{
    double te = 0;
    memset(scores, 0, nf * sizeof(*scores));
    for (size_t k = 0; k < w->n; ++k) {
        te += power(w->exact[k]);
        w->base[k] = conj(w->exact[k]) * rotate(-TAU*frequencies[0]*k/w->rate);
    }
    int frames = 0;
    for (int frame = 0; ; ++frame) {
        int start = frame_start(w, epoch, frame);
        if ((size_t)start + w->n > count) break;
        double energy = 0;
        for (size_t k = 0; k < w->n; ++k) {
            energy += power(w->samples[start+k]);
            w->weighted[k] = w->samples[start+k] * w->base[k];
        }
        double denom = sqrt(te*energy);
        for (int f = 0; f < nf && denom > 0; ++f) {
            double complex total = 0;
            int regular = frequencies[f] == frequencies[0] + f*100.0;
            for (size_t k = 0; k < w->n; ++k)
                total += w->weighted[k] * (regular ? w->conditioned_offsets[f*w->n+k] :
                    rotate(-TAU*(frequencies[f]-frequencies[0])*k/w->rate));
            scores[f] += cabs(total)/denom;
        }
        ++frames;
    }
    if (frames) for (int f = 0; f < nf; ++f) scores[f] /= frames;
}

static double normalized_score(leo_presence_workspace *w, size_t count, int epoch,
    double cfo, const double complex *reference, int first_symbol)
{
    double te = 0, score = 0;
    size_t last = (size_t)nearbyint((first_symbol == 2 ? 301 : 302)*w->rate*SYMBOL_S)-1;
    for (int symbol = first_symbol; symbol < 302; symbol += 2) {
        int begin = (int)nearbyint(symbol*w->rate*SYMBOL_S);
        int end = (int)nearbyint((symbol+1)*w->rate*SYMBOL_S);
        for (int k = begin; k < end; ++k) {
            te += power(reference[k]);
            w->base[k] = conj(reference[k]) * rotate(-TAU*cfo*k/w->rate);
        }
    }
    int frames = 0;
    for (int frame = 0; ; ++frame) {
        int start = frame_start(w, epoch, frame);
        if ((size_t)start + last >= count) break;
        double energy = 0; double complex total = 0;
        for (int symbol = first_symbol; symbol < 302; symbol += 2) {
            int begin = (int)nearbyint(symbol*w->rate*SYMBOL_S);
            int end = (int)nearbyint((symbol+1)*w->rate*SYMBOL_S);
            for (int k = begin; k < end; ++k) {
                total += w->samples[start+k]*w->base[k];
                energy += power(w->samples[start+k]);
            }
        }
        double denom = sqrt(te*energy);
        if (denom > 0) score += cabs(total)/denom;
        ++frames;
    }
    return frames ? score/frames : 0;
}

static double sinc(double x) { return x == 0 ? 1 : sin(TAU*0.5*x)/(TAU*0.5*x); }

static int glrt(leo_presence_workspace *w, size_t count, int epoch,
    double cfo, double offset, double result[3])
{
    if (epoch < 0 || epoch >= (int)w->n || !isfinite(cfo) || !isfinite(offset) || fabs(offset)>2)
        return -1;
    double spectra[2][128] = {{0}}, ceilings[2] = {0};
    int integer = fabs(offset-nearbyint(offset)) <= 1e-12;
    int first = (int)nearbyint(2*w->rate*SYMBOL_S);
    int stop = (int)nearbyint(66*w->rate*SYMBOL_S);
    /* Rotation depends on local sample position, never on the frame number.
     * Keep the original arithmetic and reuse it across every supporting frame. */
    for (int k = first; k < stop; ++k)
        w->weighted[k] = rotate(-TAU*cfo*(k+offset)/w->rate);
    double previous_fraction = NAN, weights[16], normalizer = 0;
    for (int frame = 0; ; ++frame) {
        int start = frame_start(w, epoch, frame);
        if (start+stop-1+offset >= (double)count-(integer ? 0 : 8)) break;
        /* Workspace.select stops at the first unsupported row. */
        if (start+first+offset < (integer ? 0 : 7)) break;
        double complex correlations[2][64] = {{0}};
        for (int symbol = 2; symbol < 66; ++symbol) {
            int begin = (int)nearbyint(symbol*w->rate*SYMBOL_S);
            int end = (int)nearbyint((symbol+1)*w->rate*SYMBOL_S);
            for (int k = begin; k < end; ++k) {
                double position = start + k + offset;
                double complex received = 0;
                if (integer) received = w->samples[(int)nearbyint(position)];
                else {
                    int base = (int)floor(position);
                    double fraction = position-base;
                    /* Adding the offset to an integer can round differently
                     * across floating-point binades. Cache the actual rounded
                     * fraction, not a nominal one shared by every position. */
                    if (fraction != previous_fraction) {
                        normalizer = 0;
                        for (int tap = -7; tap <= 8; ++tap) {
                            double distance = position-(base+tap);
                            weights[tap+7] = sinc(distance)*sinc(distance/8);
                            normalizer += weights[tap+7];
                        }
                        previous_fraction = fraction;
                    }
                    for (int tap = -7; tap <= 8; ++tap) {
                        received += weights[tap+7]*w->samples[base+tap];
                    }
                    received /= normalizer;
                }
                /* Omit only the common unit-magnitude frame phase. */
                double complex corrected = received*w->weighted[k];
                correlations[0][symbol-2] += conj(w->exact[k])*corrected;
                correlations[1][symbol-2] += conj(w->control[k])*corrected;
            }
        }
        for (int which = 0; which < 2; ++which) {
            memset(w->input, 0, 128*sizeof(*w->input));
            double ceiling = 0;
            for (int k = 0; k < 64; ++k) {
                w->input[k] = correlations[which][k];
                ceiling += cabs(w->input[k]);
            }
            ceilings[which] += ceiling*ceiling;
            leo_fft_forward(&w->short_fft, w->input);
            for (int k = 0; k < 128; ++k) spectra[which][k] += power(w->short_fft.output[k]);
        }
    }
    result[2] = 0;
    for (int which = 0; which < 2; ++which) {
        for (int k = 0; k < 128; ++k) w->input[k] = spectra[which][k];
        leo_fft_forward(&w->short_fft, w->input);
        memset(w->input, 0, 512*sizeof(*w->input));
        for (int k = 0; k < 64; ++k) w->input[k] = conj(w->short_fft.output[k])/128;
        for (int k = 1; k < 64; ++k) w->input[512-k] = conj(w->short_fft.output[128-k])/128;
        leo_fft_forward(&w->glrt_fft, w->input);
        int best = 0;
        for (int k = 1; k < 512; ++k)
            if (creal(w->glrt_fft.output[k]) > creal(w->glrt_fft.output[best])) best = k;
        result[which] = ceilings[which]>0 ? creal(w->glrt_fft.output[best])/ceilings[which] : 0;
        if (which == 0 && ceilings[which]>0)
            result[2] = (best < 256 ? best : best-512)/(512*SYMBOL_S);
    }
    return 0;
}

int leo_presence_glrt(leo_presence_workspace *w, const leo_presence_complex *x,
    size_t count, int32_t epoch, double cfo, double offset, double result[3])
{
    if (!result || ingest(w, x, count)) return -1;
    return glrt(w, count, epoch, cfo, offset, result);
}

static int candidate_before(const leo_presence_candidate *a, const leo_presence_candidate *b)
{
    double av[] = {a->verify_score-a->verify_control_score, a->verify_score,
        a->conditioned_score, a->acquire_score, -fabs(a->acquired_cfo_hz), -a->epoch};
    double bv[] = {b->verify_score-b->verify_control_score, b->verify_score,
        b->conditioned_score, b->acquire_score, -fabs(b->acquired_cfo_hz), -b->epoch};
    for (int k = 0; k < 6; ++k) if (av[k] != bv[k]) return av[k] > bv[k];
    return 0;
}

static int execute(leo_presence_workspace *w, size_t count, leo_presence_result *out)
{
    double started = clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    coarse(w, count);
    out->coarse_cpu_ms = clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
    int retained_epoch[2], retained_bin[2], nr = 0;
    /* Two passes avoid sorting an entire allocation of coarse peaks. */
    for (int selection = 0; selection < 2; ++selection) {
        int best_e = -1, best_f = -1; double best_score = -1;
        for (int f = 0; f < 11; ++f) for (int e = 0; e < (int)w->n; ++e) {
            double value = w->grid[f*w->n+e];
            double left = e ? w->grid[f*w->n+e-1] : -INFINITY;
            double right = e+1 < (int)w->n ? w->grid[f*w->n+e+1] : -INFINITY;
            if (!(value>=left && value>=right && (value>left || value>right))) continue;
            if (selection) {
                int distance = abs(e-retained_epoch[0]);
                if (distance > (int)w->n-distance) distance = (int)w->n-distance;
                if (distance < 5 && fabs(w->frequencies[f]-w->frequencies[retained_bin[0]])<=10000)
                    continue;
            }
            if (value>best_score || (value==best_score &&
                (best_f<0 || fabs(w->frequencies[f])<fabs(w->frequencies[best_f]) ||
                 (fabs(w->frequencies[f])==fabs(w->frequencies[best_f]) && e<best_e)))) {
                best_e=e; best_f=f; best_score=value;
            }
        }
        if (best_e<0 || (selection==0 && best_score<=0)) break;
        retained_epoch[nr]=best_e; retained_bin[nr]=best_f; ++nr;
    }
    started = clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    for (int r = 0; r < nr; ++r) {
        leo_presence_candidate *c = &out->candidates[out->candidate_count];
        int e=retained_epoch[r], f=retained_bin[r], refined=e;
        for (int k=e-1; k<=e+1; ++k)
            if (k>=0 && k<(int)w->n && (w->grid[f*w->n+k]>w->grid[f*w->n+refined] ||
                (w->grid[f*w->n+k]==w->grid[f*w->n+refined] && k<refined))) refined=k;
        c->epoch=refined; c->coarse_score=w->grid[f*w->n+e];
        double frequencies[322], scores[322], coarse_cfo=w->frequencies[f];
        int nf=grid(fmax(-400000,coarse_cfo-80000),fmin(400000,coarse_cfo+80000),500,frequencies);
        fine_scores(w,count,refined,frequencies[0],nf,scores);
        int best=best_frequency(scores,frequencies,nf);
        double interpolated=frequencies[best];
        if (best>0 && best+1<nf) {
            double curve=scores[best-1]-2*scores[best]+scores[best+1];
            if (isfinite(curve) && curve < -1e-15)
                interpolated += fmax(-500,fmin(500,0.5*(scores[best-1]-scores[best+1])/curve*500));
        }
        nf=grid(fmax(-400000,interpolated-2000),fmin(400000,interpolated+2000),100,frequencies);
        conditioned_scores(w,count,refined,frequencies,nf,scores);
        best=best_frequency(scores,frequencies,nf);
        c->acquired_cfo_hz=frequencies[best]; c->conditioned_score=scores[best];
        c->acquire_score=normalized_score(w,count,refined,c->acquired_cfo_hz,w->exact,2);
        c->verify_score=normalized_score(w,count,refined,c->acquired_cfo_hz,w->exact,3);
        c->verify_control_score=normalized_score(w,count,refined,c->acquired_cfo_hz,w->control,3);
        if (frame_start(w,refined,1)+(int)nearbyint(302*w->rate*SYMBOL_S)>(int)count) continue;
        ++out->candidate_count;
    }
    if (out->candidate_count==2 && candidate_before(&out->candidates[1],&out->candidates[0])) {
        leo_presence_candidate tmp=out->candidates[0];
        out->candidates[0]=out->candidates[1]; out->candidates[1]=tmp;
    }
    out->fine_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
    started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    for (int r=0; r<out->candidate_count; ++r) {
        leo_presence_candidate *c=&out->candidates[r]; int best=0;
        for (int k=0; k<5; ++k) {
            int epoch=(c->epoch+k-2+(int)w->n)%(int)w->n; double score[3];
            glrt(w,count,epoch,c->acquired_cfo_hz,0,score);
            c->exact_grid[k]=score[0]; c->control_grid[k]=score[1];
            if (score[0]>c->exact_grid[best]) best=k;
        }
        if (best==0 || best==4) continue;
        double a=log(fmax(c->exact_grid[best-1],DBL_MIN));
        double b=log(fmax(c->exact_grid[best],DBL_MIN));
        double d=log(fmax(c->exact_grid[best+1],DBL_MIN));
        double curve=a-2*b+d;
        if (!isfinite(curve) || curve >= -DBL_EPSILON) continue;
        double offset=best-2+fmax(-0.5,fmin(0.5,0.5*(a-d)/curve));
        double score[3]; glrt(w,count,c->epoch,c->acquired_cfo_hz,offset,score);
        c->fractional_complete=1; c->fractional_offset_samples=offset;
        c->exact_score=score[0]; c->control_score=score[1]; c->margin=score[0]-score[1];
        c->tracking_cfo_hz=c->acquired_cfo_hz+score[2];
    }
    out->fractional_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
    return 0;
}

int leo_presence_run(leo_presence_workspace *w, const leo_presence_complex *samples,
    size_t count, leo_presence_result *out)
{
    if (!out) return -1;
    memset(out,0,sizeof(*out));
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID), wall=clock_ms(CLOCK_MONOTONIC);
    if (ingest(w,samples,count)) return -1;
    out->conversion_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    int result=execute(w,count,out);
    out->total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out->total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    return result;
}

int leo_presence_run_ci16(leo_presence_workspace *w, const int16_t *iq,
    size_t count, leo_presence_result *out)
{
    if (!w || !iq || !out || count<(size_t)ceil(w->rate/375.0) || count>w->max_samples) return -1;
    memset(out,0,sizeof(*out));
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID), wall=clock_ms(CLOCK_MONOTONIC);
    for (size_t k=0;k<count;++k) w->samples[k]=iq[2*k]+I*(double)iq[2*k+1];
    out->conversion_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    int result=execute(w,count,out);
    out->total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out->total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    return result;
}
