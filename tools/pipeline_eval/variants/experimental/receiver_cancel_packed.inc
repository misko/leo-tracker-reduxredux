/* Included after the reference cancellation constants and quantizer. */
#include <immintrin.h>
#include <fenv.h>

static int phase_start(int phase) {
    return phase == 0 ? 0 : phase * (thirds / 3) + 1;
}

/* Advancing one input sample advances three synthesis ticks. Arrange the
   three possible tick phases contiguously without changing the recurrence. */
static void rotate_phases(const float *pilot, float *scratch, double carrier_hz) {
    const double d = 6.28318530717958647693 * carrier_hz / 3e7;
    const double dr = cos(d), di = sin(d);
    double ar = 1., ai = 0.;
    for (int j = 0; j < thirds; ++j) {
        double pr = pilot[2 * j], pi = pilot[2 * j + 1];
        int k = 2 * (phase_start(j % 3) + j / 3);
        scratch[k] = (float)(pr * ar - pi * ai);
        scratch[k + 1] = (float)(pi * ar + pr * ai);
        double next = ar * dr - ai * di;
        ai = ar * di + ai * dr;
        ar = next;
    }
}

__attribute__((target("avx2")))
static void subtract_packed(float *iq, const float *wave, int count, double re, double im) {
    const __m256d gain_re = _mm256_set1_pd(re), gain_im = _mm256_set1_pd(im);
    const __m256d low = _mm256_set1_pd(-32768.), high = _mm256_set1_pd(32767.);
    int i = 0;
    for (; i + 3 < 2 * count; i += 4) {
        __m256d h = _mm256_cvtps_pd(_mm_loadu_ps(wave + i));
        __m256d cross = _mm256_permute_pd(h, 5);
        __m256d correction = _mm256_addsub_pd(_mm256_mul_pd(h, gain_re), _mm256_mul_pd(cross, gain_im));
        __m256d value = _mm256_sub_pd(_mm256_cvtps_pd(_mm_loadu_ps(iq + i)), correction);
        /* The lower bound is the second operand so an unordered value maps
           to the same endpoint as the scalar quantizer. */
        value = _mm256_min_pd(_mm256_max_pd(value, low), high);
        _mm_storeu_ps(iq + i, _mm_cvtepi32_ps(_mm256_cvtpd_epi32(value)));
    }
    for (; i < 2 * count; i += 2) {
        double hr = wave[i], hi = wave[i + 1];
        iq[i] = quantize(iq[i] - (re * hr - im * hi));
        iq[i + 1] = quantize(iq[i + 1] - (im * hr + re * hi));
    }
}

static int cancel_packed(float *iq, const float *pilot, float *scratch, double epoch, double carrier_hz) {
    rotate_phases(pilot, scratch, carrier_hz);
    enum { blocks = (end_symbol - first_symbol + 63) / 64 };
    double full_norm[3][blocks];
    unsigned norm_cached[3] = {0};
    for (int t = (int)lrint(3. * epoch) - thirds; t < 3 * samples; t += thirds) {
        for (int block = first_symbol; block < end_symbol; block += 64) {
            int start = first_sample(t + symbol * block);
            int end = first_sample(t + symbol * (block + 64 < end_symbol ? block + 64 : end_symbol));
            if (end <= start) continue;
            int tick = 3 * start - t;
            int phase = tick % 3;
            const float *wave = scratch + 2 * (phase_start(phase) + tick / 3);
            float *lane = iq + 2 * start;
            const int span = 2 * (end - start);
            const int number = (block - first_symbol) / 64;
            const unsigned bit = 1u << number;
            const int complete = start > 0 && end < samples;
            double norm = 0.;
            if (complete && (norm_cached[phase] & bit)) {
                norm = full_norm[phase][number];
            } else {
                for (int i = 0; i < span; i += 2) {
                    double hr = wave[i], hi = wave[i + 1];
                    norm += hr * hr + hi * hi;
                }
                if (complete) {
                    full_norm[phase][number] = norm;
                    norm_cached[phase] |= bit;
                }
            }
            if (norm == 0.) continue;
            double re = 0., im = 0.;
            for (int i = 0; i < span; i += 2) {
                double hr = wave[i], hi = wave[i + 1];
                re += hr * lane[i] + hi * lane[i + 1];
                im += hr * lane[i + 1] - hi * lane[i];
            }
            subtract_packed(lane, wave, end - start, re / norm, im / norm);
        }
    }
    return 0;
}
