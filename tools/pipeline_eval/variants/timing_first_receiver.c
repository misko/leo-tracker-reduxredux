/* Allocation-free per-visit receiver. All transforms in this method are powers of two. */
#include "timing_first_receiver.h"

#include <complex.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    float re, im;
} Sample;
_Static_assert(sizeof(Sample) == 2 * sizeof(float), "pilot and FIR require interleaved float32");
typedef struct {
    double power;
    int epoch, bin;
} Seed;
typedef struct {
    double epoch, hz, score;
    int sample;
} Peak;
enum {
    points = 200000,
    period = 13333,
    first = 88,
    symbol = 44,
    count = 14,
    lags = 8,
    clocks = 12,
    bins = 4096,
    choices = 4,
    max_peaks = 16
};
static const double turn = 6.283185307179586476925286766559;
static const int half_lags[lags] = {3, 7, 13, 22, 37, 55, 88, 149};
int delay_decimate(const float *, const float *, int, int, float *);
int delay_refine(const float *, const float *, int, double, double, double, double *);

struct TimingFirst {
    int stride, rate, epochs, width, fft_size, length;
    size_t allocated;
    Sample *pilot, *code, *data, *low, *frames, *modes, *filters, *scratch, *roots;
    int *reverse;
    double *prefix, *time_score, *power;
    float fir[81];
};

static Sample multiply(Sample a, Sample b) {
    return (Sample){a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re};
}
static inline float power(Sample a) { return a.re * a.re + a.im * a.im; }
static inline Sample conjugate(Sample a) { return (Sample){a.re, -a.im}; }
static int rounded_offset(int frame, int stride) {
    return (int)nearbyint(frame * 1e7 / (750. * stride));
}
static void *reserve(TimingFirst *w, size_t n, size_t bytes) {
    w->allocated += n * bytes;
    return calloc(n, bytes);
}

static void transform(TimingFirst *w, int n, int backward) {
    Sample *a = w->scratch;
    int shift = 0;
    for (int p = n; p < w->fft_size; p *= 2)
        ++shift;
    for (int i = 0; i < n; ++i) {
        int j = w->reverse[i] >> shift;
        if (j > i) {
            Sample saved = a[i];
            a[i] = a[j];
            a[j] = saved;
        }
    }
    for (int half = 1; half < n; half *= 2) {
        int step = w->fft_size / (2 * half);
        for (int i = 0; i < n; i += 2 * half) {
            for (int k = 0; k < half; ++k) {
                Sample coeff = w->roots[k * step];
                if (backward)
                    coeff.im = -coeff.im;
                Sample b = multiply(coeff, a[i + k + half]), s = a[i + k];
                a[i + k] = (Sample){s.re + b.re, s.im + b.im};
                a[i + k + half] = (Sample){s.re - b.re, s.im - b.im};
            }
        }
    }
    if (backward)
        for (int i = 0; i < n; ++i) {
            a[i].re /= n;
            a[i].im /= n;
        }
}

static int displacement(const TimingFirst *w, int index) {
    return (int)fmax(1., nearbyint(2. * half_lags[index] / w->stride));
}

static void prepare(TimingFirst *w) {
    for (int i = 0; i < w->fft_size / 2; ++i) {
        double a = -turn * i / w->fft_size;
        w->roots[i] = (Sample){(float)cos(a), (float)sin(a)};
    }
    for (int i = 1; i < w->fft_size; ++i)
        w->reverse[i] = (w->reverse[i >> 1] >> 1) | ((i & 1) * (w->fft_size / 2));
    for (int i = 0; i < w->length; ++i) {
        int at = first + i * w->stride;
        if (w->stride == 1)
            w->code[i] = w->pilot[at];
        else {
            float re = 0.f, im = 0.f;
            for (int k = 0; k < 81; ++k) {
                re += w->fir[k] * w->pilot[at + k - 40].re;
                im += w->fir[k] * w->pilot[at + k - 40].im;
            }
            w->code[i] = (Sample){re, im};
        }
    }
    for (int j = 0; j < lags; ++j) {
        int lag = displacement(w, j), length = w->length - lag;
        memset(w->scratch, 0, w->fft_size * sizeof(Sample));
        double re = 0., im = 0., energy = 0.;
        for (int i = 0; i < length; ++i) {
            Sample p = multiply(w->code[i + lag], conjugate(w->code[i]));
            w->scratch[i] = p;
            re += p.re;
            im += p.im;
        }
        for (int i = 0; i < length; ++i) {
            w->scratch[i].re -= (float)(re / length);
            w->scratch[i].im -= (float)(im / length);
            energy += power(w->scratch[i]);
        }
        transform(w, w->fft_size, 0);
        float scale = (float)(1. / sqrt(fmax(energy, 1e-25)));
        for (int i = 0; i < w->fft_size; ++i)
            w->filters[j * w->fft_size + i] =
                (Sample){w->scratch[i].re * scale, -w->scratch[i].im * scale};
    }
}

