#define _POSIX_C_SOURCE 200809L
/* Deliberately include the private research TU: this edge fixture inspects the
 * coarse grid after qualification, which restores the direct FP32 grid. */
#include "full_search.c"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static uint32_t edge_state = 0x51a7e93du;

static float edge_random(void)
{
    edge_state = 1664525u * edge_state + 1013904223u;
    return ((edge_state >> 8) * 0x1p-23f - 1.0f) * 0.5f;
}

static void direct_maximum(const leo_presence_workspace *w, int *epoch, int *bin)
{
    double best = -INFINITY;
    *epoch = 0;
    *bin = 0;
    for (int f = 0; f < 11; ++f) {
        for (int e = 0; e < (int)w->n; ++e) {
            double score = w->grid[(size_t)f * w->n + e];
            if (score > best || (score == best &&
                (e < *epoch || (e == *epoch && f < *bin)))) {
                best = score;
                *epoch = e;
                *bin = f;
            }
        }
    }
}

static void inject_anchor(const leo_presence_workspace *w,
    leo_presence_complex *samples, size_t count, int epoch)
{
    for (int symbol = 0; symbol < 12; ++symbol) {
        int taps = (int)(w->stops[symbol] - w->starts[symbol]);
        for (int frame = 0; frame < LEO_PRESENCE_COARSE_FRAMES; ++frame) {
            ptrdiff_t position = w->starts[symbol] + w->offsets[frame] + epoch;
            if (position < 0 || position + taps > (ptrdiff_t)count)
                continue;
            for (int k = 0; k < taps; ++k) {
                double complex reference = w->exact[w->starts[symbol] + k];
                samples[position + k].re += (float)(3.0 * creal(reference));
                samples[position + k].im += (float)(3.0 * cimag(reference));
            }
        }
    }
}

static int run_edge(uint32_t rate, int injected_epoch)
{
    size_t n = (rate + 375) / 750;
    size_t count = rate / 50;
    leo_presence_complex *exact = calloc(n, sizeof(*exact));
    leo_presence_complex *control = calloc(n, sizeof(*control));
    leo_presence_complex *samples = calloc(count, sizeof(*samples));
    if (!exact || !control || !samples) return 1;
    for (size_t k = 0; k < n; ++k) {
        exact[k].re = edge_random(); exact[k].im = edge_random();
        control[k].re = edge_random(); control[k].im = edge_random();
    }
    for (size_t k = 0; k < count; ++k) {
        samples[k].re = 0.02f * edge_random();
        samples[k].im = 0.02f * edge_random();
    }
    leo_presence_workspace *w = leo_presence_create(rate, exact, control, n);
    if (!w) return 1;
    inject_anchor(w, samples, count, injected_epoch);
    double maximum_error;
    int retained_equal, repaired_epochs, fallback, maximum_epoch, maximum_bin;
    int rc = leo_fft_coarse_qualify(w, samples, count, &maximum_error,
        &retained_equal, &repaired_epochs, &fallback);
    direct_maximum(w, &maximum_epoch, &maximum_bin);
    printf("rate=%u epoch=%d direct_epoch=%d direct_bin=%d equal=%d repaired=%d fallback=%d error=%.9g\n",
        rate, injected_epoch, maximum_epoch, maximum_bin, retained_equal,
        repaired_epochs, fallback, maximum_error);
    leo_presence_destroy(w);
    free(samples); free(control); free(exact);
    return rc || !retained_equal || fallback || maximum_epoch != injected_epoch ||
        maximum_bin != 5;
}

int main(void)
{
    const uint32_t rates[] = {5000000, 7500000, 10000000};
    for (size_t i = 0; i < sizeof(rates) / sizeof(rates[0]); ++i) {
        int last = (int)((rates[i] + 375) / 750) - 1;
        if (run_edge(rates[i], 0) || run_edge(rates[i], last)) return 1;
    }
    /* 5 MS/s has 22 taps and the specified 128-point overlap-save step 107. */
    if (run_edge(5000000, 106) || run_edge(5000000, 107)) return 1;
    puts("fft coarse edge fixtures passed");
    return 0;
}
