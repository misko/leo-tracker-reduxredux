/* Capture-era post-coarse verification, from authenticated CI16 to GLRT margins. */
#include "portable_verifier.h"
#include "fft.h"

#include <float.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

enum {
    max_frames = 15, n = PORTABLE_FINE_EPOCHS, taps = PORTABLE_FINE_TAPS,
    first = 2 * taps, aperture = 64 * taps, stop = first + aperture,
    block = 256, terms = 6, blocks = (n + block - 1) / block,
    short_size = 128, glrt_size = 512, max_bins = PORTABLE_VERIFIER_CONDITIONED_BINS,
    rounded_weight_rows = 64,
    samples = PORTABLE_FINE_SAMPLES
};

static const double tau = 6.283185307179586476925286766559;
static const double rate = 10000000.0;
static const double gate = 0.025;

/* Match the existing conditioned and GLRT correlation translation-unit interfaces. */
typedef struct { double re, im; } GlrtComplex;
void conditioned_moments(const double *, const double *, const int32_t *, int, int,
                         const double *, double *, double *);
void conditioned_single(const double *, const double *, const int32_t *, int, int, double *);
void correlated_integer(const GlrtComplex *, const int32_t *, int, int, const int32_t *,
                        const GlrtComplex *, const GlrtComplex *, const GlrtComplex *,
                        GlrtComplex *, GlrtComplex *);
void correlated_fractional(const GlrtComplex *, const int32_t *, int, const int32_t *,
                           const double *, const GlrtComplex *, const GlrtComplex *,
                           const GlrtComplex *, GlrtComplex *, GlrtComplex *);

typedef union { PortableFineComplex fine[samples]; GlrtComplex glrt[samples]; double data[2*samples]; } Iq;
typedef union { PortableFineComplex fine[n]; double data[2*n]; } Rotated;

struct PortableVerifier {
    const PortableFineComplex *exact, *control;
    PortableFineWorkspace fine;
    Iq iq;
    Rotated reference;
    double powers[(terms - 1) * block];
    double moments[max_frames][blocks][terms][2];
    double energy[max_frames];
    GlrtComplex glrt_exact[aperture], glrt_control[aperture];
    GlrtComplex glrt_rotation[max_frames * aperture];
    int32_t indices[max_frames * aperture], weight_row[max_frames * aperture];
    double weights[rounded_weight_rows][16];
    GlrtComplex correlations[2][max_frames * 64];
    double complex fft_input[glrt_size];
    leo_fft fft128, fft512;
};

static inline double energy(PortableFineComplex z) { return z.r*z.r + z.i*z.i; }
static inline PortableFineComplex rotate(double theta) {
    return (PortableFineComplex){cos(theta), sin(theta)};
}
static inline PortableFineComplex multiply(PortableFineComplex a, PortableFineComplex b) {
    return (PortableFineComplex){a.r*b.r-a.i*b.i, a.r*b.i+a.i*b.r};
}
static inline PortableFineComplex conjugate(PortableFineComplex z) {
    return (PortableFineComplex){z.r, -z.i};
}
static inline int frame_start(unsigned epoch, unsigned frame) {
    return (int)(epoch + (frame*40000 + 1)/3);
}

PortableVerifier *portable_verifier_create(const PortableFineComplex *exact,
                                          const PortableFineComplex *control) {
    if (!exact || !control) return NULL;
    for (int k = 0; k < n; ++k) {
        if (!isfinite(exact[k].r) || !isfinite(exact[k].i) ||
            !isfinite(control[k].r) || !isfinite(control[k].i)) return NULL;
    }
    PortableVerifier *w = calloc(1, sizeof(*w));
    if (!w) return NULL;
    w->exact = exact;
    w->control = control;
    if (leo_fft_init(&w->fft128, short_size) || leo_fft_init(&w->fft512, glrt_size)) {
        portable_verifier_free(w);
        return NULL;
    }
    portable_fine_prepare(&w->fine);
    for (int k = 0; k < block; ++k) {
        double x = (k - 127.5) / 127.5, value = x;
        for (int d = 0; d < terms - 1; ++d, value *= x) w->powers[d * block + k] = value;
    }
    for (int k = 0; k < aperture; ++k) {
        w->glrt_exact[k] = (GlrtComplex){exact[first+k].r, -exact[first+k].i};
        w->glrt_control[k] = (GlrtComplex){control[first+k].r, -control[first+k].i};
    }
    return w;
}

