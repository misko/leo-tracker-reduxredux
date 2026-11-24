/* Research overlay, after the original find_times and before its callers. */
#include <fenv.h>
#include <float.h>
#include <immintrin.h>
#include <time.h>

enum { q_rows = 64, q_cols = 75, q_pitch = 80, q_size = q_rows * q_cols, q_cells = q_rows * q_pitch };

typedef struct {
    _Alignas(32) int16_t re[q_cells], im[q_cells];
    uint16_t input[q_size], output[q_size];
    int16_t cosine[q_rows], sine[q_rows];
    fftwf_complex *partial;
    fftwf_plan fwd, inv;
} Q15Plan;

typedef struct {
    uint64_t ns;
    double score_radius, smallest_gap;
    int epochs[clocks], tentative[clocks];
    int fallback;
} Q15Trace;

static _Thread_local Q15Plan *q_plan;
static _Thread_local Q15Trace q_trace[2];
static _Thread_local int q_mode, q_traces;

static int reverse_six(int input) {
    int value = 0;
    for (int step = 0; step < 6; ++step) {
        value = value * 2 + input % 2;
        input /= 2;
    }
    return value;
}

static void q15_release(Q15Plan *p) {
    if (p->fwd) fftwf_destroy_plan(p->fwd);
    if (p->inv) fftwf_destroy_plan(p->inv);
    fftwf_free(p->partial);
    free(p);
}

static Q15Plan *q15_prepare(void) {
    Q15Plan *p = aligned_alloc(32, sizeof(*p));
    if (!p) return NULL;
    *p = (Q15Plan){0};
    p->partial = fftwf_alloc_complex(q_cells);
    if (!p->partial) {
        q15_release(p);
        return NULL;
    }
    const int len = q_cols;
    p->fwd = fftwf_plan_many_dft(1, &len, q_rows, p->partial, NULL, 1, q_pitch,
                                p->partial, NULL, 1, q_pitch, FFTW_FORWARD, FFTW_ESTIMATE);
    p->inv = fftwf_plan_many_dft(1, &len, q_rows, p->partial, NULL, 1, q_pitch,
                                p->partial, NULL, 1, q_pitch, FFTW_BACKWARD, FFTW_ESTIMATE);
    if (!p->fwd || !p->inv) {
        q15_release(p);
        return NULL;
    }
    for (int i = 0; i < q_size; ++i) {
        // 35 = 75^-1 mod 64 and 34 = 64^-1 mod 75. The DIF stage stores bit-reversed bins.
        p->input[i] = q_pitch * (i % q_rows) + i % q_cols;
        p->output[i] = q_pitch * reverse_six(i * 35 % q_rows) + i * 34 % q_cols;
    }
    for (int i = 0; i < q_rows; ++i) {
        const double angle = turn * i / q_rows;
        p->cosine[i] = (int16_t)lrint(32767 * cos(angle));
        p->sine[i] = (int16_t)lrint(32767 * sin(angle));
    }
    return p;
}

__attribute__((target("avx2")))
static inline __m256i q15_half_sum(__m256i a, __m256i b) {
    const __m256i sign = _mm256_set1_epi16(INT16_MIN);
    return _mm256_xor_si256(sign, _mm256_avg_epu16(_mm256_xor_si256(sign, a), _mm256_xor_si256(sign, b)));
}

