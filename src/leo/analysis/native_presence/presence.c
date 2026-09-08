#define _POSIX_C_SOURCE 200809L
#include "presence.h"
#include "fft.h"
#include "budget.h"
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

/* Exact execution reuse. No search bins, frames, templates or thresholds
 * change. Keep the uncached path available for differential qualification. */
#ifndef LEO_PRESENCE_PRECOMPUTE
#define LEO_PRESENCE_PRECOMPUTE 1
#endif
#if LEO_PRESENCE_PRECOMPUTE != 0 && LEO_PRESENCE_PRECOMPUTE != 1
#error "LEO_PRESENCE_PRECOMPUTE must be 0 or 1"
#endif
#if LEO_PRESENCE_PRECOMPUTE
/* grid() may append a clipped off-grid endpoint. This includes that spare
 * slot even though it takes the nonregular (uncached) rotation path. */
#define CONDITIONED_TABLES (2*LEO_PRESENCE_CONDITIONED_RADIUS/100+2)
#else
#define CONDITIONED_TABLES 42
#endif
#ifndef LEO_PRESENCE_BOUNDED_MAGNITUDE
#define LEO_PRESENCE_BOUNDED_MAGNITUDE 0
#endif
#if LEO_PRESENCE_BOUNDED_MAGNITUDE != 0 && LEO_PRESENCE_BOUNDED_MAGNITUDE != 1
#error "LEO_PRESENCE_BOUNDED_MAGNITUDE must be 0 or 1"
#endif

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

#if !defined(LEO_PRESENCE_COARSE_FP32)
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
#endif

struct leo_presence_workspace {
    uint32_t rate;
    size_t n, max_samples;
    double complex *exact, *control, *samples, *input, *weighted, *base;
    double complex *conditioned_offsets;
#if LEO_PRESENCE_PRECOMPUTE
    double complex *glrt_rotations;
    double rotation_cfo, rotation_offset;
    int have_rotations, symbol_starts[303];
#endif
    double *prefix, *grid, *accumulated, *rotated_real, *rotated_imag;
    int32_t *support;
    npy_intp starts[12], stops[12], offsets[16];
    double frequencies[12], correlation_real[12], correlation_imag[12];
    leo_fft fine_fft, short_fft, glrt_fft;
    double fine_step_hz;
#if LEO_PRESENCE_POWER_PROPOSAL
    leo_fft power_fft;
    double complex *power_input, *power_template_fft;
    double *power_native_template, *power_native_folded;
    double power_template_energy, power_native_template_energy, power_native_folded_energy;
#if LEO_PRESENCE_DIFFERENTIAL_PROPOSAL
    double complex *diff_template, *diff_folded;
    int32_t *diff_support;
    double diff_template_energy, diff_folded_energy;
#endif
#endif
    leo_presence_profile profile;
    leo_presence_nuisance nuisance;
#if defined(LEO_PRESENCE_COARSE_FP32)
    float *float_samples, *float_accumulated;
    float float_reference_real[12*23*12], float_reference_imag[12*23*12];
    double float_reference_energy[12];
#endif
};

static double clock_ms(clockid_t id)
{
    struct timespec ts;
    if (clock_gettime(id, &ts)) return 0.0;
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}
static double power(double complex x) { return creal(x)*creal(x) + cimag(x)*cimag(x); }
static double magnitude(double complex x)
{
#if LEO_PRESENCE_BOUNDED_MAGNITUDE
    /* Avoid general hypot scaling for ordinary finite detector values. Keep
     * libc's robust path for underflow, overflow and nonfinite inputs. This
     * changes floating-point rounding, not the statistic: qualify separately. */
    double squared=power(x);
    if (squared>=DBL_MIN && isfinite(squared)) return sqrt(squared);
#endif
    return cabs(x);
}
static double complex rotate(double angle) { return cos(angle) + I * sin(angle); }
static int frame_start(const leo_presence_workspace *w, int epoch, int frame)
{
#if LEO_PRESENCE_PRECOMPUTE
    return epoch+(int)w->offsets[frame];
#else
    return epoch+(int)nearbyint(frame*(w->rate/750.0));
#endif
}
static int symbol_start(const leo_presence_workspace *w, int symbol)
{
#if LEO_PRESENCE_PRECOMPUTE
    return w->symbol_starts[symbol];
#else
    return (int)nearbyint(symbol*w->rate*SYMBOL_S);
#endif
}
static int epoch_stride(const leo_presence_workspace *w)
{ return LEO_PRESENCE_STRIDE_2P5 ? LEO_PRESENCE_STRIDE_2P5*(int)(w->rate/2500000) : 1; }

