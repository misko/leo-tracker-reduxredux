#include <stdint.h>
#include <time.h>

static _Thread_local int jacobi_columns_on, jacobi_trace_on;
static _Thread_local uint64_t jacobi_trace[3];

int receiver_jacobi_columns_mode(int enabled, int trace)
{
#if defined(__x86_64__) || defined(__i386__)
    if (enabled && !__builtin_cpu_supports("avx2")) return -1;
#else
    if (enabled) return -1;
#endif
    jacobi_columns_on = enabled;
    jacobi_trace_on = trace;
    memset(jacobi_trace, 0, sizeof(jacobi_trace));
    return enabled;
}

void receiver_jacobi_columns_times(uint64_t *times)
{
    memcpy(times, jacobi_trace, sizeof(jacobi_trace));
}

static uint64_t jacobi_now(void)
{
    if (!jacobi_trace_on) return 0;
    struct timespec reading;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &reading);
    return (uint64_t)reading.tv_sec * 1000000000 + reading.tv_nsec;
}

static void jacobi_add_time(int slot, uint64_t start)
{
    if (start) jacobi_trace[slot] += jacobi_now() - start;
}

static int jacobi_columns_eligible(const double complex covariance[count][count])
{
    if (!jacobi_columns_on) return 0;
    for (int p = 0; p < count; ++p)
        for (int q = 0; q < count; ++q)
            if (!isfinite(creal(covariance[p][q])) || !isfinite(cimag(covariance[p][q])))
                return 0;
    return 1;
}

#if defined(__x86_64__) || defined(__i386__)
#include <immintrin.h>

#define JACOBI_AVX2 __attribute__((target("avx2"), always_inline)) static inline

JACOBI_AVX2 __m256d jacobi_load_pair(const double complex *first, const double complex *second)
{
    return _mm256_set_m128d(_mm_loadu_pd((const double *)second), _mm_loadu_pd((const double *)first));
}

JACOBI_AVX2 void jacobi_store_pair(double complex *first, double complex *second, __m256d values)
{
    _mm_storeu_pd((double *)first, _mm256_castpd256_pd128(values));
    _mm_storeu_pd((double *)second, _mm256_extractf128_pd(values, 1));
}

JACOBI_AVX2 __m256d jacobi_product(__m256d r, __m256d i, __m256d values)
{
    return _mm256_addsub_pd(_mm256_mul_pd(r, values), _mm256_mul_pd(i, _mm256_permute_pd(values, 5)));
}

JACOBI_AVX2 void jacobi_pair(__m256d x, __m256d y, __m256d c, __m256d real, __m256d imag,
                            __m256d minus_imag, __m256d *out_x, __m256d *out_y)
{
    *out_x = _mm256_sub_pd(_mm256_mul_pd(c, x), jacobi_product(real, minus_imag, y));
    *out_y = _mm256_add_pd(jacobi_product(real, imag, x), _mm256_mul_pd(c, y));
}

__attribute__((target("avx2")))
static void jacobi_rotate_columns(double complex covariance[count][count], double complex axis[count][count],
                                   int p, int q, double cosine, double complex sine)
{
    const __m256d c = _mm256_set1_pd(cosine), real = _mm256_set1_pd(creal(sine));
    const __m256d imag = _mm256_set1_pd(cimag(sine)), minus_imag = _mm256_set1_pd(-cimag(sine));
    const __m256d conjugate_mask = _mm256_set_pd(-0.0, 0.0, -0.0, 0.0);
    // The axes use contiguous columns during the solve.
    int k = 0;
    for (; k + 1 < count; k += 2) {
        __m256d x = _mm256_loadu_pd((const double *)&axis[p][k]);
        __m256d y = _mm256_loadu_pd((const double *)&axis[q][k]);
        __m256d a, b;
        jacobi_pair(x, y, c, real, imag, minus_imag, &a, &b);
        _mm256_storeu_pd((double *)&axis[p][k], a);
        _mm256_storeu_pd((double *)&axis[q][k], b);
    }
    if (k < count) {
        double complex x = axis[p][k], y = axis[q][k];
        axis[p][k] = cosine * x - conj(sine) * y;
        axis[q][k] = sine * x + cosine * y;
    }
    // Skip both pivot rows while retaining the exact stored Hermitian pairs.
    for (k = 0; k < count;) {
        if (k == p || k == q) {
            ++k;
            continue;
        }
        if (k + 1 < count && k + 1 != p && k + 1 != q) {
            __m256d x = jacobi_load_pair(&covariance[k][p], &covariance[k + 1][p]);
            __m256d y = jacobi_load_pair(&covariance[k][q], &covariance[k + 1][q]);
            __m256d a, b;
            jacobi_pair(x, y, c, real, imag, minus_imag, &a, &b);
            jacobi_store_pair(&covariance[k][p], &covariance[k + 1][p], a);
            jacobi_store_pair(&covariance[k][q], &covariance[k + 1][q], b);
            _mm256_storeu_pd((double *)&covariance[p][k], _mm256_xor_pd(a, conjugate_mask));
            _mm256_storeu_pd((double *)&covariance[q][k], _mm256_xor_pd(b, conjugate_mask));
            k += 2;
            continue;
        }
        double complex x = covariance[k][p], y = covariance[k][q];
        covariance[k][p] = cosine * x - conj(sine) * y;
        covariance[p][k] = conj(covariance[k][p]);
        covariance[k][q] = sine * x + cosine * y;
        covariance[q][k] = conj(covariance[k][q]);
        ++k;
    }
}
#undef JACOBI_AVX2
#else
static void jacobi_rotate_columns(double complex covariance[count][count], double complex axis[count][count],
                                   int p, int q, double cosine, double complex sine)
{
    (void)covariance; (void)axis; (void)p; (void)q; (void)cosine; (void)sine;
}
#endif

static void jacobi_restore_axis(double complex axis[count][count])
{
    for (int i = 0; i < count; ++i)
        for (int j = 0; j < i; ++j) {
            double complex temporary = axis[i][j];
            axis[i][j] = axis[j][i];
            axis[j][i] = temporary;
        }
}
