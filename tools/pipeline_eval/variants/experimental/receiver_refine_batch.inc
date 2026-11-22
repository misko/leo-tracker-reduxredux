/* The first four blocks use four ordered sums per offset. Later blocks
   accumulate serially. AVX2 lanes are distinct offsets at the same tap. */

#include <string.h>

static inline __attribute__((target("avx2"), always_inline))
void refine_eight(const float *iq, const RefineRotation *const *p, int count,
                  int begin, int chains, BlockMatrix *matrix, int frame, int b)
{
    __m256 re[2] = {_mm256_setzero_ps(), _mm256_setzero_ps()};
    __m256 im[2] = {_mm256_setzero_ps(), _mm256_setzero_ps()};
    __m256 power = _mm256_setzero_ps();
    for (int c = 0; c < chains; ++c) {
        __m256 a[2] = {_mm256_setzero_ps(), _mm256_setzero_ps()};
        __m256 d[2] = {_mm256_setzero_ps(), _mm256_setzero_ps()};
        __m256 energy = _mm256_setzero_ps();
        for (int j = begin + c; j < begin + block; j += chains) {
            __m256 first = _mm256_loadu_ps(iq + 2*j);
            __m256 last = _mm256_loadu_ps(iq + 2*j + 8);
            __m256 xr = _mm256_shuffle_ps(first, last, _MM_SHUFFLE(2, 0, 2, 0));
            __m256 xi = _mm256_shuffle_ps(first, last, _MM_SHUFFLE(3, 1, 3, 1));
            energy = _mm256_add_ps(energy, _mm256_add_ps(_mm256_mul_ps(xr, xr),
                                                       _mm256_mul_ps(xi, xi)));
            for (int n = 0; n < count; ++n) {
                __m256 hr = _mm256_set1_ps(p[n]->real[j]), hi = _mm256_set1_ps(p[n]->imag[j]);
                a[n] = _mm256_add_ps(a[n], _mm256_sub_ps(_mm256_mul_ps(xr, hr),
                                                        _mm256_mul_ps(xi, hi)));
                d[n] = _mm256_add_ps(d[n], _mm256_add_ps(_mm256_mul_ps(xr, hi),
                                                        _mm256_mul_ps(xi, hr)));
            }
        }
        power = _mm256_add_ps(power, energy);
        for (int n = 0; n < count; ++n) {
            re[n] = _mm256_add_ps(re[n], a[n]);
            im[n] = _mm256_add_ps(im[n], d[n]);
        }
    }
    const int offset[] = {0, 1, 4, 5, 2, 3, 6, 7};
    float squared[8];
    _mm256_storeu_ps(squared, power);
    for (int n = 0; n < count; ++n) {
        float real[8], imag[8];
        _mm256_storeu_ps(real, re[n]);
        _mm256_storeu_ps(imag, im[n]);
        for (int i = 0; i < 8; ++i)
            matrix[n][offset[i]][frame][b] = (LateCorrelation){real[i], imag[i], squared[i]};
    }
}

static inline __attribute__((always_inline))
void refine_last(const float *iq, const RefineRotation *const *p, int count,
                 int begin, int chains, BlockMatrix *matrix, int frame, int b)
{
    float re[2] = {0.f}, im[2] = {0.f}, power = 0.f;
    for (int c = 0; c < chains; ++c) {
        float a[2] = {0.f}, d[2] = {0.f}, energy = 0.f;
        for (int j = begin + c; j < begin + block; j += chains) {
            float xr = iq[2*j], xi = iq[2*j + 1];
            energy += xr*xr + xi*xi;
            for (int n = 0; n < count; ++n) {
                float hr = p[n]->real[j], hi = p[n]->imag[j];
                a[n] += xr*hr - xi*hi;
                d[n] += xr*hi + xi*hr;
            }
        }
        power += energy;
        for (int n = 0; n < count; ++n) {
            re[n] += a[n];
            im[n] += d[n];
        }
    }
    for (int n = 0; n < count; ++n)
        matrix[n][8][frame][b] = (LateCorrelation){re[n], im[n], power};
}

static inline __attribute__((target("avx2"), always_inline))
void correlate_group(const float *x, const RefineRotation *const *rotation, int count,
                     int epoch, BlockMatrix *matrix)
{
    for (int f = 0; f < frames; ++f) {
        int begin = (40000*f + 1)/3 + 88 + epoch - 4;
        const float *iq = x + 2*begin;
        for (int b = 0; b < 8; ++b) {
            if (b < 4) {
                refine_eight(iq, rotation, count, b*block, 4, matrix, f, b);
                refine_last(iq + 16, rotation, count, b*block, 4, matrix, f, b);
            } else {
                refine_eight(iq, rotation, count, b*block, 1, matrix, f, b);
                refine_last(iq + 16, rotation, count, b*block, 1, matrix, f, b);
            }
        }
    }
}

static inline int safe_request(RefineRequest request)
{
    return request.epoch >= 4 && request.epoch < period - 4 && isfinite(request.hz);
}

__attribute__((target("avx2")))
static int refine_batch(const float *x, const float *h, const RefineRequest *seeds,
                        int count, double lo, double hi, double (*out)[4])
{
    enum { capacity = 4 };
    RefineRotation prepared[capacity];
    int rotation_slot[capacity], rotated = 0, completed[capacity] = {0};
    double hz[capacity];
    for (int i = 0; i < count; ++i) {
        if (!safe_request(seeds[i])) continue;
        int k = 0;
        while (k < rotated && memcmp(&hz[k], &seeds[i].hz, sizeof(double))) ++k;
        if (k == rotated) {
            prepare_refine_rotation(h, seeds[i].hz, &prepared[k]);
            hz[rotated++] = seeds[i].hz;
        }
        rotation_slot[i] = k;
    }
    for (int i = 0; i < count; ++i) {
        if (completed[i]) continue;
        RefineRequest seed = seeds[i];
        if (!safe_request(seed)) {
            if (delay_refine(x, h, seed.epoch, seed.hz, lo, hi, out[i])) return -1;
            continue;
        }
        int j = i + 1;
        while (j < count && (completed[j] || seeds[j].epoch != seed.epoch ||
                             !safe_request(seeds[j]))) ++j;
        const RefineRotation *rotation[2] = {&prepared[rotation_slot[i]], NULL};
        BlockMatrix matrix[2];
        if (j < count) {
            completed[j] = 1;
            rotation[1] = &prepared[rotation_slot[j]];
            correlate_group(x, rotation, 2, seed.epoch, matrix);
            finish_refine(seeds[j].epoch, seeds[j].hz, lo, hi, rotation[1]->energy,
                           matrix[1], out[j]);
        } else {
            correlate_group(x, rotation, 1, seed.epoch, matrix);
        }
        finish_refine(seed.epoch, seed.hz, lo, hi, rotation[0]->energy, matrix[0], out[i]);
    }
    return 0;
}

int delay_refine_bank(const float *x, const float *h, const RefineRequest *seeds,
                      int count, double lo, double hi, double (*out)[4])
{
    if (!x || !h || !seeds || !out || count < 0 || !(hi > lo)) return -1;
    if (count <= 4 && __builtin_cpu_supports("avx2"))
        return refine_batch(x, h, seeds, count, lo, hi, out);
    for (int i = 0; i < count; ++i)
        if (delay_refine(x, h, seeds[i].epoch, seeds[i].hz, lo, hi, out[i])) return -1;
    return 0;
}