int leo_presence_get_profile(const leo_presence_workspace *w, leo_presence_profile *profile)
{
    if (!w || !profile) return -1;
    *profile=w->profile;
    profile->coarse_frames=LEO_PRESENCE_COARSE_FRAMES;
    profile->fine_frames=LEO_PRESENCE_FINE_FRAMES;
    profile->epoch_frames=LEO_PRESENCE_EPOCH_FRAMES;
    profile->anchor_stride=LEO_PRESENCE_ANCHOR_STRIDE;
    profile->epoch_stride=(uint32_t)epoch_stride(w);
    profile->conditioned_radius_hz=LEO_PRESENCE_CONDITIONED_RADIUS;
    return 0;
}

int leo_presence_get_nuisance(const leo_presence_workspace *w, leo_presence_nuisance *nuisance)
{
    if (!w || !nuisance) return -1;
    *nuisance=w->nuisance;
    return 0;
}

#if defined(LEO_PRESENCE_COARSE_FP32)
#include "coarse_fp32.h"
#endif
#if LEO_PRESENCE_DIFFERENTIAL_PROPOSAL
#include "coarse_differential.h"
#elif LEO_PRESENCE_POWER_PROPOSAL
#include "coarse_power.h"
#endif
#if LEO_PRESENCE_TONE_NUISANCE
#include "tone_nuisance.h"
#endif