void timing_first_free(TimingFirst *w) {
    if (!w)
        return;
    free(w->pilot);
    free(w->code);
    free(w->data);
    free(w->low);
    free(w->frames);
    free(w->modes);
    free(w->filters);
    free(w->scratch);
    free(w->roots);
    free(w->reverse);
    free(w->prefix);
    free(w->time_score);
    free(w->power);
    free(w);
}

TimingFirst *timing_first_create(int stride, const float *pilot, const float *fir) {
    if (!pilot || (stride != 1 && stride != 4) || (stride == 4 && !fir))
        return NULL;
    TimingFirst *w = calloc(1, sizeof(*w));
    if (!w)
        return NULL;
    w->allocated = sizeof(*w);
    w->stride = stride;
    w->rate = 10000000 / stride;
    w->epochs = (int)nearbyint(w->rate / 750.);
    w->length = 128 * symbol / stride;
    w->width = w->epochs + w->length - 1;
    w->fft_size = 32768 / stride;
    if (stride == 4)
        memcpy(w->fir, fir, sizeof(w->fir));
    w->pilot = reserve(w, period, sizeof(Sample));
    w->code = reserve(w, w->length, sizeof(Sample));
    w->data = reserve(w, points, sizeof(Sample));
    if (stride == 4)
        w->low = reserve(w, points / stride, sizeof(Sample));
    w->frames = reserve(w, count * w->width, sizeof(Sample));
    w->modes = reserve(w, 2 * w->width, sizeof(Sample));
    w->filters = reserve(w, lags * w->fft_size, sizeof(Sample));
    w->scratch = reserve(w, w->fft_size, sizeof(Sample));
    w->roots = reserve(w, w->fft_size / 2, sizeof(Sample));
    w->reverse = reserve(w, w->fft_size, sizeof(int));
    w->prefix = reserve(w, w->width + 1, sizeof(double));
    w->time_score = reserve(w, w->epochs, sizeof(double));
    w->power = reserve(w, bins, sizeof(double));
    if (!w->pilot || !w->code || !w->data || (stride == 4 && !w->low) || !w->frames || !w->modes ||
        !w->filters || !w->scratch || !w->roots || !w->reverse || !w->prefix || !w->time_score ||
        !w->power) {
        timing_first_free(w);
        return NULL;
    }
    memcpy(w->pilot, pilot, period * sizeof(Sample));
    prepare(w);
    return w;
}

size_t timing_first_bytes(const TimingFirst *w) { return w ? w->allocated : 0; }

/* Cyclic Jacobi rotations on the Hermitian 14 by 14 frame covariance. */
static void principal_modes(TimingFirst *w, const Sample *low) {
    double complex covariance[count][count] = {0}, axis[count][count] = {0};
    for (int f = 0; f < count; ++f) {
        int start = rounded_offset(f, w->stride) + first / w->stride;
        Sample *a = w->frames + f * w->width;
        double ar = 0., ai = 0., norm = 0.;
        for (int i = 0; i < w->width; ++i) {
            ar += low[start + i].re;
            ai += low[start + i].im;
        }
        for (int i = 0; i < w->width; ++i) {
            a[i] = (Sample){low[start + i].re - (float)(ar / w->width),
                            low[start + i].im - (float)(ai / w->width)};
            norm += power(a[i]);
        }
        float scale = (float)(1. / fmax(sqrt(norm / w->width), 1e-12));
        for (int i = 0; i < w->width; ++i) {
            a[i].re *= scale;
            a[i].im *= scale;
        }
        axis[f][f] = 1.;
        for (int other = 0; other <= f; ++other) {
            const Sample *b = w->frames + other * w->width;
            float re = 0.f, im = 0.f;
#pragma omp simd reduction(+ : re, im)
            for (int i = 0; i < w->width; ++i) {
                re += a[i].re * b[i].re + a[i].im * b[i].im;
                im += a[i].im * b[i].re - a[i].re * b[i].im;
            }
            covariance[f][other] = re + I * im;
            covariance[other][f] = re - I * im;
        }
    }
    for (int sweep = 0; sweep < 20; ++sweep) {
        int changed = 0;
        for (int p = 0; p < count - 1; ++p)
            for (int q = p + 1; q < count; ++q) {
                double complex elem = covariance[p][q];
                double r = cabs(elem), a = creal(covariance[p][p]), b = creal(covariance[q][q]);
                if (r <= 1e-10 * fmax(1., sqrt(fabs(a * b))))
                    continue;
                ++changed;
                double tau = (b - a) / (2 * r);
                double t = copysign(1., tau) / (fabs(tau) + hypot(1., tau));
                double c = 1. / sqrt(1. + t * t);
                double complex s = c * t * elem / r;
                for (int k = 0; k < count; ++k) {
                    if (k != p && k != q) {
                        double complex x = covariance[k][p], y = covariance[k][q];
                        covariance[k][p] = c * x - conj(s) * y;
                        covariance[p][k] = conj(covariance[k][p]);
                        covariance[k][q] = s * x + c * y;
                        covariance[q][k] = conj(covariance[k][q]);
                    }
                    double complex x = axis[k][p], y = axis[k][q];
                    axis[k][p] = c * x - conj(s) * y;
                    axis[k][q] = s * x + c * y;
                }
                covariance[p][p] = a - t * r;
                covariance[q][q] = b + t * r;
                covariance[p][q] = 0.;
                covariance[q][p] = 0.;
            }
        if (!changed)
            break;
    }
    memset(w->modes, 0, 2 * w->width * sizeof(Sample));
    for (int m = 0; m < 2; ++m) {
        int best = 0;
        for (int k = 1; k < count; ++k)
            if (creal(covariance[k][k]) > creal(covariance[best][best]))
                best = k;
        covariance[best][best] = -INFINITY;
        Sample *v = w->modes + m * w->width;
        for (int k = 0; k < count; ++k) {
            Sample weight = {(float)creal(axis[k][best]), (float)-cimag(axis[k][best])};
            const Sample *z = w->frames + k * w->width;
            for (int i = 0; i < w->width; ++i) {
                Sample add = multiply(weight, z[i]);
                v[i].re += add.re;
                v[i].im += add.im;
            }
        }
    }
}

