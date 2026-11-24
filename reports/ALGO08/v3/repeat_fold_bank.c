#define _POSIX_C_SOURCE 200809L
#include <fftw3.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static void shifted_product(int count, const fftwf_complex *restrict folded,
                            const fftwf_complex *restrict pilot, fftwf_complex *restrict out) {
    for (int k = 0; k < count; ++k) {
        const float ar = folded[k][0], ai = folded[k][1];
        const float br = pilot[k][0], bi = pilot[k][1];
        out[k][0] = ar * br + ai * bi;
        out[k][1] = ai * br - ar * bi;
    }
}

static void delay_spectrum(int period, int stride, int shift, const fftwf_complex *folded,
                           const fftwf_complex *pilot, fftwf_complex *row,
                           fftwf_complex *scratch) {
    fftwf_complex *product = stride == 1 ? row : scratch;
    const int tail = period - shift;
    shifted_product(tail, folded + shift, pilot, product);
    shifted_product(shift, folded, pilot + tail, product + tail);
    if (stride == 1) return;

    const int length = period / stride;
    memcpy(row, product, length * sizeof(*row));
    /* Sum spectral aliases to obtain the exact inverse at delays 0, stride, ... */
    for (int phase = 1; phase < stride; ++phase) {
        const fftwf_complex *part = product + phase * length;
        for (int k = 0; k < length; ++k) {
            row[k][0] += part[k][0];
            row[k][1] += part[k][1];
        }
    }
}

static void fill(fftwf_complex *values, int count, int seed) {
    for (int i = 0; i < count; ++i) {
        values[i][0] = (float)((37 * i + seed) % 201 - 100) / 100;
        values[i][1] = (float)((19 * i + seed) % 179 - 89) / 100;
    }
}

static int check(void) {
    enum { period = 64 };
    const double angle = 2 * acos(-1) / period;
    const int shifts[] = {-17, 0, 21};
    fftwf_complex *folded = fftwf_alloc_complex(period);
    fftwf_complex *pilot = fftwf_alloc_complex(period);
    fftwf_complex *row = fftwf_alloc_complex(period);
    fftwf_complex scratch[period], input_time[period], pilot_time[period];
    if (!folded || !pilot || !row) return 1;
    fill(folded, period, 43);
    fill(pilot, period, 17);
    memcpy(input_time, folded, sizeof(input_time));
    memcpy(pilot_time, pilot, sizeof(pilot_time));
    fftwf_plan fft = fftwf_plan_dft_1d(period, folded, folded, FFTW_FORWARD, FFTW_ESTIMATE);
    if (!fft) return 1;
    fftwf_execute(fft);
    fftwf_execute_dft(fft, pilot, pilot);
    fftwf_destroy_plan(fft);

    double max_error = 0;
    for (int stride = 1; stride <= 4; stride *= 2) {
        fftwf_plan inverse = fftwf_plan_dft_1d(period / stride, row, row,
                                               FFTW_BACKWARD, FFTW_ESTIMATE);
        if (!inverse) return 1;
        for (size_t s = 0; s < sizeof(shifts) / sizeof(*shifts); ++s) {
            const int lift = shifts[s];
            delay_spectrum(period, stride, (lift + period) % period, folded, pilot, row, scratch);
            fftwf_execute(inverse);
            for (int delay = 0; delay < period; delay += stride) {
                double re = 0, im = 0;
                for (int j = 0; j < period; ++j) {
                    const int k = (j - delay + period) % period;
                    const double ar = input_time[j][0], ai = input_time[j][1];
                    const double br = pilot_time[k][0], bi = pilot_time[k][1];
                    const double c = cos(angle * lift * j), d = sin(angle * lift * j);
                    re += (ar * br + ai * bi) * c + (ai * br - ar * bi) * d;
                    im += (ai * br - ar * bi) * c - (ar * br + ai * bi) * d;
                }
                const int k = delay / stride;
                max_error = fmax(max_error, hypot(re - row[k][0] / period, im - row[k][1] / period));
            }
        }
        fftwf_destroy_plan(inverse);
    }
    fftwf_free(row);
    fftwf_free(pilot);
    fftwf_free(folded);
    printf("%.12g\n", max_error);
    return max_error >= 0.0001;
}