void portable_verifier_free(PortableVerifier *w) {
    if (w) { leo_fft_free(&w->fft128); leo_fft_free(&w->fft512); free(w); }
}

size_t portable_verifier_workspace_bytes(void) {
    return sizeof(PortableVerifier) + 3 * (short_size + glrt_size) * sizeof(double complex);
}

int portable_verifier_load(PortableVerifier *w, const int16_t *iq, unsigned lane) {
    if (!w || !iq || lane > 1) return -1;
    for (int sample = 0; sample < samples; ++sample) {
        size_t index = 4 * (size_t)sample + 2 * lane;
        w->iq.fine[sample] = (PortableFineComplex){iq[index], iq[index + 1]};
    }
    return 0;
}

static unsigned bounded_grid(double low, double high, double *grid) {
    unsigned count = (unsigned)floor((high - low) / 100.0 + 1e-12) + 1;
    if (count > max_bins) return 0;
    for (unsigned i = 0; i < count; ++i) grid[i] = low + i*100.0;
    if (fabs(grid[count-1] - high) > 1e-9) {
        if (count == max_bins) return 0;
        grid[count++] = high;
    }
    return count;
}

static double direct_conditioned(PortableVerifier *w, double frequency,
                                 const int32_t *starts, int frames, const double *denom) {
    for (int k = 0; k < n; ++k) w->reference.fine[k] = multiply(
        conjugate(w->exact[k]), rotate(-tau * frequency * k / rate));
    double correlations[max_frames][2], score = 0;
    conditioned_single(w->iq.data, w->reference.data, starts, frames, n, &correlations[0][0]);
    for (int f = 0; f < frames; ++f) if (denom[f] > 0)
        score += hypot(correlations[f][0], correlations[f][1]) / denom[f];
    return frames ? score / frames : 0;
}

static int preferable(double score, double residual, double other, double other_residual) {
    if (score != other) return score > other;
    if (fabs(residual) != fabs(other_residual)) return fabs(residual) < fabs(other_residual);
    return residual < other_residual;
}

