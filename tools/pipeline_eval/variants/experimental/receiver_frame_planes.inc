/* Each four-sample stripe stores two frames' real vectors, then their imaginary vectors. */
#include <immintrin.h>

static inline float *frame_plane(TimingFirst *w, int frame) {
    return (float *)w->frames + (frame / 2) * (4 * w->width) + (frame % 2) * 4;
}

__attribute__((target("avx2")))
static void normalize_plane(float *plane, const Sample *low, int width) {
    double ar = 0., ai = 0., norm = 0.;
    for (int i = 0; i < width; ++i) {
        ar += low[i].re;
        ai += low[i].im;
    }
    __m128 mean_r = _mm_set1_ps((float)(ar / width));
    __m128 mean_i = _mm_set1_ps((float)(ai / width));
    for (int i = 0; i < width; i += 4) {
        float *stripe = plane + 4 * i;
        __m128 a = _mm_loadu_ps((const float *)(low + i));
        __m128 b = _mm_loadu_ps((const float *)(low + i + 2));
        __m128 re = _mm_sub_ps(_mm_shuffle_ps(a, b, _MM_SHUFFLE(2, 0, 2, 0)), mean_r);
        __m128 im = _mm_sub_ps(_mm_shuffle_ps(a, b, _MM_SHUFFLE(3, 1, 3, 1)), mean_i);
        _mm_storeu_ps(stripe, re);
        _mm_storeu_ps(stripe + 8, im);
        float contribution[4];
        _mm_storeu_ps(contribution, _mm_add_ps(_mm_mul_ps(re, re), _mm_mul_ps(im, im)));
        for (int k = 0; k < 4; ++k)
            norm += contribution[k];
    }
    __m128 scale = _mm_set1_ps((float)(1. / fmax(sqrt(norm / width), 1e-12)));
    for (int i = 0; i < width; i += 4) {
        float *stripe = plane + 4 * i;
        _mm_storeu_ps(stripe, _mm_mul_ps(_mm_loadu_ps(stripe), scale));
        _mm_storeu_ps(stripe + 8, _mm_mul_ps(_mm_loadu_ps(stripe + 8), scale));
    }
}

__attribute__((target("avx2")))
static inline float sum_four(__m128 values) {
    float lanes[4], sum = 0.f;
    _mm_storeu_ps(lanes, values);
    for (int k = 0; k < 4; ++k)
        sum += lanes[k];
    return sum;
}

__attribute__((target("avx2")))
static void covariance_plane_pair(const float *a, const float *b, int width, Sample out[2]) {
    __m256 re = _mm256_setzero_ps(), im = _mm256_setzero_ps();
    for (int i = 0; i < width; i += 4) {
        const float *other = b + 4 * i, *current = a + 4 * i;
        __m256 ar = _mm256_broadcast_ps((const __m128 *)current);
        __m256 ai = _mm256_broadcast_ps((const __m128 *)(current + 8));
        __m256 br = _mm256_loadu_ps(other), bi = _mm256_loadu_ps(other + 8);
        re = _mm256_add_ps(re, _mm256_add_ps(_mm256_mul_ps(ar, br), _mm256_mul_ps(ai, bi)));
        im = _mm256_add_ps(im, _mm256_sub_ps(_mm256_mul_ps(ai, br), _mm256_mul_ps(ar, bi)));
    }
    out[0] = (Sample){sum_four(_mm256_castps256_ps128(re)), sum_four(_mm256_castps256_ps128(im))};
    out[1] = (Sample){sum_four(_mm256_extractf128_ps(re, 1)), sum_four(_mm256_extractf128_ps(im, 1))};
}

__attribute__((target("avx2")))
static Sample covariance_plane_diagonal(const float *a, int width) {
    __m128 re = _mm_setzero_ps(), im = _mm_setzero_ps();
    for (int i = 0; i < width; i += 4) {
        const float *stripe = a + 4 * i;
        __m128 ar = _mm_loadu_ps(stripe), ai = _mm_loadu_ps(stripe + 8);
        __m128 ri = _mm_mul_ps(ar, ai);
        re = _mm_add_ps(re, _mm_add_ps(_mm_mul_ps(ar, ar), _mm_mul_ps(ai, ai)));
        im = _mm_add_ps(im, _mm_sub_ps(ri, ri));
    }
    return (Sample){sum_four(re), sum_four(im)};
}

static void build_frame_planes(TimingFirst *w, const Sample *low,
                               double complex covariance[count][count],
                               double complex axis[count][count]) {
    for (int f = 0; f < count; ++f) {
        const int start = rounded_offset(f, w->stride) + first / w->stride;
        float *a = frame_plane(w, f);
        normalize_plane(a, low + start, w->width);
        axis[f][f] = 1.;
        int other = 0;
        for (; other < f; other += 2) {
            Sample values[2];
            covariance_plane_pair(a, frame_plane(w, other), w->width, values);
            store_covariance(covariance, f, other, values[0]);
            store_covariance(covariance, f, other + 1, values[1]);
        }
        if (other == f)
            store_covariance(covariance, f, f, covariance_plane_diagonal(a, w->width));
    }
}

__attribute__((target("avx2")))
static void project_frame_planes(TimingFirst *w, double complex covariance[count][count],
                                 double complex axis[count][count]) {
    int mode[2] = {0};
    for (int m = 0; m < 2; ++m) {
        for (int k = 1; k < count; ++k)
            if (creal(covariance[k][k]) > creal(covariance[mode[m]][mode[m]]))
                mode[m] = k;
        covariance[mode[m]][mode[m]] = -INFINITY;
    }
    __m256 wr[count], wi[count];
    const float *planes[count];
    for (int k = 0; k < count; ++k) {
        wr[k] = _mm256_set_m128(_mm_set1_ps((float)creal(axis[k][mode[1]])),
                               _mm_set1_ps((float)creal(axis[k][mode[0]])));
        wi[k] = _mm256_set_m128(_mm_set1_ps((float)-cimag(axis[k][mode[1]])),
                               _mm_set1_ps((float)-cimag(axis[k][mode[0]])));
        planes[k] = frame_plane(w, k);
    }
    for (int i = 0; i < w->width; i += 4) {
        __m256 re = _mm256_setzero_ps(), im = _mm256_setzero_ps();
        for (int k = 0; k < count; ++k) {
            const float *z = planes[k] + 4 * i;
            __m256 zr = _mm256_broadcast_ps((const __m128 *)z);
            __m256 zi = _mm256_broadcast_ps((const __m128 *)(z + 8));
            re = _mm256_add_ps(re, _mm256_sub_ps(_mm256_mul_ps(wr[k], zr), _mm256_mul_ps(wi[k], zi)));
            im = _mm256_add_ps(im, _mm256_add_ps(_mm256_mul_ps(wr[k], zi), _mm256_mul_ps(wi[k], zr)));
        }
        __m256 first_two = _mm256_unpacklo_ps(re, im), last_two = _mm256_unpackhi_ps(re, im);
        float *a = (float *)(w->modes + i), *b = (float *)(w->modes + w->width + i);
        _mm_storeu_ps(a, _mm256_castps256_ps128(first_two));
        _mm_storeu_ps(a + 4, _mm256_castps256_ps128(last_two));
        _mm_storeu_ps(b, _mm256_extractf128_ps(first_two, 1));
        _mm_storeu_ps(b + 4, _mm256_extractf128_ps(last_two, 1));
    }
}
