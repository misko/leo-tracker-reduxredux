/* Measure independent stock or sample-interleaved FFTW transforms on one core. */
#include <complex.h>
#include <fftw3.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {
    int n, lanes;
    fftwf_complex *scratch;
    fftwf_plan scalar, batch;
} Bench;

static uint64_t thread_clock(void) {
    struct timespec t;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
    return (uint64_t)t.tv_sec * 1000000000 + (uint64_t)t.tv_nsec;
}

void fft_lane_free(Bench *b) {
    if (!b) return;
    if (b->scalar) fftwf_destroy_plan(b->scalar);
    if (b->batch) fftwf_destroy_plan(b->batch);
    fftwf_free(b->scratch);
    free(b);
}

Bench *fft_lane_create(int n, int lanes, int backwards) {
    if ((n != 4096 && n != 4800) || (lanes != 2 && lanes != 4 && lanes != 8)) return NULL;
    Bench *b = calloc(1, sizeof(*b));
    if (!b) return NULL;
    b->n = n;
    b->lanes = lanes;
    b->scratch = fftwf_alloc_complex((size_t)n * lanes);
    if (b->scratch) {
        int sign = backwards ? FFTW_BACKWARD : FFTW_FORWARD;
        fftwf_complex *v = b->scratch;
        b->scalar = fftwf_plan_dft_1d(n, v, v, sign, FFTW_ESTIMATE);
        b->batch = fftwf_plan_many_dft(1, &n, lanes, v, NULL, lanes, 1,
                                      v, NULL, lanes, 1, sign, FFTW_ESTIMATE);
    }
    if (!b->scalar || !b->batch) {
        fft_lane_free(b);
        return NULL;
    }
    return b;
}

char *fft_lane_plan(Bench *b, int batched) {
    return fftwf_sprint_plan(batched ? b->batch : b->scalar);
}

void fft_lane_plan_free(char *plan) { free(plan); }

static void pack(const fftwf_complex *src, fftwf_complex *dest, int n, int lanes) {
    for (int lane = 0; lane < lanes; ++lane)
        for (int i = 0; i < n; ++i)
            dest[i * lanes + lane] = src[lane * n + i];
}

static void unpack(const fftwf_complex *src, fftwf_complex *dest, int n, int lanes) {
    for (int lane = 0; lane < lanes; ++lane)
        for (int i = 0; i < n; ++i)
            dest[lane * n + i] = src[i * lanes + lane];
}

/* Input, output and observed receiver rows are always in chronological lane order. */
void fft_lane_measure(Bench *b, const fftwf_complex *input, fftwf_complex *output,
                      int groups, int batched, uint64_t elapsed[2]) {
    int n = b->n, lanes = b->lanes;
    size_t length = (size_t)n * lanes;
    elapsed[0] = elapsed[1] = 0;
    for (int i = 0; i < groups; ++i) {
        uint64_t start = thread_clock();
        if (batched) pack(input, b->scratch, n, lanes);
        else memcpy(b->scratch, input, length * sizeof(*input));
        uint64_t kernel = thread_clock();
        if (batched) fftwf_execute(b->batch);
        else for (int lane = 0; lane < lanes; ++lane) {
            fftwf_complex *part = b->scratch + lane * n;
            fftwf_execute_dft(b->scalar, part, part);
        }
        elapsed[0] += thread_clock() - kernel;
        if (batched) unpack(b->scratch, output, n, lanes);
        else memcpy(output, b->scratch, length * sizeof(*output));
        elapsed[1] += thread_clock() - start;
        input += length;
        output += length;
    }
}
