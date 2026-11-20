/* Shared sliding rectangular tone apertures for capture-era Qin anchors. */
#include <immintrin.h>
#include <math.h>
#include <stdint.h>

#include "pilot_kernel.c"

enum { tones = 8, block_size = 128, max_taps = 44, basis_tile = 2048 };

static void sliding_tones(
    const float *real, const float *imag, int valid, int aperture,
    const double *weights, const double *inverse_phase, float *basis)
{
    int span = block_size + aperture - 1;
    for (int tone = 0; tone < tones; ++tone) {
        const double *wr = weights + 2 * span * tone, *wi = wr + span;
        const double *qr = inverse_phase + 2 * block_size * tone, *qi = qr + block_size;
        float *out_real = basis + 2 * tone * valid;
        float *out_imag = out_real + valid;
        for (int block = 0; block < valid; block += block_size) {
            int count = valid - block < block_size ? valid - block : block_size;
            int used = count + aperture - 1;
            double pr[block_size + max_taps], pi[block_size + max_taps];
            pr[0] = 0;
            pi[0] = 0;
            int i = 0;
            for (; i <= used - 4; i += 4) {
                __m256d xr = _mm256_cvtps_pd(_mm_loadu_ps(real + block + i));
                __m256d xi = _mm256_cvtps_pd(_mm_loadu_ps(imag + block + i));
                __m256d cr = _mm256_loadu_pd(wr + i), ci = _mm256_loadu_pd(wi + i);
                _mm256_storeu_pd(pr + i + 1, _mm256_fmsub_pd(xr, cr, _mm256_mul_pd(xi, ci)));
                _mm256_storeu_pd(pi + i + 1, _mm256_fmadd_pd(xr, ci, _mm256_mul_pd(xi, cr)));
            }
            for (; i < used; ++i) {
                double xr = real[block + i], xi = imag[block + i];
                pr[i + 1] = xr * wr[i] - xi * wi[i];
                pi[i + 1] = xr * wi[i] + xi * wr[i];
            }
            for (i = 0; i < used; ++i) {
                pr[i + 1] += pr[i];
                pi[i + 1] += pi[i];
            }
            for (i = 0; i <= count - 4; i += 4) {
                __m256d ar = _mm256_sub_pd(_mm256_loadu_pd(pr + i + aperture),
                                          _mm256_loadu_pd(pr + i));
                __m256d ai = _mm256_sub_pd(_mm256_loadu_pd(pi + i + aperture),
                                          _mm256_loadu_pd(pi + i));
                __m256d cr = _mm256_loadu_pd(qr + i), ci = _mm256_loadu_pd(qi + i);
                __m256d re = _mm256_fmsub_pd(ar, cr, _mm256_mul_pd(ai, ci));
                __m256d im = _mm256_fmadd_pd(ar, ci, _mm256_mul_pd(ai, cr));
                _mm_storeu_ps(out_real + block + i, _mm256_cvtpd_ps(re));
                _mm_storeu_ps(out_imag + block + i, _mm256_cvtpd_ps(im));
            }
            for (; i < count; ++i) {
                double ar = pr[i + aperture] - pr[i], ai = pi[i + aperture] - pi[i];
                out_real[block + i] = (float) (ar * qr[i] - ai * qi[i]);
                out_imag[block + i] = (float) (ar * qi[i] + ai * qr[i]);
            }
        }
    }
}

static int support_at(int valid, int origin, int epochs)
{
    int support = valid - origin;
    return support < epochs ? support : epochs;
}