static double seconds(clockid_t clock) {
    struct timespec time;
    if (clock_gettime(clock, &time)) abort();
    return time.tv_sec + time.tv_nsec * 1e-9;
}

int main(int argc, char **argv) {
    if (argc == 2 && !strcmp(argv[1], "--check")) return check();
    if (argc != 6) return 2;
    const int period = atoi(argv[1]), stride = atoi(argv[2]), rows = atoi(argv[3]);
    const int tile = atoi(argv[4]), lift_step = atoi(argv[5]);
    if (period < 1 || (stride != 1 && stride != 2 && stride != 4) || period % stride ||
        (tile != 1 && tile != 8) || rows < tile || lift_step < 1) return 2;
    const int length = period / stride, tail = rows % tile;
    fftwf_complex *folded = fftwf_alloc_complex(period), *pilot = fftwf_alloc_complex(period);
    fftwf_complex *scratch = fftwf_alloc_complex(period), *data = fftwf_alloc_complex(tile * length);
    fftwf_complex *ready = fftwf_alloc_complex(tile * length);
    if (!folded || !pilot || !scratch || !data || !ready) return 1;
    fill(folded, period, 43);
    fill(pilot, period, 17);
    fill(ready, tile * length, 9);
    fftwf_plan full = fftwf_plan_many_dft(1, &length, tile, data, NULL, 1, length,
                                        data, NULL, 1, length, FFTW_BACKWARD, FFTW_ESTIMATE);
    fftwf_plan last = tail ? fftwf_plan_many_dft(1, &length, tail, data, NULL, 1, length,
                                                data, NULL, 1, length, FFTW_BACKWARD, FFTW_ESTIMATE) : NULL;
    fftwf_plan hot = fftwf_plan_many_dft(1, &length, tile, ready, NULL, 1, length,
                                       data, NULL, 1, length, FFTW_BACKWARD, FFTW_ESTIMATE);
    fftwf_plan hot_tail = tail ? fftwf_plan_many_dft(1, &length, tail, ready, NULL, 1, length,
                                                    data, NULL, 1, length, FFTW_BACKWARD, FFTW_ESTIMATE) : NULL;
    if (!full || !hot || (tail && (!last || !hot_tail))) return 1;

    enum { measured_pairs = 9, sweeps = 8 };
    for (int trial = -1; trial < measured_pairs; ++trial) {
        for (int arm = 0; arm < 2; ++arm) {
            const int multiply = ((trial + 1) % 2) ^ arm;
            double wall = 0, cpu = 0;
            for (int sweep = 0; sweep < sweeps; ++sweep) {
                const double w0 = seconds(CLOCK_MONOTONIC), c0 = seconds(CLOCK_THREAD_CPUTIME_ID);
                for (int first = 0; first < rows; first += tile) {
                    const int complete = rows - first >= tile;
                    if (multiply) {
                        for (int lane = 0; lane < (complete ? tile : tail); ++lane) {
                            const int shift = ((first + lane) * lift_step) % period;
                            delay_spectrum(period, stride, shift, folded, pilot,
                                           data + length * lane, scratch);
                        }
                        fftwf_execute(complete ? full : last);
                    } else {
                        fftwf_execute(complete ? hot : hot_tail);
                    }
                }
                cpu += seconds(CLOCK_THREAD_CPUTIME_ID) - c0;
                wall += seconds(CLOCK_MONOTONIC) - w0;
            }
            if (trial >= 0) printf("%d %d %.9g %.9g\n", trial, multiply, cpu / sweeps, wall / sweeps);
        }
    }
    if (hot_tail) fftwf_destroy_plan(hot_tail);
    fftwf_destroy_plan(hot);
    if (last) fftwf_destroy_plan(last);
    fftwf_destroy_plan(full);
    fftwf_free(ready);
    fftwf_free(data);
    fftwf_free(scratch);
    fftwf_free(pilot);
    fftwf_free(folded);
    return 0;
}
