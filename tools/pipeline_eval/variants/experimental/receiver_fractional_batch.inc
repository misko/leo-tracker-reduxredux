#include <immintrin.h>

/* Each vector holds two interleaved complex samples. The four Lanczos
   accumulation chains and the later four symbol chains retain their order. */
typedef struct { __m256d left, right; } FractionalPairs;

static inline __attribute__((target("avx2,fma"), always_inline))
__m256d fractional_product(__m256d a, __m256d b)
{
    __m256d cross = _mm256_mul_pd(_mm256_permute_pd(a, 15), _mm256_permute_pd(b, 5));
    return _mm256_fmaddsub_pd(_mm256_movedup_pd(a), b, cross);
}

static inline __attribute__((target("avx2,fma"), always_inline))
FractionalPairs interpolate_group(const IqSample *iq, const double *weights)
{
    __m256d left[lanes], right[lanes];
    for (int i = 0; i < lanes; ++i) {
        __m256d w = _mm256_broadcast_sd(weights + i);
        left[i] = _mm256_mul_pd(_mm256_loadu_pd((const double *)(iq + i)), w);
        right[i] = _mm256_mul_pd(_mm256_loadu_pd((const double *)(iq + i + 2)), w);
    }
    for (int t = lanes; t < lanczos_taps; t += lanes) {
        for (int i = 0; i < lanes; ++i) {
            int j = t + i;
            __m256d w = _mm256_broadcast_sd(weights + j);
            __m256d a = _mm256_mul_pd(_mm256_loadu_pd((const double *)(iq + j)), w);
            __m256d b = _mm256_mul_pd(_mm256_loadu_pd((const double *)(iq + j + 2)), w);
            left[i] = _mm256_add_pd(left[i], a);
            right[i] = _mm256_add_pd(right[i], b);
        }
    }
    return (FractionalPairs){
        _mm256_add_pd(_mm256_add_pd(left[0], left[1]), _mm256_add_pd(left[2], left[3])),
        _mm256_add_pd(_mm256_add_pd(right[0], right[1]), _mm256_add_pd(right[2], right[3]))
    };
}

static inline __attribute__((target("avx2,fma"), always_inline))
FractionalPairs fractional_samples(const IqSample *iq, const int32_t *starts,
                                  const int32_t *row, const double *weights)
{
    if (starts[1] == starts[0] + 1 && starts[2] == starts[0] + 2 &&
        starts[3] == starts[0] + 3 && row[1] == row[0] && row[2] == row[0] && row[3] == row[0])
        return interpolate_group(iq + starts[0], weights + row[0] * lanczos_taps);
    complex64x2 isolated[lanes];
    for (int i = 0; i < lanes; ++i)
        isolated[i] = interpolate(iq + starts[i], weights + row[i] * lanczos_taps);
    return (FractionalPairs){_mm256_loadu_pd((const double *)isolated),
                             _mm256_loadu_pd((const double *)(isolated + 2))};
}

static inline __attribute__((target("avx2,fma"), always_inline))
FractionalPairs fractional_terms(FractionalPairs signal, const complex64x2 *reference)
{
    __m256d first = _mm256_loadu_pd((const double *)reference);
    __m256d last = _mm256_loadu_pd((const double *)(reference + 2));
    return (FractionalPairs){fractional_product(first, signal.left),
                             fractional_product(last, signal.right)};
}

static inline __attribute__((target("avx2,fma"), always_inline))
FractionalPairs fractional_add(FractionalPairs a, FractionalPairs b)
{
    return (FractionalPairs){_mm256_add_pd(a.left, b.left), _mm256_add_pd(a.right, b.right)};
}

static inline __attribute__((target("avx2,fma"), always_inline))
void finish_fractional(FractionalPairs a, complex64x2 *out)
{
    __m128d first = _mm_add_pd(_mm256_castpd256_pd128(a.left), _mm256_extractf128_pd(a.left, 1));
    __m128d last = _mm_add_pd(_mm256_castpd256_pd128(a.right), _mm256_extractf128_pd(a.right, 1));
    _mm_storeu_pd((double *)out, _mm_add_pd(first, last));
}

__attribute__((target("avx2,fma")))
static void correlate_fractional_packed(
    const IqSample *restrict iq, const int32_t *restrict starts, int frames,
    const int32_t *restrict row, const double *restrict weights,
    const complex64x2 *restrict rotation,
    const complex64x2 *restrict exact, const complex64x2 *restrict control,
    complex64x2 *restrict exact_out, complex64x2 *restrict control_out)
{
    for (int f = 0; f < frames; ++f) {
        for (int s = 0; s < symbols; ++s) {
            int offset = s * taps, index = f * aperture + offset;
            FractionalPairs sample = fractional_samples(iq, starts + index, row + index, weights);
            FractionalPairs corrected = {
                fractional_product(sample.left, _mm256_loadu_pd((const double *)(rotation + index))),
                fractional_product(sample.right, _mm256_loadu_pd((const double *)(rotation + index + 2)))
            };
            FractionalPairs a = fractional_terms(corrected, exact + offset);
            FractionalPairs b = fractional_terms(corrected, control + offset);
            for (int t = lanes; t < taps; t += lanes) {
                int i = index + t;
                sample = fractional_samples(iq, starts + i, row + i, weights);
                corrected = (FractionalPairs){
                    fractional_product(sample.left, _mm256_loadu_pd((const double *)(rotation + i))),
                    fractional_product(sample.right, _mm256_loadu_pd((const double *)(rotation + i + 2)))
                };
                a = fractional_add(a, fractional_terms(corrected, exact + offset + t));
                b = fractional_add(b, fractional_terms(corrected, control + offset + t));
            }
            finish_fractional(a, exact_out + f * symbols + s);
            finish_fractional(b, control_out + f * symbols + s);
        }
    }
}

void correlated_fractional(
    const IqSample *restrict iq, const int32_t *restrict starts, int frames,
    const int32_t *restrict row, const double *restrict weights,
    const complex64x2 *restrict rotation,
    const complex64x2 *restrict exact, const complex64x2 *restrict control,
    complex64x2 *restrict exact_out, complex64x2 *restrict control_out)
{
    if (__builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma")) {
        correlate_fractional_packed(iq, starts, frames, row, weights, rotation, exact,
                                    control, exact_out, control_out);
    } else {
        correlated_fractional_reference(iq, starts, frames, row, weights, rotation, exact,
                                        control, exact_out, control_out);
    }
}