static void fold_spectral_tile(
    const float *real, const float *imag, int valid, int aperture, const double *weights,
    const double *inverse_phase, const int32_t *anchors, int anchor_count,
    const uint8_t *states, const float *boundary, const float *inverse_template_norm,
    const int32_t *frames, int frame_count, const float *inverse_iq_norm,
    int epochs, int first, int length, float *basis, double *scores)
{
    sliding_tones(real + first, imag + first, length, aperture, weights, inverse_phase, basis);
    int last = first + length;
    for (int anchor = 0; anchor < anchor_count; ++anchor) {
        const float *mix_real[tones], *mix_imag[tones];
        __m256 sign_real[tones], sign_imag[tones];
        for (int tone = 0; tone < tones; ++tone) {
            /* Multiplication by i^-state is one exchange and two sign bits. */
            unsigned state = states[anchor * tones + tone];
            mix_real[tone] = basis + (2 * tone + (state & 1)) * length;
            mix_imag[tone] = basis + (2 * tone + 1 - (state & 1)) * length;
            sign_real[tone] = _mm256_set1_ps(state >= 2 ? -0.0f : 0.0f);
            sign_imag[tone] = _mm256_set1_ps(state == 1 || state == 2 ? -0.0f : 0.0f);
        }
        float cr = boundary[2 * anchor], ci = boundary[2 * anchor + 1];
        __m256 br = _mm256_set1_ps(cr), bi = _mm256_set1_ps(ci);
        __m256 norm = _mm256_set1_ps(inverse_template_norm[anchor]);
        for (int frame = 0; frame < frame_count; ++frame) {
            int origin = frames[frame] + anchors[anchor];
            int n = support_at(valid, origin, epochs);
            if (origin >= last) break;
            if (origin + n <= first) continue;
            int epoch = first > origin ? first - origin : 0;
            n = last - origin < n ? last - origin : n;
            for (; epoch <= n - 8; epoch += 8) {
                int pos = origin + epoch;
                __m256 xr = _mm256_loadu_ps(real + pos), xi = _mm256_loadu_ps(imag + pos);
                __m256 rr = _mm256_sub_ps(_mm256_mul_ps(xr, br), _mm256_mul_ps(xi, bi));
                __m256 ri = _mm256_add_ps(_mm256_mul_ps(xr, bi), _mm256_mul_ps(xi, br));
                #pragma GCC unroll 8
                for (int tone = 0; tone < tones; ++tone) {
                    __m256 ar = _mm256_loadu_ps(mix_real[tone] + pos - first);
                    __m256 ai = _mm256_loadu_ps(mix_imag[tone] + pos - first);
                    rr = _mm256_add_ps(rr, _mm256_xor_ps(ar, sign_real[tone]));
                    ri = _mm256_add_ps(ri, _mm256_xor_ps(ai, sign_imag[tone]));
                }
                __m256 squared = _mm256_add_ps(_mm256_mul_ps(rr, rr), _mm256_mul_ps(ri, ri));
                __m256 scale = _mm256_mul_ps(norm, _mm256_loadu_ps(inverse_iq_norm + pos));
                __m256 folded = _mm256_mul_ps(_mm256_sqrt_ps(squared), scale);
                __m256d low = _mm256_cvtps_pd(_mm256_castps256_ps128(folded));
                __m256d high = _mm256_cvtps_pd(_mm256_extractf128_ps(folded, 1));
                _mm256_storeu_pd(scores + epoch, _mm256_add_pd(_mm256_loadu_pd(scores + epoch), low));
                _mm256_storeu_pd(scores + epoch + 4,
                                 _mm256_add_pd(_mm256_loadu_pd(scores + epoch + 4), high));
            }
            for (; epoch < n; ++epoch) {
                int pos = origin + epoch;
                float xr = real[pos], xi = imag[pos];
                float rr = xr * cr - xi * ci, ri = xr * ci + xi * cr;
                for (int tone = 0; tone < tones; ++tone) {
                    unsigned state = states[anchor * tones + tone];
                    float r = mix_real[tone][pos - first], i = mix_imag[tone][pos - first];
                    rr += state >= 2 ? -r : r;
                    ri += state == 1 || state == 2 ? -i : i;
                }
                scores[epoch] += sqrtf(rr*rr + ri*ri) * inverse_template_norm[anchor]
                    * inverse_iq_norm[pos];
            }
        }
    }
}

void score_spectral_row(
    const float *real, const float *imag, int valid, int aperture, const double *weights,
    const double *inverse_phase, const int32_t *anchors, int anchor_count,
    const uint8_t *states, const float *boundary, const float *inverse_template_norm,
    const int32_t *frames, int frame_count, const float *inverse_iq_norm,
    int epochs, float *basis, double *scores)
{
    for (int first = 0; first < valid; first += basis_tile) {
        int length = valid - first < basis_tile ? valid - first : basis_tile;
        fold_spectral_tile(real, imag, valid, aperture, weights, inverse_phase, anchors,
                           anchor_count, states, boundary, inverse_template_norm, frames,
                           frame_count, inverse_iq_norm, epochs, first, length, basis, scores);
    }
}

/* Repair using the exact same lanes, tile origins, tail and reduction as pilot_kernel.c. */
void repair_spectral_row(
    const float *real, const float *imag, int valid, int aperture, const float *coeff_real,
    const float *coeff_imag, const int32_t *anchors, int anchor_count,
    const int32_t *frames, int frame_count, const float *inverse_iq_norm,
    int epochs, const int32_t *tile_starts, int tile_count, double *scores)
{
    for (int anchor = 0; anchor < anchor_count; ++anchor) {
        const float *cr = coeff_real + aperture * anchor;
        const float *ci = coeff_imag + aperture * anchor;
        for (int t = 0; t < tile_count; ++t) {
            int e = tile_starts[t];
            int count = epochs - e < tile ? epochs - e : tile;
            int32_t support[tile] = {0};
            fold_filter_bank(real, imag, valid + aperture - 1, cr, ci, 1, aperture,
                             anchors[anchor] + e, frames, frame_count, inverse_iq_norm,
                             count, scores + e, support);
        }
    }
}
