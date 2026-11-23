#include <fftw3.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum { line_count = 16, capacity = 4 };
static const double sample_rate = 5000000.;
static const double pilot_rate = 750.;

typedef struct {
    int size;
    fftwf_complex *signal;
    fftwf_complex *spectrum;
    fftwf_plan plan;
    float *window;
    float *power;
    float *score;
} CyclicCarrier;

void cyclic_carrier_free(CyclicCarrier *work) {
    if (!work) return;
    if (work->plan) fftwf_destroy_plan(work->plan);
    fftwf_free(work->signal);
    fftwf_free(work->spectrum);
    free(work->window);
    free(work->power);
    free(work->score);
    free(work);
}

CyclicCarrier *cyclic_carrier_create(int size) {
    if (size != 16384 && size != 32768) return NULL;
    CyclicCarrier *work = calloc(1, sizeof(*work));
    if (!work) return NULL;
    work->size = size;
    work->signal = fftwf_alloc_complex(size);
    work->spectrum = fftwf_alloc_complex(size);
    work->window = malloc(size * sizeof(float));
    work->power = malloc(2 * size * sizeof(float));
    work->score = malloc(size * sizeof(float));
    if (!work->signal || !work->spectrum || !work->window || !work->power || !work->score) {
        cyclic_carrier_free(work);
        return NULL;
    }
    work->plan = fftwf_plan_dft_1d(size, work->signal, work->spectrum, FFTW_FORWARD, FFTW_ESTIMATE);
    if (!work->plan) {
        cyclic_carrier_free(work);
        return NULL;
    }
    for (int i = 0; i < size; ++i)
        work->window[i] = (float)(.5 - .5 * cos(6.283185307179586 * i / size));
    return work;
}

static void make_spectrum(CyclicCarrier *work, const int16_t *iq, int lane) {
    const int16_t *sample = iq + 2 * lane;
    for (int i = 0; i < work->size; ++i, sample += 8) {
        const float real = sample[0], imag = sample[1], next_real = sample[4], next_imag = sample[5];
        const float taper = work->window[i];
        work->signal[i][0] = taper * (real * next_real - imag * next_imag);
        work->signal[i][1] = taper * (real * next_imag + imag * next_real);
    }
    fftwf_execute(work->plan);
    for (int i = 0; i < work->size; ++i) {
        const float real = work->spectrum[i][0], imag = work->spectrum[i][1];
        work->power[i] = real * real + imag * imag;
    }
    memcpy(work->power + work->size, work->power, work->size * sizeof(float));
}

static int make_scores(CyclicCarrier *work, const int16_t *iq, int lane, double center,
                       const int *lines, const float *weights, int *first_bin) {
    if (!work || !iq || !lines || !weights || lane < 0 || lane > 1
        || !isfinite(center) || fabs(center) > sample_rate / 2) return -1;
    const int size = work->size;
    const double spacing = sample_rate / size;
    const int low = (int)ceil(2 * (center - 800000.) / spacing);
    const int high = (int)floor(2 * (center + 800000.) / spacing);
    const int count = high - low + 1;
    *first_bin = low;
    make_spectrum(work, iq, lane);
    memset(work->score, 0, count * sizeof(float));
    for (int line = 0; line < line_count; ++line) {
        const double bin = pilot_rate * lines[line] / spacing;
        const int offset = (int)floor(bin);
        const float fraction = (float)(bin - offset);
        const float *bins = work->power + ((low + offset + 2 * size) & (size - 1));
        const float before = weights[line] * (1.f - fraction), after = weights[line] * fraction;
        for (int i = 0; i < count; ++i)
            work->score[i] += before * bins[i] + after * bins[i + 1];
    }
    return count;
}

int cyclic_carrier_surface(CyclicCarrier *work, const int16_t *iq, int lane,
                           double center, const int *lines, const float *weights,
                           float *scores, int *first_bin) {
    if (!scores || !first_bin) return -1;
    const int count = make_scores(work, iq, lane, center, lines, weights, first_bin);
    if (count > 0) memcpy(scores, work->score, count * sizeof(float));
    return count;
}

int cyclic_carrier_accumulate(const float *scores, int size, double lower, double bin_hz,
                             const double *carrier, int satellites, const double *offsets,
                             int cells, double *sums) {
    int reads = 0;
    for (int sat = 0; sat < satellites; ++sat) {
        if (!isfinite(carrier[sat])) continue;
        for (int i = 0; i < cells; ++i) {
            const double index = (carrier[sat] + offsets[i] - lower) / bin_hz;
            if (index < 0 || index > size - 1) continue;
            const int bin = (int)index;
            const double weight = index - bin;
            const float left = scores[bin];
            const float right = scores[bin + (bin < size - 1)];
            sums[sat * cells + i] += left + weight * (right - left);
            ++reads;
        }
    }
    return reads;
}

int cyclic_carrier_propose(CyclicCarrier *work, const int16_t *iq, int lane,
                          double center, const int *lines, const float *weights,
                          double *hz, double *scores) {
    if (!hz || !scores) return -1;
    int low;
    const int count = make_scores(work, iq, lane, center, lines, weights, &low);
    if (count < 0) return count;
    const double spacing = sample_rate / work->size;
    const int exclude = (int)ceil(2 * 10000. / spacing);
    for (int hypothesis = 0; hypothesis < capacity; ++hypothesis) {
        int best = 0;
        for (int i = 1; i < count; ++i)
            if (work->score[i] > work->score[best]) best = i;
        hz[hypothesis] = (low + best) * spacing / 2;
        scores[hypothesis] = work->score[best];
        const int start = best >= exclude ? best - exclude + 1 : 0;
        const int stop = best + exclude < count ? best + exclude : count;
        for (int i = start; i < stop; ++i) work->score[i] = -INFINITY;
    }
    return capacity;
}
