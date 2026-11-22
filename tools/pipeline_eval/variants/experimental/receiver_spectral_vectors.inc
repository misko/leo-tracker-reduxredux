/* Keep the two scout modes and FFT plans while packing their surrounding arithmetic. */
#include <immintrin.h>

__attribute__((target("avx2")))
static inline __m256 spectral_samples(const Sample *samples) {
    return _mm256_loadu_ps((const float *)samples);
}

__attribute__((target("avx2")))
static inline __m256 spectral_conjugate(__m256 values) {
    const __m256 sign = _mm256_setr_ps(0.f, -0.f, 0.f, -0.f, 0.f, -0.f, 0.f, -0.f);
    return _mm256_xor_ps(values, sign);
}

__attribute__((target("avx2")))
static inline __m256 spectral_product(__m256 a, __m256 b) {
    __m256 ar = _mm256_moveldup_ps(a), ai = _mm256_movehdup_ps(a);
    __m256 swapped = _mm256_permute_ps(b, _MM_SHUFFLE(2, 3, 0, 1));
    return _mm256_addsub_ps(_mm256_mul_ps(ar, b), _mm256_mul_ps(ai, swapped));
}

__attribute__((target("avx2")))
static inline __m128 spectral_power(__m256 values) {
    __m256 squares = _mm256_mul_ps(values, values);
    __m256 powers = _mm256_hadd_ps(squares, squares);
    return _mm_movelh_ps(_mm256_castps256_ps128(powers), _mm256_extractf128_ps(powers, 1));
}

__attribute__((target("avx2")))
static void spectral_lag_products(Sample *out, double *prefix, const Sample *a, const Sample *b,
                                  int width, int lag, int fft_size) {
    const int size = width - lag;
    prefix[0] = 0.;
    int i = 0;
    for (; i + 3 < size; i += 4) {
        __m256 aa = spectral_product(spectral_samples(a + i + lag),
                                     spectral_conjugate(spectral_samples(a + i)));
        __m256 bb = spectral_product(spectral_samples(b + i + lag),
                                     spectral_conjugate(spectral_samples(b + i)));
        __m256 both = _mm256_add_ps(aa, bb);
        _mm256_storeu_ps((float *)(out + i), both);
        float energies[4];
        _mm_storeu_ps(energies, spectral_power(both));
        for (int k = 0; k < 4; ++k)
            prefix[i + k + 1] = prefix[i + k] + energies[k];
    }
    for (; i < size; ++i) {
        Sample aa = multiply(a[i + lag], conjugate(a[i]));
        Sample bb = multiply(b[i + lag], conjugate(b[i]));
        out[i] = (Sample){aa.re + bb.re, aa.im + bb.im};
        prefix[i + 1] = prefix[i] + power(out[i]);
    }
    memset(out + size, 0, (fft_size - size) * sizeof(*out));
}

__attribute__((target("avx2")))
static void spectral_filter(Sample *out, const Sample *filter, int size) {
    int i = 0;
    for (; i + 3 < size; i += 4) {
        __m256 v = spectral_product(spectral_samples(out + i), spectral_samples(filter + i));
        _mm256_storeu_ps((float *)(out + i), v);
    }
    for (; i < size; ++i)
        out[i] = multiply(out[i], filter[i]);
}

__attribute__((target("avx2")))
static void spectral_timing_scores(double *scores, const double *prefix, const Sample *inverse,
                                  int epochs, int length, int fft_size) {
    const float scale = 1.f / fft_size;
    const __m256 scale_vec = _mm256_set1_ps(scale);
    const __m256d floor = _mm256_set1_pd(1e-20);
    int i = 0;
    for (; i + 3 < epochs; i += 4) {
        __m256 scaled = _mm256_mul_ps(spectral_samples(inverse + i), scale_vec);
        __m256d numerator = _mm256_cvtps_pd(spectral_power(scaled));
        __m256d energy = _mm256_sub_pd(_mm256_loadu_pd(prefix + i + length), _mm256_loadu_pd(prefix + i));
        __m256d added = _mm256_div_pd(numerator, _mm256_max_pd(energy, floor));
        _mm256_storeu_pd(scores + i, _mm256_add_pd(_mm256_loadu_pd(scores + i), added));
    }
    for (; i < epochs; ++i) {
        Sample scaled = {inverse[i].re * scale, inverse[i].im * scale};
        scores[i] += power(scaled) / fmax(prefix[i + length] - prefix[i], 1e-20);
    }
}

__attribute__((target("avx2")))
static double spectral_carrier_input(Sample *out, const Sample *mode, const Sample *code,
                                     int length, int fft_size, double energy) {
    int i = 0;
    for (; i + 3 < length; i += 4) {
        __m256 v = spectral_samples(mode + i);
        __m256 result = spectral_product(v, spectral_conjugate(spectral_samples(code + i)));
        _mm256_storeu_ps((float *)(out + i), result);
        float energies[4];
        _mm_storeu_ps(energies, spectral_power(v));
        for (int k = 0; k < 4; ++k)
            energy += energies[k];
    }
    for (; i < length; ++i) {
        out[i] = multiply(mode[i], conjugate(code[i]));
        energy += power(mode[i]);
    }
    memset(out + length, 0, (fft_size - length) * sizeof(*out));
    return energy;
}

__attribute__((target("avx2")))
static void spectral_carrier_power(double *powers, const Sample *fft, int size) {
    int i = 0;
    for (; i + 3 < size; i += 4) {
        __m256d added = _mm256_cvtps_pd(spectral_power(spectral_samples(fft + i)));
        _mm256_storeu_pd(powers + i, _mm256_add_pd(_mm256_loadu_pd(powers + i), added));
    }
    for (; i < size; ++i)
        powers[i] += power(fft[i]);
}