__attribute__((target("avx2")))
static void q15_fft64(Q15Plan *p, int backward) {
    const __m256i zero = _mm256_setzero_si256();
    for (int width = q_rows; width > 1; width /= 2) {
        int half = width / 2;
        for (int first = 0; first < q_rows; first += width) {
            for (int i = 0; i < half; ++i) {
                int root = i * (q_rows / width);
                __m256i c = _mm256_set1_epi16(p->cosine[root]);
                __m256i s = _mm256_set1_epi16(backward ? p->sine[root] : -p->sine[root]);
                __m256i *ar = (__m256i *)(p->re + (first + i) * q_pitch);
                __m256i *ai = (__m256i *)(p->im + (first + i) * q_pitch);
                __m256i *br = ar + half * q_pitch / 16;
                __m256i *bi = ai + half * q_pitch / 16;
                for (int j = 0; j < q_pitch / 16; ++j) {
                    __m256i a = _mm256_load_si256(ar + j), b = _mm256_load_si256(br + j);
                    __m256i u = _mm256_load_si256(ai + j), v = _mm256_load_si256(bi + j);
                    _mm256_store_si256(ar + j, q15_half_sum(a, b));
                    _mm256_store_si256(ai + j, q15_half_sum(u, v));
                    __m256i dr = q15_half_sum(a, _mm256_sub_epi16(zero, b));
                    __m256i di = q15_half_sum(u, _mm256_sub_epi16(zero, v));
                    if (root) {
                        __m256i tr = _mm256_sub_epi16(_mm256_mulhrs_epi16(dr, c), _mm256_mulhrs_epi16(di, s));
                        di = _mm256_add_epi16(_mm256_mulhrs_epi16(dr, s), _mm256_mulhrs_epi16(di, c));
                        dr = tr;
                    }
                    _mm256_store_si256(br + j, dr);
                    _mm256_store_si256(bi + j, di);
                }
            }
        }
    }
}

__attribute__((target("avx2")))
static float q15_maximum(const Sample *restrict data) {
    __m256 largest = _mm256_setzero_ps(), valid = _mm256_cmp_ps(largest, largest, _CMP_EQ_OQ);
    const __m256 sign = _mm256_set1_ps(-0.f), ceiling = _mm256_set1_ps(FLT_MAX);
    for (int i = 0; i < q_size; i += 4) {
        __m256 v = _mm256_andnot_ps(sign, _mm256_loadu_ps((const float *)(data + i)));
        valid = _mm256_and_ps(valid, _mm256_cmp_ps(v, ceiling, _CMP_LE_OQ));
        largest = _mm256_max_ps(largest, v);
    }
    if (_mm256_movemask_ps(valid) != 255) return NAN;
    float lane[8];
    _mm256_storeu_ps(lane, largest);
    float result = 0.f;
    for (int i = 0; i < 8; ++i)
        if (lane[i] > result) result = lane[i];
    return result;
}

static double q15_transform(Q15Plan *p, Sample *data, int backward) {
    float largest = q15_maximum(data);
    if (largest == 0.f) return 0.;
    if (!(largest >= 1e-25f && largest <= 1e25f)) return -1.;
    float scale = 16000.f / largest;
    // 16000 leaves sqrt(2) complex magnitude headroom plus over 10000 guard units.
    for (int i = 0; i < q_size; ++i) {
        unsigned k = p->input[i];
        p->re[k] = (int16_t)lrintf(data[i].re * scale);
        p->im[k] = (int16_t)lrintf(data[i].im * scale);
    }
    q15_fft64(p, backward);
    for (int i = 0; i < q_cells; ++i) {
        p->partial[i][0] = (float)p->re[i];
        p->partial[i][1] = (float)p->im[i];
    }
    fftwf_execute(backward ? p->inv : p->fwd);
    float unscale = q_rows / scale;
    for (int i = 0; i < q_size; ++i) {
        unsigned k = p->output[i];
        data[i] = (Sample){p->partial[k][0] * unscale, p->partial[k][1] * unscale};
    }
    // Entry rounding plus six normalized stages at four complex units per stage.
    // The 75-point float transform amplifies an absolute per-input error by at most 75.
    return 25. * q_size / scale;
}

static int q15_choose(double *scores, int n, int radius, int *peaks, int count, double bound, double *gap) {
    *gap = INFINITY;
    int clear = 1;
    for (int k = 0; k < count; ++k) {
        int best = 0;
        double second = -INFINITY;
        for (int i = 1; i < n; ++i) {
            if (scores[i] > scores[best]) {
                if (bound >= 0.) second = scores[best];
                best = i;
            } else if (bound >= 0. && scores[i] > second) {
                second = scores[i];
            }
        }
        if (bound >= 0.) {
            double margin = scores[best] - second;
            if (margin < *gap) *gap = margin;
            if (!(margin > 2. * bound)) clear = 0;
        }
        peaks[k] = best;
        for (int j = -radius; j <= radius; ++j)
            scores[(best + j + n) % n] = -1.;
    }
    return clear;
}

