/* Analytic checks for the isolated radix-2/3/5 full-search FFT. */
#include "fft.h"
#include <complex.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#define PI 3.14159265358979323846264338327950288
#define TOLERANCE 1e-8

static int close_enough(double complex actual, double complex expected)
{
    return cabs(actual - expected) <= TOLERANCE;
}

static int compare_direct(size_t n)
{
    leo_fft fft;
    double complex *input = calloc(n, sizeof(*input));
    if (!input || leo_fft_init(&fft, n)) return 1;
    for (size_t index = 0; index < n; ++index)
        input[index] = (double)(index + 1) + I * (double)((3 * index + 1) % 7);
    leo_fft_forward(&fft, input);
    for (size_t bin = 0; bin < n; ++bin) {
        double complex expected = 0.0;
        for (size_t index = 0; index < n; ++index) {
            double angle = -2.0 * PI * (double)(bin * index) / (double)n;
            expected += input[index] * (cos(angle) + I * sin(angle));
        }
        if (!close_enough(fft.output[bin], expected)) {
            fprintf(stderr, "direct DFT mismatch n=%zu bin=%zu\n", n, bin);
            leo_fft_free(&fft);
            free(input);
            return 1;
        }
    }
    leo_fft_free(&fft);
    free(input);
    return 0;
}

static int impulse(size_t n)
{
    leo_fft fft;
    double complex *input = calloc(n, sizeof(*input));
    if (!input || leo_fft_init(&fft, n)) return 1;
    input[0] = 1.0;
    leo_fft_forward(&fft, input);
    for (size_t bin = 0; bin < n; ++bin)
        if (!close_enough(fft.output[bin], 1.0)) return 1;
    leo_fft_free(&fft);
    free(input);
    return 0;
}

static int sinusoid(size_t n, size_t tone)
{
    leo_fft fft;
    double complex *input = calloc(n, sizeof(*input));
    if (!input || leo_fft_init(&fft, n)) return 1;
    for (size_t index = 0; index < n; ++index) {
        double angle = 2.0 * PI * (double)(tone * index) / (double)n;
        input[index] = cos(angle) + I * sin(angle);
    }
    leo_fft_forward(&fft, input);
    for (size_t bin = 0; bin < n; ++bin) {
        double complex expected = bin == tone ? (double)n : 0.0;
        if (!close_enough(fft.output[bin], expected)) {
            fprintf(stderr, "sinusoid mismatch n=%zu tone=%zu bin=%zu error=%.17g\n",
                n, tone, bin, cabs(fft.output[bin] - expected));
            leo_fft_free(&fft);
            free(input);
            return 1;
        }
    }
    leo_fft_free(&fft);
    free(input);
    return 0;
}

int main(void)
{
    if (impulse(3) || impulse(15000)) return 1;
    if (sinusoid(3, 1) || sinusoid(6, 5) || sinusoid(15, 7)) return 1;
    if (compare_direct(3) || compare_direct(6) || compare_direct(15)) return 1;
    if (sinusoid(15000, 4321)) return 1;
    return 0;
}
