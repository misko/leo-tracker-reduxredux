/* One complex lane per symbol. Keep all 44 additions in their original
   order, including the first addition to positive zero. */
#if defined(__x86_64__) && defined(__GNUC__)
#include <immintrin.h>
_Static_assert(symbol == 44, "The scout's SIMD transpose covers eleven groups of four taps");

__attribute__((target("avx2")))
static inline __m256d scout_symbol_terms(const Sample *data, const Sample *pilot)
{
    __m256 signal = _mm256_loadu_ps((const float *)data);
    __m256 phase = _mm256_loadu_ps((const float *)pilot);
    __m256 first = _mm256_mul_ps(_mm256_moveldup_ps(signal), phase);
    __m256 second = _mm256_mul_ps(_mm256_movehdup_ps(signal), _mm256_permute_ps(phase, 0xb1));
    return _mm256_castps_pd(_mm256_addsub_ps(first, second));
}

__attribute__((target("avx2")))
static void scout_gate_symbols_avx2(const Sample *data, const Sample *pilot, Sample *out)
{
    for (int s = 0; s < 64; s += 4) {
        __m256 sum = _mm256_setzero_ps();
        for (int k = 0; k < symbol; k += 4) {
            int j = s * symbol + k;
            __m256d a = scout_symbol_terms(data + j, pilot + j);
            __m256d b = scout_symbol_terms(data + j + symbol, pilot + j + symbol);
            __m256d c = scout_symbol_terms(data + j + 2*symbol, pilot + j + 2*symbol);
            __m256d d = scout_symbol_terms(data + j + 3*symbol, pilot + j + 3*symbol);
            __m256d ab_even = _mm256_unpacklo_pd(a, b);
            __m256d cd_even = _mm256_unpacklo_pd(c, d);
            __m256d ab_odd = _mm256_unpackhi_pd(a, b);
            __m256d cd_odd = _mm256_unpackhi_pd(c, d);
            sum = _mm256_add_ps(sum, _mm256_castpd_ps(_mm256_permute2f128_pd(ab_even, cd_even, 0x20)));
            sum = _mm256_add_ps(sum, _mm256_castpd_ps(_mm256_permute2f128_pd(ab_odd, cd_odd, 0x20)));
            sum = _mm256_add_ps(sum, _mm256_castpd_ps(_mm256_permute2f128_pd(ab_even, cd_even, 0x31)));
            sum = _mm256_add_ps(sum, _mm256_castpd_ps(_mm256_permute2f128_pd(ab_odd, cd_odd, 0x31)));
        }
        _mm256_storeu_ps((float *)(out + s), sum);
    }
}
#endif

static _Thread_local int scout_gate_symbols_vector;

int scout_gate_symbols_mode(int vector)
{
#if defined(__x86_64__) && defined(__GNUC__)
    scout_gate_symbols_vector = vector && __builtin_cpu_supports("avx2");
#else
    (void)vector;
    scout_gate_symbols_vector = 0;
#endif
    return scout_gate_symbols_vector;
}

static int scout_gate_symbols_try(const Sample *data, const Sample *pilot, Sample *out)
{
#if defined(__x86_64__) && defined(__GNUC__)
    if (scout_gate_symbols_vector) {
        scout_gate_symbols_avx2(data, pilot, out);
        return 1;
    }
#else
    (void)data;
    (void)pilot;
    (void)out;
#endif
    return 0;
}