static int q15_guess(TimingFirst *w, Q15Trace *trace) {
    if (!q_plan || w->stride != 4 || w->epochs != 3333 || w->correlation_size != q_size
            || !__builtin_cpu_supports("avx2") || fegetround() != FE_TONEAREST)
        return 1;
    memset(w->time_score, 0, w->epochs * sizeof(double));
    for (int k = 0; k < lags; ++k) {
        int lag = displacement(w, k), length = w->length - lag;
        spectral_lag_products(w->scratch, w->prefix, w->modes, w->modes + w->width, w->width, lag, q_size);
        double forward = q15_transform(q_plan, w->scratch, 0);
        if (forward < 0.) return 1;
        spectral_filter(w->scratch, w->filters + k * q_size, q_size);
        double inverse = q15_transform(q_plan, w->scratch, 1);
        if (inverse < 0.) return 1;
        spectral_timing_scores(w->time_score, w->prefix, w->scratch, w->epochs, length, q_size);
        if (q_mode == 2) {
            // A unit-energy filter has mean spectral magnitude <= 1 by Parseval.
            // Allow double that transfer and a small extra radius for float operations.
            double error = 2. * forward + inverse / q_size;
            double magnitude2 = 0., energy = INFINITY;
            for (int i = 0; i < w->epochs; ++i) {
                double re = w->scratch[i].re, im = w->scratch[i].im;
                magnitude2 = fmax(magnitude2, re * re + im * im);
                energy = fmin(energy, w->prefix[i + length] - w->prefix[i]);
            }
            double amplitude = sqrt(magnitude2) / q_size;
            error += 1e-5 * amplitude;
            trace->score_radius += error * (2. * amplitude + error) / fmax(energy, 1e-20);
        }
    }
    double smallest;
    double bound = q_mode == 2 ? trace->score_radius : -1.;
    int clear = q15_choose(w->time_score, w->epochs, (int)nearbyint(6. / w->stride),
                           trace->tentative, clocks, bound, &smallest);
    trace->smallest_gap = isfinite(smallest) ? smallest : 0.;
    return clear ? 0 : 2;
}

static uint64_t q15_now(void) {
    struct timespec t;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
    return UINT64_C(1000000000) * t.tv_sec + t.tv_nsec;
}

static void find_times_trial(TimingFirst *w, int *epochs) {
    if (q_traces < 0 || q_traces >= 2) {
        q_traces = -1;
        find_times(w, epochs);
        return;
    }
    Q15Trace *trace = q_trace + q_traces++;
    *trace = (Q15Trace){0};
    uint64_t start = q15_now();
    if (q_mode) trace->fallback = q15_guess(w, trace);
    if (!q_mode || trace->fallback)
        find_times(w, epochs);
    else
        memcpy(epochs, trace->tentative, sizeof(trace->tentative));
    trace->ns = q15_now() - start;
    memcpy(trace->epochs, epochs, sizeof(trace->epochs));
}

int timing_q15_set(int mode) {
    if (mode < 0 || mode > 2) return -1;
    if (mode && !q_plan && __builtin_cpu_supports("avx2")) q_plan = q15_prepare();
    if (mode && !q_plan) return -1;
    q_traces = 0;
    q_mode = mode;
    return 0;
}

int timing_q15_read(Q15Trace *result) {
    if (q_traces > 0) memcpy(result, q_trace, q_traces * sizeof(*result));
    return q_traces;
}

void timing_q15_free(void) {
    if (q_plan) q15_release(q_plan);
    q_plan = NULL;
}

double timing_q15_test_transform(float *data, int backward) {
    if (timing_q15_set(1) || fegetround() != FE_TONEAREST) return -1.;
    return q15_transform(q_plan, (Sample *)data, backward);
}

int timing_q15_test_peaks(double *data, int n, int radius, int *peaks, int count, double bound) {
    double gap;
    if (radius < 0 || count < 1 || n / (2 * radius + 1) < count) return -1;
    return q15_choose(data, n, radius, peaks, count, bound, &gap);
}
