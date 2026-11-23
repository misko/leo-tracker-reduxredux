#include <fftw3.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum { samples = 200000, half_carrier_bins = 16000, carrier_bins = 2 * half_carrier_bins + 1 };

typedef struct {
    fftwf_complex *fft;
    fftwf_plan plan;
    float *power;
    int size, stride;
} Comb;

void sparse_template_free(Comb *w) {
    if (!w) return;
    if (w->plan) fftwf_destroy_plan(w->plan);
    fftwf_free(w->power);
    fftwf_free(w->fft);
    free(w);
}

Comb *sparse_template_create(int stride) {
    if (stride != 1 && stride != 4) return NULL;
    Comb *w = calloc(1, sizeof(*w));
    if (!w) return NULL;
    w->stride = stride;
    w->size = samples / stride;
    w->power = fftwf_alloc_real(2 * w->size);
    w->fft = fftwf_alloc_complex(w->size);
    if (w->fft) w->plan = fftwf_plan_dft_1d(w->size, w->fft, w->fft, FFTW_FORWARD, FFTW_ESTIMATE);
    if (!w->power || !w->plan) {
        sparse_template_free(w);
        return NULL;
    }
    return w;
}

int sparse_template_comb(Comb *w, const int16_t *iq, int lane,
                         const int *lines, const float *weights, int count, float *scores) {
    if (!w || !iq || !scores || lane < 0 || lane > 1 || count < 0 ||
        (count && (!lines || !weights))) return -1;
    int n = w->size;
    for (int i = 0; i < n; ++i) {
        const int16_t *x = iq + 4 * w->stride * i + 2 * lane;
        w->fft[i][0] = x[0];
        w->fft[i][1] = x[1];
    }
    fftwf_execute(w->plan);
    if (!count) return 0;
    for (int i = 0; i < n; ++i) {
        const float re = w->fft[i][0], im = w->fft[i][1];
        w->power[i] = re * re + im * im;
    }
    memcpy(w->power + n, w->power, n * sizeof(float));
    memset(scores, 0, carrier_bins * sizeof(float));
    for (int k = 0; k < count; ++k) {
        if (lines[k] < 0 || lines[k] >= n) return -1;
        const int start = (lines[k] + n - half_carrier_bins) % n;
        const float *power = w->power + start;
        const float weight = weights[k];
        for (int b = 0; b < carrier_bins; ++b) scores[b] += weight * power[b];
    }
    return 0;
}