/* A constant carrier rotates each lag product once. Squared correlation
   magnitude therefore ranks the frame epochs before we know the carrier. */
static void find_times(TimingFirst *w, int *epochs) {
    memset(w->time_score, 0, w->epochs * sizeof(double));
    for (int k = 0; k < lags; ++k) {
        int lag = displacement(w, k), len = w->length - lag;
        memset(w->scratch, 0, w->fft_size * sizeof(Sample));
        w->prefix[0] = 0.;
        for (int i = 0; i < w->width - lag; ++i) {
            Sample a = multiply(w->modes[i + lag], conjugate(w->modes[i]));
            Sample b = multiply(w->modes[w->width + i + lag], conjugate(w->modes[w->width + i]));
            w->scratch[i] = (Sample){a.re + b.re, a.im + b.im};
            w->prefix[i + 1] = w->prefix[i] + power(w->scratch[i]);
        }
        transform(w, w->fft_size, 0);
        for (int i = 0; i < w->fft_size; ++i)
            w->scratch[i] = multiply(w->scratch[i], w->filters[k * w->fft_size + i]);
        transform(w, w->fft_size, 1);
        for (int i = 0; i < w->epochs; ++i)
            w->time_score[i] +=
                power(w->scratch[i]) / fmax(w->prefix[i + len] - w->prefix[i], 1e-20);
    }
    int radius = (int)nearbyint(6. / w->stride);
    for (int k = 0; k < clocks; ++k) {
        int best = 0;
        for (int i = 1; i < w->epochs; ++i)
            if (w->time_score[i] > w->time_score[best])
                best = i;
        epochs[k] = best;
        for (int j = -radius; j <= radius; ++j)
            w->time_score[(best + j + w->epochs) % w->epochs] = -1.;
    }
}

static double bin_hz(const TimingFirst *w, int i) {
    return (i < bins / 2 ? i : i - bins) * (double)w->rate / bins;
}

static int find_carriers(TimingFirst *w, const int *epochs, double lo, double hi, double center,
                         Seed *all) {
    int used = 0, len = 64 * symbol / w->stride;
    for (int i = 0; i < clocks; ++i) {
        double energy = 0.;
        memset(w->power, 0, bins * sizeof(double));
        for (int m = 0; m < 2; ++m) {
            const Sample *v = w->modes + m * w->width + epochs[i];
            memset(w->scratch, 0, bins * sizeof(Sample));
            for (int j = 0; j < len; ++j) {
                w->scratch[j] = multiply(v[j], conjugate(w->code[j]));
                energy += power(v[j]);
            }
            transform(w, bins, 0);
            for (int j = 0; j < bins; ++j)
                w->power[j] += power(w->scratch[j]);
        }
        int prev = -1;
        for (int rep = 0; rep < 2; ++rep) {
            int best = -1;
            for (int j = 0; j < bins; ++j) {
                double f = bin_hz(w, j) + center;
                if (ceil((lo - f) / w->rate) > floor((hi - f) / w->rate))
                    continue;
                if (prev >= 0 && fabs(remainder(f - center - bin_hz(w, prev), w->rate)) < 10000.)
                    continue;
                if (best < 0 || w->power[j] > w->power[best])
                    best = j;
            }
            if (best < 0)
                break;
            all[used++] = (Seed){w->power[best] / fmax(energy, 1e-15), epochs[i] * w->stride, best};
            prev = best;
        }
    }
    return used;
}