void leo_presence_destroy(leo_presence_workspace *w)
{
    if (!w) return;
    free(w->exact); free(w->control); free(w->samples); free(w->input);
    free(w->weighted); free(w->base); free(w->conditioned_offsets);
#if LEO_PRESENCE_PRECOMPUTE
    free(w->glrt_rotations);
#endif
    free(w->prefix); free(w->grid); free(w->accumulated); free(w->support);
    free(w->rotated_real); free(w->rotated_imag);
#if defined(LEO_PRESENCE_COARSE_FP32)
    free(w->float_samples); free(w->float_accumulated);
#endif
    leo_fft_free(&w->fine_fft); leo_fft_free(&w->short_fft); leo_fft_free(&w->glrt_fft);
#if LEO_PRESENCE_POWER_PROPOSAL
    leo_fft_free(&w->power_fft); free(w->power_input); free(w->power_template_fft);
    free(w->power_native_template); free(w->power_native_folded);
#if LEO_PRESENCE_DIFFERENTIAL_PROPOSAL
    free(w->diff_template); free(w->diff_folded); free(w->diff_support);
#endif
#endif
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
    ALLOC(conditioned_offsets, CONDITIONED_TABLES * n); ALLOC(prefix, w->max_samples + 1);
#if LEO_PRESENCE_PRECOMPUTE
    ALLOC(glrt_rotations, n);
#endif
    ALLOC(grid, CFO_COUNT * n); ALLOC(accumulated, CFO_COUNT * n); ALLOC(support, n);
    ALLOC(rotated_real, CFO_COUNT * 23); ALLOC(rotated_imag, CFO_COUNT * 23);
#if defined(LEO_PRESENCE_COARSE_FP32)
    ALLOC(float_samples, 2*w->max_samples); ALLOC(float_accumulated, CFO_COUNT*n);
#endif
#if LEO_PRESENCE_POWER_PROPOSAL
    size_t power_size=2;
    while (power_size<2*n-1) power_size*=2;
    if (LEO_PRESENCE_POWER_BINS) power_size=LEO_PRESENCE_POWER_BINS;
#if LEO_PRESENCE_DIFFERENTIAL_PROPOSAL
    power_size=2;
    while (power_size<n) power_size*=2;
    ALLOC(diff_template,n); ALLOC(diff_folded,n); ALLOC(diff_support,n);
#endif
    ALLOC(power_input,power_size); ALLOC(power_template_fft,power_size);
    ALLOC(power_native_template,n); ALLOC(power_native_folded,n);
    if (leo_fft_init(&w->power_fft,power_size)) { leo_presence_destroy(w); return NULL; }
#endif
#undef ALLOC
    size_t fine_size=rate/500;
    if (LEO_PRESENCE_FAST_FINE_FFT) {
        fine_size=2;
        while (fine_size<n) fine_size*=2;
    }
    w->fine_step_hz=(double)rate/fine_size;
    if (leo_fft_init(&w->fine_fft, fine_size) ||
        leo_fft_init(&w->short_fft, 128) || leo_fft_init(&w->glrt_fft, 512)) {
        leo_presence_destroy(w); return NULL;
    }
    for (size_t k = 0; k < n; ++k) {
        if (!isfinite(exact[k].re) || !isfinite(exact[k].im) ||
            !isfinite(control[k].re) || !isfinite(control[k].im) ||
            fabs(exact[k].re)>16 || fabs(exact[k].im)>16 ||
            fabs(control[k].re)>16 || fabs(control[k].im)>16) {
            leo_presence_destroy(w); return NULL;
        }
        w->exact[k] = exact[k].re + I * exact[k].im;
        w->control[k] = control[k].re + I * control[k].im;
        for (size_t f = 0; f < CONDITIONED_TABLES; ++f)
            w->conditioned_offsets[f*n+k] = rotate(-TAU * (f * 100.0) * k / rate);
    }
    for (int k = 0; k < 12; ++k) {
        w->starts[k] = (npy_intp)nearbyint((2 + k * 26) * rate * SYMBOL_S);
        w->stops[k] = (npy_intp)nearbyint((3 + k * 26) * rate * SYMBOL_S);
        w->frequencies[k] = -400000.0 + k * 80000.0;
    }
    for (int k = 0; k < 16; ++k)
        w->offsets[k]=(npy_intp)nearbyint(k*(rate/750.0));
#if LEO_PRESENCE_PRECOMPUTE
    for (int k=0; k<303; ++k)
        w->symbol_starts[k]=(int)nearbyint(k*rate*SYMBOL_S);
#endif
#if defined(LEO_PRESENCE_COARSE_FP32)
    coarse_fp32_templates(w);
#endif
#if LEO_PRESENCE_DIFFERENTIAL_PROPOSAL
    coarse_differential_template(w);
#elif LEO_PRESENCE_POWER_PROPOSAL
    coarse_power_template(w);
#endif
    return w;
}

static int ingest(leo_presence_workspace *w, const leo_presence_complex *x, size_t count)
{
    if (!w || !x || fegetround()!=FE_TONEAREST ||
        count < (size_t)ceil(w->rate / 375.0) || count > w->max_samples)
        return -1;
    for (size_t k = 0; k < count; ++k) {
        if (!isfinite(x[k].re) || !isfinite(x[k].im) ||
            fabs(x[k].re) > 1e12 || fabs(x[k].im) > 1e12) return -1;
        w->samples[k] = x[k].re + I*x[k].im;
    }
    return 0;
}

static int coarse(leo_presence_workspace *w, size_t count, const int16_t *iq)
{
    (void)iq;
#if LEO_PRESENCE_DIFFERENTIAL_PROPOSAL
    return coarse_differential(w,count,iq);
#elif LEO_PRESENCE_POWER_PROPOSAL
    return coarse_power(w,count);
#endif
#if defined(LEO_PRESENCE_COARSE_FP32)
    return coarse_fp32(w, count);
#else
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
    return kernel.invalid_geometry ? -1 : 0;
#endif
}

int leo_presence_coarse(leo_presence_workspace *w, const leo_presence_complex *x,
    size_t count, double *scores)
{
    if (!scores || ingest(w, x, count)) return -1;
    if (coarse(w, count, NULL)) return -1;
    memcpy(scores, w->grid, 11 * w->n * sizeof(double));
    return 0;
}