static void condition(PortableVerifier *w, unsigned epoch, double center_hz, double *residuals,
                      PortableVerifierResult *out) {
    unsigned count = out->conditioned_bins;
    double mid = center_hz + (residuals[0] + residuals[count-1]) / 2.0;
    double half = (residuals[count-1] - residuals[0]) / 2.0;
    double maximum = fmax(fabs(center_hz + residuals[0]), fabs(center_hz + residuals[count-1]));
    double distortion = tau * half * 127.5 / rate;
    /* Same Taylor remainder plus roundoff enclosure as the conditioned moment bank. */
    double bound = pow(distortion, 6) / 720 + (DBL_EPSILON / 2) *
                   (64*n + 128*(1 + tau*maximum*n/rate));
    double template_energy = 0;
    for (int k = 0; k < n; ++k) {
        template_energy += energy(w->exact[k]);
        w->reference.fine[k] = multiply(conjugate(w->exact[k]), rotate(-tau * mid * k / rate));
    }
    int32_t starts[max_frames];
    int frames = 0;
    for (int f = 0; f < max_frames; ++f) {
        int start = frame_start(epoch, f);
        if (start + n > samples) break;
        starts[frames++] = start;
    }
    out->stage_frames = frames;
    conditioned_moments(w->iq.data, w->reference.data, starts, frames, n, w->powers,
                        &w->moments[0][0][0][0], w->energy);
    double denom[max_frames];
    for (int f = 0; f < frames; ++f) denom[f] = sqrt(template_energy * w->energy[f]);

    double screen_best = 0;
    for (unsigned i = 0; i < count; ++i) {
        double absolute = center_hz + residuals[i];
        double delta = -tau * (absolute - mid) / rate;
        PortableFineComplex phase[blocks][terms];
        for (int b = 0; b < blocks; ++b) {
            phase[b][0] = rotate(delta * (b*block + 127.5));
            for (int d = 1; d < terms; ++d) {
                PortableFineComplex a = phase[b][d-1];
                double scale = delta*127.5 / d;
                phase[b][d] = (PortableFineComplex){-a.i*scale, a.r*scale};
            }
        }
        double score = 0;
        for (int f = 0; f < frames; ++f) if (denom[f] > 0) {
            PortableFineComplex sum = {0};
            for (int b = 0; b < blocks; ++b) for (int d = 0; d < terms; ++d) {
                PortableFineComplex z = {w->moments[f][b][d][0], w->moments[f][b][d][1]};
                PortableFineComplex term = multiply(phase[b][d], z);
                sum.r += term.r; sum.i += term.i;
            }
            score += hypot(sum.r, sum.i) / denom[f];
        }
        out->conditioned_grid[i] = absolute;
        out->conditioned_scores[i] = frames ? score / frames : 0;
        screen_best = fmax(screen_best, out->conditioned_scores[i]);
    }
    unsigned best = 0, contenders = 0;
    int outside = 0;
    for (unsigned i = 0; i < count; ++i) {
        double screening = out->conditioned_scores[i];
        if (screening >= screen_best - 2*bound) {
            double repaired = direct_conditioned(w, out->conditioned_grid[i], starts, frames, denom);
            if (++contenders == 1 || preferable(repaired, residuals[i],
                                               out->conditioned_scores[best], residuals[best])) best = i;
            out->conditioned_scores[i] = repaired;
            outside |= fabs(repaired - screening) > bound;
        }
    }
    if (outside) {
        best = 0;
        for (unsigned i = 0; i < count; ++i) {
            out->conditioned_scores[i] = direct_conditioned(w, out->conditioned_grid[i],
                                                             starts, frames, denom);
            if (preferable(out->conditioned_scores[i], residuals[i],
                           out->conditioned_scores[best], residuals[best])) best = i;
        }
    }
    if (contenders > 1 || outside) out->flags |= PORTABLE_VERIFIER_CONDITIONED_TIE;
    out->conditioned_winner = best;
    out->conditioned = out->conditioned_scores[best];
    out->acquired_hz = out->conditioned_grid[best];
    out->acquired_residual_hz = residuals[best];
}

static double pilots(PortableVerifier *w, unsigned epoch, double cfo,
                     const PortableFineComplex *template, int first_symbol) {
    const int limit = (299 + first_symbol) * taps;
    const int begin = first_symbol * taps, stride = 2*taps;
    double te = 0;
    memset(&w->reference, 0, sizeof(w->reference));
    for (int k = begin; k < limit; k += stride) for (int j = k; j < k+taps; ++j) {
        w->reference.fine[j] = multiply(conjugate(template[j]), rotate(-tau*cfo*j/rate));
        te += energy(template[j]);
    }
    double sum = 0, correlations[max_frames][2], d[max_frames];
    int32_t starts[max_frames];
    int frames = 0;
    for (int f = 0; f < max_frames; ++f) {
        int start = frame_start(epoch, f);
        if (start + limit > samples) break;
        double re = 0;
        for (int k = begin; k < limit; k += stride) for (int j = k; j < k+taps; ++j)
            re += energy(w->iq.fine[start+j]);
        starts[frames] = start;
        d[frames++] = sqrt(te*re);
    }
    conditioned_single(w->iq.data, w->reference.data, starts, frames, limit, &correlations[0][0]);
    for (int f = 0; f < frames; ++f) if (d[f] > 0) sum += hypot(correlations[f][0], correlations[f][1]) / d[f];
    return frames ? sum / frames : 0;
}

