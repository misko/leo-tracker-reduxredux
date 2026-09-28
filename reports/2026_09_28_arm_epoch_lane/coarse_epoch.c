#include "coarse_epoch.h"
#include <math.h>

#if defined(__ARM_NEON)
#include <arm_neon.h>

static float32x4_t epoch_magnitude(float32x4_t real, float32x4_t imag)
{
    float32x4_t squared = vaddq_f32(vmulq_f32(real, real),
        vmulq_f32(imag, imag));
    float32x4_t safe = vbslq_f32(vceqq_f32(squared, vdupq_n_f32(0)),
        vdupq_n_f32(1), squared);
    float32x4_t reciprocal = vrsqrteq_f32(safe);
    reciprocal = vmulq_f32(reciprocal,
        vrsqrtsq_f32(vmulq_f32(safe, reciprocal), reciprocal));
    reciprocal = vmulq_f32(reciprocal,
        vrsqrtsq_f32(vmulq_f32(safe, reciprocal), reciprocal));
    return vmulq_f32(squared, reciprocal);
}

void leo_coarse_epoch4_add(const float *samples, const float *real,
    const float *imag, int taps, const float inverse_norm[4], float *sum)
{
    float32x4_t inverse = vld1q_f32(inverse_norm);
    for (int f = 0; f < 12; ++f) {
        float32x4_t r = vdupq_n_f32(0), i = r;
        for (int k = 0; k < taps; ++k) {
            float32x4x2_t x = vld2q_f32(samples + 2*k);
            float32x4_t rr = vdupq_n_f32(real[12*k+f]);
            float32x4_t ri = vdupq_n_f32(imag[12*k+f]);
            r = vaddq_f32(r, vaddq_f32(vmulq_f32(x.val[0], rr),
                vmulq_f32(x.val[1], ri)));
            i = vaddq_f32(i, vsubq_f32(vmulq_f32(x.val[1], rr),
                vmulq_f32(x.val[0], ri)));
        }
        float32x4_t value = vmulq_f32(epoch_magnitude(r, i), inverse);
        sum[f] += vgetq_lane_f32(value, 0);
        sum[12+f] += vgetq_lane_f32(value, 1);
        sum[24+f] += vgetq_lane_f32(value, 2);
        sum[36+f] += vgetq_lane_f32(value, 3);
    }
}
#else
void leo_coarse_epoch4_add(const float *samples, const float *real,
    const float *imag, int taps, const float inverse_norm[4], float *sum)
{
    for (int f = 0; f < 12; ++f) {
        float r[4] = {0}, i[4] = {0};
        for (int k = 0; k < taps; ++k)
            for (int epoch = 0; epoch < 4; ++epoch) {
                float xr = samples[2*(k+epoch)], xi = samples[2*(k+epoch)+1];
                r[epoch] += xr*real[12*k+f] + xi*imag[12*k+f];
                i[epoch] += xi*real[12*k+f] - xr*imag[12*k+f];
            }
        for (int epoch = 0; epoch < 4; ++epoch)
            sum[12*epoch+f] += sqrtf(r[epoch]*r[epoch]+i[epoch]*i[epoch]) *
                inverse_norm[epoch];
    }
}
#endif