/* At a proposed native carrier, every independent frame group must put the
   despread pilot at zero residual ahead of all 63 competing residuals. */
static int gate(TimingFirst *w, const Peak *p, int start_symbol, int early) {
    double groups[7][64] = {{0}};
    int groups_used = early ? 7 : 2;
    Sample rotation[64 * symbol];
    double angle = -turn * p->hz / 1e7, dr = cos(angle), di = sin(angle), ar = 1., ai = 0.;
    for (int i = 0; i < 64 * symbol; ++i) {
        rotation[i] = multiply(conjugate(w->pilot[first + start_symbol * symbol + i]),
                               (Sample){(float)ar, (float)ai});
        double next = ar * dr - ai * di;
        ai = ar * di + ai * dr;
        ar = next;
    }
    for (int f = 0; f < count; ++f) {
        int offset = rounded_offset(f, 1) + first + p->sample + start_symbol * symbol;
        if (offset + 64 * symbol > points)
            continue;
        for (int s = 0; s < 64; ++s) {
            float re = 0.f, im = 0.f;
            for (int k = 0; k < symbol; ++k) {
                int j = s * symbol + k;
                Sample z = multiply(w->data[offset + j], rotation[j]);
                re += z.re;
                im += z.im;
            }
            w->scratch[s] = (Sample){re, im};
        }
        transform(w, 64, 0);
        for (int b = 0; b < 64; ++b)
            groups[f % groups_used][b] += power(w->scratch[b]);
    }
    for (int i = 0; i < groups_used; ++i)
        for (int b = 1; b < 64; ++b)
            if (groups[i][b] >= groups[i][0])
                return 0;
    return 1;
}

static void input(TimingFirst *w, const int16_t *iq, int lane, double center) {
    double phase = -turn * center / 1e7, dr = cos(phase), di = sin(phase), ar = 1., ai = 0.;
    for (int i = 0; i < points; ++i) {
        Sample z = {iq[4 * i + 2 * lane], iq[4 * i + 2 * lane + 1]};
        if (center) {
            z = multiply(z, (Sample){(float)ar, (float)ai});
            double next = ar * dr - ai * di;
            ai = ar * di + ai * dr;
            ar = next;
        }
        w->data[i] = z;
    }
}

int timing_first_detect(TimingFirst *w, const int16_t *iq, int lane, double lo, double hi,
                        TimingFirstResult *out) {
    if (!w || !iq || !out || lane < 0 || lane > 1 || !(lo < hi) || lo < -5e6 || hi > 5e6 ||
        (w->stride == 4 && hi - lo > 1600000.))
        return -1;
    *out = (TimingFirstResult){0};
    double center = (lo + hi) / 2;
    input(w, iq, lane, center);
    const Sample *low = w->data;
    if (w->stride == 4) {
        if (delay_decimate((float *)w->data, w->fir, 81, 4, (float *)w->low))
            return -1;
        low = w->low;
    }
    principal_modes(w, low);
    int epochs[clocks];
    find_times(w, epochs);
    Seed seeds[2 * clocks];
    int n = find_carriers(w, epochs, lo, hi, center, seeds), done = 0;
    Peak peaks[max_peaks];
    if (center)
        input(w, iq, lane, 0.);
    for (int k = 0; k < choices && k < n; ++k) {
        int pick = 0;
        for (int i = 1; i < n; ++i)
            if (seeds[i].power > seeds[pick].power)
                pick = i;
        Seed selected = seeds[pick];
        seeds[pick].power = -1.;
        double base = bin_hz(w, selected.bin) + center;
        int lower = (int)ceil((lo - base) / w->rate), upper = (int)floor((hi - base) / w->rate);
        for (int branch = lower; branch <= upper && done < max_peaks; ++branch) {
            double v[4];
            if (delay_refine((float *)w->data, (float *)(w->pilot + first), selected.epoch,
                             base + branch * w->rate, lo, hi, v))
                return -1;
            peaks[done++] = (Peak){v[0], v[1], v[3], (int)v[2]};
        }
    }
    for (int k = 0; k < done; ++k) {
        int best = 0;
        for (int i = 1; i < done; ++i)
            if (peaks[i].score > peaks[best].score)
                best = i;
        Peak p = peaks[best];
        peaks[best].score = -1.;
        int why = 0;
        if (gate(w, &p, 160, 0) || gate(w, &p, 232, 0))
            why = 1;
        else if (gate(w, &p, 0, 1))
            why = 2;
        if (why) {
            *out = (TimingFirstResult){p.epoch, p.hz, p.score, why};
            break;
        }
    }
    return 0;
}
