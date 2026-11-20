/* Stock integer-VNNI statistic, sharing each tap load across two epochs. */
#include <immintrin.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

static inline void correlate_pair(const uint32_t *iq, const int32_t *qr,
                                  const int32_t *qi, size_t taps, size_t blocks,
                                  int32_t out_r[2][24], int32_t out_i[2][24]) {
    __m256i r0[3], r1[3], i0[3], i1[3];
    for (size_t g = 0; g < blocks; ++g) {
        r0[g] = r1[g] = i0[g] = i1[g] = _mm256_setzero_si256();
    }
    for (size_t n = 0; n < taps; ++n) {
        const __m256i x0 = _mm256_set1_epi32((int32_t)iq[n]);
        const __m256i x1 = _mm256_set1_epi32((int32_t)iq[n + 1]);
        for (size_t g = 0; g < blocks; ++g) {
            const size_t offset = n * 8 * blocks + 8 * g;
            const __m256i real = _mm256_loadu_si256((const __m256i *)(qr + offset));
            r0[g] = _mm256_dpwssd_avx_epi32(r0[g], x0, real);
            r1[g] = _mm256_dpwssd_avx_epi32(r1[g], x1, real);
            const __m256i imag = _mm256_loadu_si256((const __m256i *)(qi + offset));
            i0[g] = _mm256_dpwssd_avx_epi32(i0[g], x0, imag);
            i1[g] = _mm256_dpwssd_avx_epi32(i1[g], x1, imag);
        }
    }
    for (size_t g = 0; g < blocks; ++g) {
        _mm256_storeu_si256((__m256i *)(out_r[0] + 8 * g), r0[g]);
        _mm256_storeu_si256((__m256i *)(out_r[1] + 8 * g), r1[g]);
        _mm256_storeu_si256((__m256i *)(out_i[0] + 8 * g), i0[g]);
        _mm256_storeu_si256((__m256i *)(out_i[1] + 8 * g), i1[g]);
    }
}

static inline uint32_t packed_words(int16_t real, int16_t imag) {
    return (uint32_t)(uint16_t)real | ((uint32_t)(uint16_t)imag << 16);
}

int screened_detector_grid(const double *input, size_t samples, const double *reference,
                           size_t template_size, const double *frequencies, size_t channels,
                           const ptrdiff_t *starts, const ptrdiff_t *stops, size_t symbols,
                           const ptrdiff_t *offsets, size_t frames, const double *prefix,
                           double rate, size_t epochs, double *output) {
    if (!samples || samples > 200000 || !epochs || epochs > 13334 || !symbols ||
        symbols > 22 || !channels || channels > 24 || !frames || frames > 16 || rate != 10000000) {
        return 1;
    }
    const size_t blocks = (channels + 7) / 8;
    const size_t width = 8 * blocks;
    double rmax = 0.0, xmax = 0.0;
    size_t max_taps = 0;
    for (size_t s = 0; s < symbols; ++s) {
        if (starts[s] < 0 || stops[s] <= starts[s] || (size_t)stops[s] > template_size) {
            return 1;
        }
        const size_t taps = (size_t)(stops[s] - starts[s]);
        if (taps > max_taps) max_taps = taps;
        for (ptrdiff_t n = starts[s]; n < stops[s]; ++n) {
            rmax = fmax(rmax, fabs(reference[2 * n]));
            rmax = fmax(rmax, fabs(reference[2 * n + 1]));
        }
    }
    for (size_t n = 0; n < 2 * samples; ++n) {
        const double x = input[n];
        if (!isfinite(x) || fabs(x) > 32767 || x != nearbyint(x)) return 1;
        xmax = fmax(xmax, fabs(x));
    }
    if (!isfinite(rmax) || rmax == 0.0 || xmax == 0.0 || max_taps > 512 || max_taps >= samples) {
        return 1;
    }
    const double scale = (fmin(32767.0, floor(2147483647.0 / (2.0 * max_taps * xmax))) - 1.0)
                         / (2.0 * rmax);
    if (!(scale > 0.0) || !isfinite(scale)) return 1;
    uint32_t *iq = malloc((samples + 1) * sizeof(*iq));
    int32_t *qr = calloc(max_taps * width, sizeof(*qr));
    int32_t *qi = calloc(max_taps * width, sizeof(*qi));
    double *sum = calloc(epochs * width, sizeof(*sum));
    unsigned int *support = calloc(epochs, sizeof(*support));
    int status = 1;
    if (!iq || !qr || !qi || !sum || !support) goto finish;
    for (size_t n = 0; n < samples; ++n) {
        iq[n] = packed_words((int16_t)input[2 * n], (int16_t)input[2 * n + 1]);
    }
    iq[samples] = 0;
    for (size_t s = 0; s < symbols; ++s) {
        const size_t taps = (size_t)(stops[s] - starts[s]);
        double ref_power = 0.0;
        for (size_t n = 0; n < taps; ++n) {
            const size_t i = (size_t)starts[s] + n;
            const double re = reference[2 * i], im = reference[2 * i + 1];
            ref_power += re * re + im * im;
            for (size_t channel = 0; channel < channels; ++channel) {
                const double angle = 6.283185307179586476925286766559 * frequencies[channel] * n / rate;
                const double c = cos(angle), si = sin(angle);
                const int16_t p = (int16_t)nearbyint((re * c - im * si) * scale);
                const int16_t q = (int16_t)nearbyint((re * si + im * c) * scale);
                qr[n * width + channel] = (int32_t)packed_words(p, q);
                qi[n * width + channel] = (int32_t)packed_words(-q, p);
            }
        }
        for (size_t frame = 0; frame < frames; ++frame) {
            if (offsets[frame] < 0 || (size_t)offsets[frame] >= samples) goto finish;
            const size_t base = (size_t)starts[s] + (size_t)offsets[frame];
            if (base + taps > samples) break;
            const size_t valid = samples + 1 - base - taps;
            const size_t end = valid < epochs ? valid : epochs;
            for (size_t e = 0; e < end; e += 2) {
                int32_t r[2][24], i[2][24];
                const uint32_t *here = iq + base + e;
                if (blocks == 1) correlate_pair(here, qr, qi, taps, 1, r, i);
                else if (blocks == 2) correlate_pair(here, qr, qi, taps, 2, r, i);
                else correlate_pair(here, qr, qi, taps, 3, r, i);
                for (size_t j = 0; j < 2 && e + j < end; ++j) {
                    const size_t p = base + e + j;
                    const double energy = prefix[p + taps] - prefix[p];
                    const double denominator = sqrt(ref_power * fmax(0.0, energy));
                    if (denominator > 0.0) {
                        for (size_t c = 0; c < channels; ++c) {
                            const double real = r[j][c] / scale;
                            const double imag = i[j][c] / scale;
                            sum[(e + j) * width + c] += sqrt(real * real + imag * imag) / denominator;
                        }
                    }
                    ++support[e + j];
                }
            }
        }
    }
    for (size_t c = 0; c < channels; ++c) {
        for (size_t e = 0; e < epochs; ++e) {
            output[c * epochs + e] = support[e] ? sum[e * width + c] / support[e] : 0.0;
        }
    }
    status = 0;
finish:
    free(iq);
    free(qr);
    free(qi);
    free(sum);
    free(support);
    return status;
}
