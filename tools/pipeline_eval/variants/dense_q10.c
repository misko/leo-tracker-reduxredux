/* Evaluate every epoch using an integer prefix in the 32-bit modular ring. */
#include "spectral_grid.c"

static inline __m256i prefix_eight(__m256i value, __m256i carry)
{
    value = _mm256_add_epi32(value, _mm256_slli_si256(value, 4));
    value = _mm256_add_epi32(value, _mm256_slli_si256(value, 8));
    __m256i midpoint = _mm256_permutevar8x32_epi32(value, _mm256_set1_epi32(3));
    midpoint = _mm256_blend_epi32(_mm256_setzero_si256(), midpoint, 0xf0);
    return _mm256_add_epi32(value, _mm256_add_epi32(midpoint, carry));
}

static float window_sum(const uint32_t *prefix, int at, int aperture)
{
    uint32_t bits = prefix[at + aperture] - prefix[at];
    int32_t value;
    memcpy(&value, &bits, sizeof(value));
    return (float)value;
}

static void quantized_tones(
    const float *real, const float *imag, int valid, int aperture,
    const float *weights, const float *inverse_phase, float *basis)
{
    int span = block_size + aperture - 1;
    for (int tone = 0; tone < tones; ++tone) {
        const float *wr = weights + 2 * span * tone, *wi = wr + span;
        const float *qr = inverse_phase + 2 * block_size * tone, *qi = qr + block_size;
        float *out_real = basis + 2 * tone * valid, *out_imag = out_real + valid;
        for (int block = 0; block < valid; block += block_size) {
            int count = valid - block < block_size ? valid - block : block_size;
            int used = count + aperture - 1;
            uint32_t pr[block_size + max_taps], pi[block_size + max_taps];
            pr[0] = 0;
            pi[0] = 0;
            __m256i sr = _mm256_setzero_si256(), si = sr;
            __m256i last = _mm256_set1_epi32(7);
            int i = 0;
            for (; i <= used - 8; i += 8) {
                __m256 xr = _mm256_loadu_ps(real + block + i), xi = _mm256_loadu_ps(imag + block + i);
                __m256 cr = _mm256_loadu_ps(wr + i), ci = _mm256_loadu_ps(wi + i);
                __m256 r = _mm256_fmsub_ps(xr, cr, _mm256_mul_ps(xi, ci));
                __m256 j = _mm256_fmadd_ps(xr, ci, _mm256_mul_ps(xi, cr));
                sr = prefix_eight(_mm256_cvtps_epi32(r), sr);
                si = prefix_eight(_mm256_cvtps_epi32(j), si);
                _mm256_storeu_si256((__m256i *)(pr + i + 1), sr);
                _mm256_storeu_si256((__m256i *)(pi + i + 1), si);
                sr = _mm256_permutevar8x32_epi32(sr, last);
                si = _mm256_permutevar8x32_epi32(si, last);
            }
            for (; i < used; ++i) {
                float xr = real[block + i], xi = imag[block + i];
                pr[i + 1] = pr[i] + (uint32_t)lrintf(xr * wr[i] - xi * wi[i]);
                pi[i + 1] = pi[i] + (uint32_t)lrintf(xr * wi[i] + xi * wr[i]);
            }
            for (i = 0; i <= count - 8; i += 8) {
                __m256 ar = _mm256_cvtepi32_ps(_mm256_sub_epi32(
                    _mm256_loadu_si256((const __m256i *)(pr + i + aperture)),
                    _mm256_loadu_si256((const __m256i *)(pr + i))));
                __m256 ai = _mm256_cvtepi32_ps(_mm256_sub_epi32(
                    _mm256_loadu_si256((const __m256i *)(pi + i + aperture)),
                    _mm256_loadu_si256((const __m256i *)(pi + i))));
                __m256 cr = _mm256_loadu_ps(qr + i), ci = _mm256_loadu_ps(qi + i);
                _mm256_storeu_ps(out_real + block + i, _mm256_fmsub_ps(ar, cr, _mm256_mul_ps(ai, ci)));
                _mm256_storeu_ps(out_imag + block + i, _mm256_fmadd_ps(ar, ci, _mm256_mul_ps(ai, cr)));
            }
            for (; i < count; ++i) {
                float ar = window_sum(pr, i, aperture), ai = window_sum(pi, i, aperture);
                out_real[block + i] = ar * qr[i] - ai * qi[i];
                out_imag[block + i] = ar * qi[i] + ai * qr[i];
            }
        }
    }
}

static void fold_quantized_tile(
    const float *real, const float *imag, int valid, const int32_t *anchors, int anchor_count,
    const uint8_t *states, const float *boundary, const float *inverse_template_norm,
    const int32_t *frames, int frame_count, const float *inverse_iq_norm,
    int epochs, int first, int length, const float *basis, double *scores)
{
    int last = first + length;
    for (int anchor = 0; anchor < anchor_count; ++anchor) {
        const float *mix_real[tones], *mix_imag[tones];
        __m256 sign_real[tones], sign_imag[tones];
        for (int tone = 0; tone < tones; ++tone) {
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
                scores[epoch] += sqrtf(rr * rr + ri * ri) * inverse_template_norm[anchor]
                    * inverse_iq_norm[pos];
            }
        }
    }
}

void score_dense_q10(
    const float *real, const float *imag, int valid, int aperture, const float *weights,
    const float *inverse_phase, const int32_t *anchors, int anchor_count,
    const uint8_t *states, const float *boundary, const float *inverse_template_norm,
    const int32_t *frames, int frame_count, const float *inverse_iq_norm,
    int epochs, float *basis, double *scores)
{
    for (int first = 0; first < valid; first += basis_tile) {
        int length = valid - first < basis_tile ? valid - first : basis_tile;
        quantized_tones(real + first, imag + first, length, aperture, weights, inverse_phase, basis);
        fold_quantized_tile(real, imag, valid, anchors, anchor_count, states, boundary,
                            inverse_template_norm, frames, frame_count, inverse_iq_norm,
                            epochs, first, length, basis, scores);
    }
}