static int equivalent(const PortableVerifierResult *a, const PortableVerifierResult *b,
                      const PortableVerifierSeed *seeds) {
    return seeds[a->seed_index].epoch == seeds[b->seed_index].epoch &&
           fabs(a->acquired_hz - b->acquired_hz) <= 1e-9 &&
           fabs(a->verify - b->verify) <= 2e-12 && fabs(a->verify_control - b->verify_control) <= 2e-12 &&
           fabs(a->conditioned - b->conditioned) <= 2e-12 && fabs(a->acquire - b->acquire) <= 2e-12;
}

static int before(const PortableVerifierResult *a, const PortableVerifierResult *b,
                  const PortableVerifierSeed *seeds) {
    /* Preserve seed order when two routes reduce to the same physical candidate. */
    if (equivalent(a, b, seeds)) return 0;
    const double x[] = {a->verify - a->verify_control, a->verify, a->conditioned, a->acquire,
                        -fabs(a->acquired_residual_hz), -(double)seeds[a->seed_index].epoch};
    const double y[] = {b->verify - b->verify_control, b->verify, b->conditioned, b->acquire,
                        -fabs(b->acquired_residual_hz), -(double)seeds[b->seed_index].epoch};
    for (unsigned i = 0; i < sizeof(x)/sizeof(*x); ++i) if (x[i] != y[i]) return x[i] > y[i];
    return 0;
}

int portable_verifier_acquire(PortableVerifier *w, const PortableVerifierSeed *seeds,
                              unsigned count, double center, double low, double high,
                              PortableVerifierResult *out) {
    if (!w || !seeds || !out || !count || count > PORTABLE_VERIFIER_MAX_SEEDS ||
        !isfinite(center) || !isfinite(low) || !isfinite(high) || low >= high ||
        center + low < -rate/2 || center + high > rate/2) return -1;
    for (unsigned i = 0; i < count; ++i) {
        const PortableVerifierSeed *seed = &seeds[i];
        double fine_scores[PORTABLE_FINE_MAX_BINS], conditioned[max_bins];
        unsigned frames;
        PortableFinePeak peak;
        if (seed->bins < 2 || seed->bins > PORTABLE_FINE_MAX_BINS ||
            seed->absolute_hz != center + seed->residual_hz ||
            !isfinite(seed->residual_hz) || seed->residual_hz < low ||
            seed->residual_hz + 500.0 * (seed->bins - 1) > high ||
            portable_fine_score(&w->fine, w->iq.fine, w->exact, seed->epoch, seed->absolute_hz,
                                seed->bins, fine_scores, &frames) ||
            portable_fine_peak(fine_scores, seed->residual_hz, seed->bins, &peak)) return -1;
        memset(&out[i], 0, sizeof(out[i]));
        out[i].seed_index = i;
        out[i].fine_winner = peak.winner;
        out[i].fine_residual_hz = peak.interpolated_hz;
        if (peak.guard) out[i].flags |= PORTABLE_VERIFIER_FINE_GUARD;
        out[i].conditioned_bins = bounded_grid(fmax(low, peak.interpolated_hz - 2000),
                                               fmin(high, peak.interpolated_hz + 2000), conditioned);
        if (!out[i].conditioned_bins) return -1;
        condition(w, seed->epoch, center, conditioned, &out[i]);
        out[i].acquire = pilots(w, seed->epoch, out[i].acquired_hz, w->exact, 2);
        out[i].verify = pilots(w, seed->epoch, out[i].acquired_hz, w->exact, 3);
        out[i].verify_control = pilots(w, seed->epoch, out[i].acquired_hz, w->control, 3);
    }
    for (unsigned i = 1; i < count; ++i) for (unsigned j = 0; j < i; ++j) {
        if (equivalent(&out[i], &out[j], seeds)) {
            out[i].flags |= PORTABLE_VERIFIER_ACQUISITION_EQUIVALENT_TIE;
            out[j].flags |= PORTABLE_VERIFIER_ACQUISITION_EQUIVALENT_TIE;
        }
    }
    for (unsigned i = 1; i < count; ++i) {
        PortableVerifierResult candidate = out[i];
        unsigned j = i;
        while (j && before(&candidate, &out[j-1], seeds)) { out[j] = out[j-1]; --j; }
        out[j] = candidate;
    }
    return 0;
}