int leo_presence_coarse_ci16(leo_presence_workspace *w, const int16_t *iq,
    size_t count, double *scores)
{
    if (!w || !iq || !scores || count<(size_t)ceil(w->rate/375.0) ||
        count>w->max_samples || fegetround()!=FE_TONEAREST) return -1;
    for (size_t k=0; k<count; ++k) w->samples[k]=iq[2*k]+I*(double)iq[2*k+1];
    if (coarse(w,count,iq)) return -1;
    memcpy(scores,w->grid,11*w->n*sizeof(double));
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

/* Normalized coherent fine acquisition. Alternating symbols remain the
 * baseline; all-symbol acquisition is a separately configured experiment. */
static void fine_scores(leo_presence_workspace *w, size_t count, int epoch,
    double first_frequency, int frequency_count, double *scores)
{
    size_t last = (size_t)symbol_start(w,301) - 1;
    double template_energy = 0;
    memset(w->base, 0, w->n * sizeof(*w->base));
    memset(scores, 0, frequency_count * sizeof(*scores));
    const int step=LEO_PRESENCE_FINE_ALL_SYMBOLS ? 1 : 2;
    /* first_frequency is an aligned FFT bin. Select circular output indices
     * instead of rotating every input sample by that integer-bin frequency. */
    int first_bin=(int)nearbyint(first_frequency/w->fine_step_hz);
    first_bin=(first_bin+(int)w->fine_fft.size)%(int)w->fine_fft.size;
    for (int symbol = 2; symbol < 302; symbol += step) {
        int begin = symbol_start(w,symbol);
        int end = symbol_start(w,symbol+1);
        for (int k = begin; k < end; ++k) {
            template_energy += power(w->exact[k]);
            w->base[k] = conj(w->exact[k]);
        }
    }
    int frames = 0;
    for (int frame = 0; frame < LEO_PRESENCE_FINE_FRAMES; ++frame) {
        int start = frame_start(w, epoch, frame);
        if ((size_t)start + last >= count) break;
        memset(w->input, 0, w->fine_fft.size * sizeof(*w->input));
        double energy = 0;
        for (int symbol = 2; symbol < 302; symbol += step) {
            int begin = symbol_start(w,symbol);
            int end = symbol_start(w,symbol+1);
            for (int k = begin; k < end; ++k) {
                energy += power(w->samples[start+k]);
                w->input[k] = w->samples[start+k] * w->base[k];
            }
        }
        leo_fft_forward(&w->fine_fft, w->input);
        double denom = sqrt(template_energy * energy);
        if (denom > 0) {
            int bin=first_bin;
            for (int f = 0; f < frequency_count; ++f) {
                scores[f] += magnitude(w->fine_fft.output[bin])/denom;
                if (++bin==(int)w->fine_fft.size) bin=0;
            }
        }
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
    for (int frame = 0; frame < LEO_PRESENCE_FINE_FRAMES; ++frame) {
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
            scores[f] += magnitude(total)/denom;
        }
        ++frames;
    }
    if (frames) for (int f = 0; f < nf; ++f) scores[f] /= frames;
}

static double normalized_score(leo_presence_workspace *w, size_t count, int epoch,
    double cfo, const double complex *reference, int first_symbol)
{
    double te = 0, score = 0;
    size_t last = (size_t)symbol_start(w,first_symbol == 2 ? 301 : 302)-1;
    for (int symbol = first_symbol; symbol < 302; symbol += 2) {
        int begin = symbol_start(w,symbol);
        int end = symbol_start(w,symbol+1);
        for (int k = begin; k < end; ++k) {
            te += power(reference[k]);
            w->base[k] = conj(reference[k]) * rotate(-TAU*cfo*k/w->rate);
        }
    }
    int frames = 0;
    for (int frame = 0; frame < LEO_PRESENCE_FINE_FRAMES; ++frame) {
        int start = frame_start(w, epoch, frame);
        if ((size_t)start + last >= count) break;
        double energy = 0; double complex total = 0;
        for (int symbol = first_symbol; symbol < 302; symbol += 2) {
            int begin = symbol_start(w,symbol);
            int end = symbol_start(w,symbol+1);
            for (int k = begin; k < end; ++k) {
                total += w->samples[start+k]*w->base[k];
                energy += power(w->samples[start+k]);
            }
        }
        double denom = sqrt(te*energy);
        if (denom > 0) score += magnitude(total)/denom;
        ++frames;
    }
    return frames ? score/frames : 0;
}

static double sinc(double x) { return x == 0 ? 1 : sin(TAU*0.5*x)/(TAU*0.5*x); }

static int glrt(leo_presence_workspace *w, size_t count, int epoch,
    double cfo, double offset, int frame_limit, double result[3])
{
    if (epoch < 0 || epoch >= (int)w->n || !isfinite(cfo) || fabs(cfo)>400000 ||
        !isfinite(offset) || fabs(offset)>2)
        return -1;
    double spectra[2][128] = {{0}}, ceilings[2] = {0};
    int integer = fabs(offset-nearbyint(offset)) <= 1e-12;
    int first = symbol_start(w,2);
    int stop = symbol_start(w,66);
    /* Rotation depends on local sample position, never on the frame number.
     * Keep the original arithmetic and reuse it across every supporting frame. */
#if LEO_PRESENCE_PRECOMPUTE
    double complex *rotations=w->glrt_rotations;
    if (!w->have_rotations || w->rotation_cfo!=cfo || w->rotation_offset!=offset) {
        for (int k=first; k<stop; ++k)
            rotations[k]=rotate(-TAU*cfo*(k+offset)/w->rate);
        w->rotation_cfo=cfo; w->rotation_offset=offset; w->have_rotations=1;
    }
#else
    double complex *rotations=w->weighted;
    for (int k=first; k<stop; ++k)
        rotations[k]=rotate(-TAU*cfo*(k+offset)/w->rate);
#endif
    double previous_fraction = NAN, weights[16], normalizer = 0;
    for (int frame = 0; frame < frame_limit; ++frame) {
        int start = frame_start(w, epoch, frame);
        if (start+stop-1+offset >= (double)count-(integer ? 0 : 8)) break;
        /* Workspace.select stops at the first unsupported row. */
        if (start+first+offset < (integer ? 0 : 7)) break;
        double complex correlations[2][64] = {{0}};
        for (int symbol = 2; symbol < 66; ++symbol) {
            int begin = symbol_start(w,symbol);
            int end = symbol_start(w,symbol+1);
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
                double complex corrected = received*rotations[k];
                correlations[0][symbol-2] += conj(w->exact[k])*corrected;
                correlations[1][symbol-2] += conj(w->control[k])*corrected;
            }
        }
        for (int which = 0; which < 2; ++which) {
            memset(w->input, 0, 128*sizeof(*w->input));
            double ceiling = 0;
            for (int k = 0; k < 64; ++k) {
                w->input[k] = correlations[which][k];
                /* Keep libc magnitude in the final GLRT statistic. Tiny
                 * ceiling differences can be amplified by fractional peak
                 * interpolation on a nearly flat, non-pilot surface. */
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
    return glrt(w, count, epoch, cfo, offset, 16, result);
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

static int execute(leo_presence_workspace *w, size_t count, leo_presence_result *out,
    const int16_t *original_ci16, int32_t proposal_epoch)
{
    (void)original_ci16;
    memset(&w->profile, 0, sizeof(w->profile));
    memset(&w->nuisance, 0, sizeof(w->nuisance));
#if LEO_PRESENCE_TONE_NUISANCE
    double nuisance_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    w->nuisance.enabled=1;
    if (tone_nuisance(w,count,original_ci16)) return -1;
    w->nuisance.cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-nuisance_started;
#endif
    double started = clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    if (proposal_epoch<0 && coarse(w, count, w->nuisance.applied ? NULL : original_ci16)) return -1;
    out->coarse_cpu_ms = clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
    int retained_epoch[2], retained_bin[2], nr = 0;
    if (proposal_epoch>=0) {
        retained_epoch[0]=proposal_epoch; retained_bin[0]=5; nr=1;
    }
    /* Two passes avoid sorting an entire allocation of coarse peaks. */
    for (int selection = 0; proposal_epoch<0 && selection < LEO_PRESENCE_CANDIDATES; ++selection) {
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
        int radius=epoch_stride(w)>1 ? epoch_stride(w)-1 : 1;
#if LEO_PRESENCE_POWER_BINS
        radius=((int)w->n+LEO_PRESENCE_POWER_BINS-1)/LEO_PRESENCE_POWER_BINS;
#endif
        if (proposal_epoch>=0) radius=0;
        double stage_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        if (proposal_epoch<0) {
#if LEO_PRESENCE_POWER_BINS
        /* Refine proposals against original-rate folded power, including the
         * circular seam. Do not compare projected and native scores locally. */
        for (int delta=-radius; delta<=radius; ++delta)
            coarse_power_cell(w,(e+delta+(int)w->n)%(int)w->n);
#endif
#if LEO_PRESENCE_DIFFERENTIAL_PROPOSAL && !LEO_PRESENCE_DIFFERENTIAL_LOCAL_RADIUS
        /* Optional staged refinement: rank eight centers first, then refine
         * only retained neighborhoods before blind CFO acquisition. */
        double power_norm=sqrt(w->power_native_template_energy*w->power_native_folded_energy);
        double diff_norm=sqrt(w->diff_template_energy*w->diff_folded_energy);
        for (int delta=-1; delta<=1; ++delta) {
            int local=(e+delta+(int)w->n)%(int)w->n;
            w->grid[5*w->n+local]=diff_native_cell(w,(size_t)local,power_norm,diff_norm);
        }
#endif
#if defined(LEO_PRESENCE_COARSE_FP32)
        if (epoch_stride(w)>1)
            for (int k=e-radius; k<=e+radius; ++k)
                if (k>=0 && k<(int)w->n && w->support[k]==0 && coarse_fp32_cell(w,count,k))
                    return -1;
#endif
        w->profile.local_coarse_cpu_ms += clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage_started;
        for (int local=e-radius; local<=e+radius; ++local) {
            int k=local;
#if LEO_PRESENCE_POWER_BINS || LEO_PRESENCE_DIFFERENTIAL_PROPOSAL
            k=(local+(int)w->n)%(int)w->n;
#endif
            if (k>=0 && k<(int)w->n && (w->grid[f*w->n+k]>w->grid[f*w->n+refined] ||
                (w->grid[f*w->n+k]==w->grid[f*w->n+refined] && k<refined))) refined=k;
        }
        }
        c->epoch=refined; c->coarse_score=proposal_epoch<0 ? w->grid[f*w->n+e] : 0;
        double frequencies[1602], scores[1602], coarse_cfo=w->frequencies[f];
        double lower=fmax(-400000,coarse_cfo-80000), upper=fmin(400000,coarse_cfo+80000);
        if (LEO_PRESENCE_POWER_PROPOSAL || proposal_epoch>=0) { lower=-400000; upper=400000; }
        if (LEO_PRESENCE_FAST_FINE_FFT) {
            lower=ceil(lower/w->fine_step_hz)*w->fine_step_hz;
            upper=floor(upper/w->fine_step_hz)*w->fine_step_hz;
        }
        int nf=grid(lower,upper,w->fine_step_hz,frequencies);
        stage_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        fine_scores(w,count,refined,frequencies[0],nf,scores);
        w->profile.acquisition_fft_cpu_ms += clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage_started;
        int best=best_frequency(scores,frequencies,nf);
        double interpolated=frequencies[best];
        if (best>0 && best+1<nf) {
            double curve=scores[best-1]-2*scores[best]+scores[best+1];
            if (isfinite(curve) && curve < -1e-15)
                interpolated += fmax(-w->fine_step_hz,fmin(w->fine_step_hz,
                    0.5*(scores[best-1]-scores[best+1])/curve*w->fine_step_hz));
        }
        nf=grid(fmax(-400000,interpolated-LEO_PRESENCE_CONDITIONED_RADIUS),
            fmin(400000,interpolated+LEO_PRESENCE_CONDITIONED_RADIUS),100,frequencies);
        stage_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        conditioned_scores(w,count,refined,frequencies,nf,scores);
        w->profile.conditioned_cpu_ms += clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage_started;
        best=best_frequency(scores,frequencies,nf);
        c->acquired_cfo_hz=frequencies[best]; c->conditioned_score=scores[best];
        stage_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        /* Power proposals keep their proposal order. Final exact/control GLRT
         * is still required; the legacy acquisition-ranking scores are unused. */
        if (!LEO_PRESENCE_POWER_PROPOSAL) {
            c->acquire_score=normalized_score(w,count,refined,c->acquired_cfo_hz,w->exact,2);
            c->verify_score=normalized_score(w,count,refined,c->acquired_cfo_hz,w->exact,3);
            c->verify_control_score=normalized_score(w,count,refined,c->acquired_cfo_hz,w->control,3);
        }
        w->profile.verification_cpu_ms += clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage_started;
        if (frame_start(w,refined,1)+symbol_start(w,302)>(int)count) continue;
        ++out->candidate_count;
    }
    if (!LEO_PRESENCE_POWER_PROPOSAL && out->candidate_count==2 &&
        candidate_before(&out->candidates[1],&out->candidates[0])) {
        leo_presence_candidate tmp=out->candidates[0];
        out->candidates[0]=out->candidates[1]; out->candidates[1]=tmp;
    }
    out->fine_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
    started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    for (int r=0; r<out->candidate_count; ++r) {
        leo_presence_candidate *c=&out->candidates[r]; int best=0;
        double stage_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        for (int k=0; k<5; ++k) {
            int epoch=(c->epoch+k-2+(int)w->n)%(int)w->n; double score[3];
            glrt(w,count,epoch,c->acquired_cfo_hz,0,LEO_PRESENCE_EPOCH_FRAMES,score);
            c->exact_grid[k]=score[0]; c->control_grid[k]=score[1];
            if (score[0]>c->exact_grid[best]) best=k;
        }
        w->profile.epoch_lattice_cpu_ms += clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage_started;
        if (best==0 || best==4) continue;
        double a=log(fmax(c->exact_grid[best-1],DBL_MIN));
        double b=log(fmax(c->exact_grid[best],DBL_MIN));
        double d=log(fmax(c->exact_grid[best+1],DBL_MIN));
        double curve=a-2*b+d;
        if (!isfinite(curve) || curve >= -DBL_EPSILON) continue;
        double offset=best-2+fmax(-0.5,fmin(0.5,0.5*(a-d)/curve));
        stage_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        double score[3]; glrt(w,count,c->epoch,c->acquired_cfo_hz,offset,16,score);
        w->profile.final_confirmation_cpu_ms += clock_ms(CLOCK_PROCESS_CPUTIME_ID)-stage_started;
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
    int result=execute(w,count,out,NULL,-1);
    out->total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out->total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    return result;
}

int leo_presence_run_ci16(leo_presence_workspace *w, const int16_t *iq,
    size_t count, leo_presence_result *out)
{
    if (!w || !iq || !out || fegetround()!=FE_TONEAREST ||
        count<(size_t)ceil(w->rate/375.0) || count>w->max_samples) return -1;
    memset(out,0,sizeof(*out));
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID), wall=clock_ms(CLOCK_MONOTONIC);
    for (size_t k=0;k<count;++k) w->samples[k]=iq[2*k]+I*(double)iq[2*k+1];
    out->conversion_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    int result=execute(w,count,out,iq,-1);
    out->total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    out->total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    return result;
}

int leo_presence_confirm_ci16(leo_presence_workspace *w, const int16_t *iq,
    size_t count, int32_t proposal_epoch, leo_presence_result *out)
{
    if (!w || !iq || !out || count!=w->max_samples || proposal_epoch<0 ||
        (size_t)proposal_epoch>=w->n || fegetround()!=FE_TONEAREST) return -1;
    leo_presence_result result={0};
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID), wall=clock_ms(CLOCK_MONOTONIC);
    for (size_t k=0; k<count; ++k) w->samples[k]=iq[2*k]+I*(double)iq[2*k+1];
    result.conversion_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    if (execute(w,count,&result,iq,proposal_epoch)) return -1;
    result.total_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    result.total_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    *out=result;
    return 0;
}
