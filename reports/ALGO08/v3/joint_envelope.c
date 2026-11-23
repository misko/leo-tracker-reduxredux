#include <fftw3.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum { cells = 3333, groups = 15, keep = 4, separation = 8, frequencies = cells / 2 + 1 };

typedef struct {
    float folded[cells], row[2][cells];
    float *grid;
    fftwf_complex *work, spectrum[2][frequencies];
    fftwf_plan forward, inverse;
} Aperture;

typedef struct { int sample; float score; } Epoch;

static float normalized(float power, float reciprocal) {
    float fraction = power * reciprocal;
    return (fraction < 8.0f ? fraction : 8.0f) - 1.0f;
}

void joint_envelope_free(Aperture *w) {
    if (!w) return;
    if (w->forward) fftwf_destroy_plan(w->forward);
    if (w->inverse) fftwf_destroy_plan(w->inverse);
    fftwf_free(w->work);
    fftwf_free(w->grid);
    free(w);
}

Aperture *joint_envelope_create(const float *energy) {
    if (!energy) return NULL;
    Aperture *w = calloc(1, sizeof(*w));
    if (!w) return NULL;
    w->grid = fftwf_alloc_real(cells);
    w->work = fftwf_alloc_complex(frequencies);
    if (w->grid && w->work) {
        w->forward = fftwf_plan_dft_r2c_1d(cells, w->grid, w->work, FFTW_ESTIMATE);
        w->inverse = fftwf_plan_dft_c2r_1d(cells, w->work, w->grid, FFTW_ESTIMATE);
    }
    if (!w->forward || !w->inverse) {
        joint_envelope_free(w);
        return NULL;
    }
    float mean = 0.f;
    for (int j = 0; j < cells; ++j) mean += energy[j] / cells;
    if (!(mean > 0.f)) {
        joint_envelope_free(w);
        return NULL;
    }
    for (int mode = 0; mode < 2; ++mode) {
        for (int j = 0; j < cells; ++j) {
            float f = normalized(energy[j], 1.f / mean);
            w->grid[j] = (mode == 0) ? f * f : f;
        }
        fftwf_execute(w->forward);
        memcpy(w->spectrum[mode], w->work, sizeof(w->spectrum[mode]));
    }
    return w;
}

/* Every energy cell covers both I/Q components at four native samples. */
static void accumulate_power(Aperture *w, const int16_t *iq, float means[2]) {
    means[0] = means[1] = 0.f;
    for (int j = 0; j < cells; ++j) {
        float energy[2] = {0.f, 0.f};
        for (int k = 0; k < 4; ++k) {
            const int16_t *x = iq + 16 * j + 4 * k;
            float ar = x[0], ai = x[1], br = x[2], bi = x[3];
            energy[0] += ar * ar + ai * ai;
            energy[1] += br * br + bi * bi;
        }
        w->row[0][j] = energy[0];
        w->row[1][j] = energy[1];
        means[0] += energy[0];
        means[1] += energy[1];
    }
    means[0] = means[0] > 0.f ? cells / means[0] : 0.f;
    means[1] = means[1] > 0.f ? cells / means[1] : 0.f;
}

int joint_envelope_detect(Aperture *w, const int16_t *iq, int lane, int shift, Epoch out[keep]) {
    if (!w || !iq || !out || lane < -1 || lane > 1 || shift < 0 || shift >= cells)
        return -1;
    memset(w->folded, 0, sizeof(w->folded));
    for (int f = 0; f < groups; ++f) {
        const int native_start = 4 * ((10000 * f + 1) / 3);
        float scale[2];
        accumulate_power(w, iq + 4 * native_start, scale);
        if (lane >= 0) {
            if (!scale[lane]) continue;
            for (int j = 0; j < cells; ++j)
                w->folded[j] += normalized(w->row[lane][j], scale[lane]);
        } else if (scale[0] > 0.f && scale[1] > 0.f) {
            int shifted = shift;
            for (int j = 0; j < cells; ++j) {
                w->folded[j] += normalized(w->row[0][j], scale[0]) *
                    normalized(w->row[1][shifted], scale[1]);
                if (++shifted == cells) shifted = 0;
            }
        }
    }
    memcpy(w->grid, w->folded, sizeof(w->folded));
    fftwf_execute(w->forward);
    const fftwf_complex *pattern = w->spectrum[lane >= 0];
    w->work[0][0] = w->work[0][1] = 0.f;
    for (int i = 1; i < frequencies; ++i) {
        float x = w->work[i][0], y = w->work[i][1];
        float a = pattern[i][0], b = pattern[i][1];
        w->work[i][0] = x * a + y * b;
        w->work[i][1] = y * a - x * b;
    }
    fftwf_execute(w->inverse);
    for (int k = 0; k < keep; ++k) {
        int best = 0;
        for (int i = 1; i < cells; ++i)
            if (w->grid[i] > w->grid[best]) best = i;
        if (!(w->grid[best] > 0.f)) return k;
        out[k] = (Epoch){4 * best, w->grid[best]};
        for (int j = -separation; j <= separation; ++j)
            w->grid[(best + j + cells) % cells] = -INFINITY;
    }
    return keep;
}