static inline double sinc(double x) { return x == 0 ? 1 : sin((tau/2)*x)/((tau/2)*x); }
static int compare_double(const void *a, const void *b) {
    double left = *(const double *)a, right = *(const double *)b;
    return (left > right) - (left < right);
}

static double glrt_spectrum(PortableVerifier *w, const GlrtComplex *values, int frames,
                            int *winner, unsigned *flags) {
    double spectra[short_size] = {0}, ceiling = 0;
    *winner = 0;
    for (int frame = 0; frame < frames; ++frame) {
        double row = 0;
        memset(w->fft_input, 0, short_size*sizeof(*w->fft_input));
        for (int k = 0; k < 64; ++k) {
            GlrtComplex z = values[frame*64+k];
            w->fft_input[k] = z.re + I*z.im;
            row += hypot(z.re, z.im);
        }
        ceiling += row*row;
        leo_fft_forward(&w->fft128, w->fft_input);
        for (int k = 0; k < short_size; ++k) {
            double re = creal(w->fft128.output[k]), im = cimag(w->fft128.output[k]);
            spectra[k] += re*re + im*im;
        }
    }
    if (ceiling == 0) return 0;
    for (int k = 0; k < short_size; ++k) w->fft_input[k] = spectra[k];
    leo_fft_forward(&w->fft128, w->fft_input);
    memset(w->fft_input, 0, sizeof(w->fft_input));
    for (int k = 0; k < 64; ++k) w->fft_input[k] = conj(w->fft128.output[k])/short_size;
    for (int k = 1; k < 64; ++k) w->fft_input[glrt_size-k] = conj(w->fft128.output[short_size-k])/short_size;
    leo_fft_forward(&w->fft512, w->fft_input);
    double best = -INFINITY, second = -INFINITY;
    for (int k = 0; k < glrt_size; ++k) {
        double score = creal(w->fft512.output[k]);
        if (score > best) { second = best; best = score; *winner = k; }
        else if (score > second) second = score;
    }
    if (best - second <= 1e-12 * ceiling) *flags |= PORTABLE_VERIFIER_GLRT_BIN_TIE;
    return best / ceiling;
}

static int glrt(PortableVerifier *w, unsigned ep, double cfo, double offset,
                double *exact, double *control, double *residual, unsigned *flags) {
    int integer = fabs(offset - nearbyint(offset)) <= 1e-12;
    int frames = 0;
    int32_t starts[max_frames];
    double steps[max_frames * 63];
    for (int frame = 0; frame < max_frames; ++frame) {
        int start = frame_start(ep, frame);
        if (start + first + offset < (integer ? 0 : 7) ||
            start + stop - 1 + offset >= samples - (integer ? 0 : 8)) break;
        starts[frames] = start;
        double previous = (start + first + offset + 21.5) / rate;
        for (int symbol = 1; symbol < 64; ++symbol) {
            double next = (start + first + symbol*taps + offset + 21.5) / rate;
            steps[frames*63 + symbol - 1] = next - previous;
            previous = next;
        }
        ++frames;
    }
    if (!frames) { *exact = *control = *residual = 0; return 0; }
    if (integer) {
        for (int f = 0; f < frames; ++f) starts[f] += first + (int)nearbyint(offset);
        for (int k = 0; k < aperture; ++k) {
            PortableFineComplex z = rotate(-tau*cfo*(first+k)/rate);
            w->glrt_rotation[k] = (GlrtComplex){z.r,z.i};
        }
        const int32_t zero = 0;
        correlated_integer(w->iq.glrt, starts, 1, frames, &zero, w->glrt_rotation,
                           w->glrt_exact, w->glrt_control, w->correlations[0], w->correlations[1]);
    } else {
        double old_fraction = NAN;
        int row = -1;
        for (int f = 0; f < frames; ++f) for (int k = 0; k < aperture; ++k) {
            const int index = f*aperture+k;
            const double position = starts[f] + first+k + offset;
            const int base = (int)position;
            const double fraction = position - base;
            w->indices[index] = base - 7;
            if (fraction != old_fraction) {
                double norm = 0;
                /* Rounded fractions change at floating-point exponent boundaries. */
                if (++row >= rounded_weight_rows) return -1;
                for (int t = 0; t < 16; ++t) {
                    double distance = fraction - (t - 7);
                    w->weights[row][t] = sinc(distance)*sinc(distance/8);
                    norm += w->weights[row][t];
                }
                for (int t = 0; t < 16; ++t) w->weights[row][t] /= norm;
                old_fraction = fraction;
            }
            w->weight_row[index] = row;
            PortableFineComplex z = rotate(-tau*cfo*position/rate);
            w->glrt_rotation[index] = (GlrtComplex){z.r,z.i};
        }
        correlated_fractional(w->iq.glrt, w->indices, frames, w->weight_row, &w->weights[0][0],
                              w->glrt_rotation, w->glrt_exact, w->glrt_control,
                              w->correlations[0], w->correlations[1]);
    }
    int best, unused;
    *exact = glrt_spectrum(w, w->correlations[0], frames, &best, flags);
    *control = glrt_spectrum(w, w->correlations[1], frames, &unused, flags);
    int count = frames*63;
    qsort(steps, count, sizeof(*steps), compare_double);
    double median = (steps[(count-1)/2] + steps[count/2])/2;
    *residual = (best < 256 ? best : best-512) * (1.0/(glrt_size*median));
    return 0;
}

int portable_verifier_fractional_peak(const double *scores, double *offset, double *curvature) {
    if (!scores || !offset || !curvature) return -1;
    int best = 0;
    for (int i = 0; i < 5; ++i) {
        if (!isfinite(scores[i]) || scores[i] < 0) return -1;
        if (scores[i] > scores[best]) best = i;
    }
    if (best == 0 || best == 4) return 0;
    double left = log(fmax(scores[best-1], DBL_MIN));
    double mid = log(fmax(scores[best], DBL_MIN)), right = log(fmax(scores[best+1], DBL_MIN));
    *curvature = left - 2*mid + right;
    if (!isfinite(*curvature) || *curvature >= -DBL_EPSILON) return 0;
    *offset = best-2 + fmax(-0.5, fmin(0.5, 0.5*(left-right)/ *curvature));
    return 1;
}

static int passes(double margin, unsigned *flags) {
    if (fabs(margin - gate) <= 2e-12) *flags |= PORTABLE_VERIFIER_GATE_GUARD;
    return margin >= gate;
}

int portable_verifier_glrt(PortableVerifier *w, unsigned epoch, PortableVerifierResult *out) {
    if (!w || !out || epoch >= n || !isfinite(out->acquired_hz) || fabs(out->acquired_hz) > rate/2) return -1;
    double freq = out->acquired_hz;
    for (int k = 0; k < 5; ++k) {
        unsigned ep = (epoch + n + k - 2) % n;
        double residual;
        if (glrt(w, ep, freq, 0, &out->exact_grid[k], &out->control_grid[k], &residual, &out->flags))
            return -1;
        if (k == 2) out->integer_residual_hz = residual;
    }
    out->integer_exact = out->exact_grid[2];
    out->integer_control = out->control_grid[2];
    if (passes(out->integer_exact - out->integer_control, &out->flags))
        out->flags |= PORTABLE_VERIFIER_INTEGER_GATE;
    int peak = portable_verifier_fractional_peak(out->exact_grid, &out->offset_samples, &out->curvature);
    if (peak < 0) return -1;
    if (peak) {
        out->flags |= PORTABLE_VERIFIER_FRACTIONAL_COMPLETE;
        if (glrt(w, epoch, freq, out->offset_samples, &out->fractional_exact, &out->fractional_control,
                 &out->fractional_residual_hz, &out->flags)) return -1;
        if (passes(out->fractional_exact - out->fractional_control, &out->flags))
            out->flags |= PORTABLE_VERIFIER_FRACTIONAL_GATE;
    }
    return 0;
}
