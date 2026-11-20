#define _POSIX_C_SOURCE 200809L
#include "../variants/portable_fine.h"

#include <float.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

_Static_assert(sizeof(double) == 8 && DBL_MANT_DIG == 53, "binary64 required");
_Static_assert(sizeof(PortableFineComplex) == 16 && sizeof(PortableFinePeak) == 40,
               "unexpected packed evidence ABI");

static void require(int condition, const char *message) {
    if (!condition) {
        fprintf(stderr, "%s\n", message);
        exit(2);
    }
}

static uint64_t now(clockid_t clock) {
    struct timespec t;
    require(clock_gettime(clock, &t) == 0, "clock unavailable");
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

static void take(FILE *stream, void *buffer, size_t size) {
    require(fread(buffer, 1, size, stream) == size, "truncated fixture");
}

static void emit(const void *data, size_t size) {
    require(fwrite(data, 1, size, stdout) == size, "could not emit score vector");
}

static int self_test(void) {
    PortableFinePeak result;
    const double tie[] = {0.4, 0.4, 0.3};
    require(portable_fine_peak(tie, -250, 3, &result) == 0 && result.winner == 0 &&
            result.runner == 1 && result.guard == PORTABLE_FINE_CLOSE_RANK &&
            result.interpolated_hz == -250.0, "equal-score signed CFO order changed");
    const double flat[] = {0, 0, 0};
    require(portable_fine_peak(flat, -500, 3, &result) == 0 && result.winner == 1 &&
            result.runner == 0 && result.guard == (PORTABLE_FINE_CLOSE_RANK |
            PORTABLE_FINE_UNSTABLE_INTERPOLATION), "flat peak lacks both guards");
    const double near[] = {0.25, 0.25 + 3e-13, 0.25};
    require(portable_fine_peak(near, 0, 3, &result) == 0 && result.winner == 1 &&
            result.guard == (PORTABLE_FINE_CLOSE_RANK | PORTABLE_FINE_UNSTABLE_INTERPOLATION),
            "nearly equal scores lack both guards");
    const double asymmetric[] = {0.25, 0.5, 0.4};
    require(portable_fine_peak(asymmetric, -500, 3, &result) == 0 && result.winner == 1 &&
            result.runner == 2 && result.guard == 0 && result.interpolated_hz > 107.14 &&
            result.interpolated_hz < 107.15, "interior interpolation changed");
    const double upper[] = {0.1, 0.2, 0.3};
    require(portable_fine_peak(upper, 4999000, 3, &result) == 0 && result.winner == 2 &&
            result.runner == 1 && result.interpolated_hz == 5000000, "upper band edge changed");
    require(portable_fine_peak(upper, 4999500, 3, &result) == -1,
            "grid above supported band was accepted");
    puts("portable fine peak sentinels passed");
    return 0;
}

int main(int argc, char **argv) {
    require(argc == 2, "usage: portable-fine captured.iq | --self-test");
    if (strcmp(argv[1], "--self-test") == 0) return self_test();
    const uint32_t one = 1;
    require(*(const unsigned char *)&one == 1, "evidence fixture requires a little-endian machine");
    uint64_t start = now(CLOCK_MONOTONIC), cpu = now(CLOCK_PROCESS_CPUTIME_ID);
    FILE *input = fopen(argv[1], "rb");
    require(input != NULL, "cannot open captured fixture");
    char magic[8];
    uint32_t visits;
    take(input, magic, sizeof(magic));
    take(input, &visits, sizeof(visits));
    require(memcmp(magic, "LEOFINE1", 8) == 0 && visits > 0 && visits <= 256,
            "unsupported captured fixture");
    size_t iq_bytes = PORTABLE_FINE_SAMPLES * 4 * sizeof(int16_t);
    size_t converted_bytes = PORTABLE_FINE_SAMPLES * sizeof(PortableFineComplex);
    size_t template_bytes = PORTABLE_FINE_EPOCHS * sizeof(PortableFineComplex);
    PortableFineComplex *samples = malloc(converted_bytes), *reference = malloc(template_bytes);
    PortableFineWorkspace *workspace = malloc(sizeof(*workspace));
    int16_t *iq = malloc(iq_bytes);
    require(iq && samples && reference && workspace, "fixture workspace allocation failed");
    take(input, reference, template_bytes);
    uint64_t mark = now(CLOCK_PROCESS_CPUTIME_ID);
    portable_fine_prepare(workspace);
    uint64_t setup_ns = now(CLOCK_PROCESS_CPUTIME_ID) - mark;
    uint64_t score_ns = 0, rank_ns = 0, conversion_ns = 0;
    unsigned calls = 0;

    for (uint32_t i = 0; i < visits; ++i) {
        uint32_t visit, count;
        take(input, &visit, sizeof(visit));
        take(input, &count, sizeof(count));
        require(count > 0 && count <= 64, "invalid call count");
        take(input, iq, iq_bytes);
        uint32_t previous_lane = 2;
        for (uint32_t j = 0; j < count; ++j) {
            uint32_t lane, epoch, bins;
            double absolute, residual, scores[PORTABLE_FINE_MAX_BINS];
            take(input, &lane, sizeof(lane));
            take(input, &epoch, sizeof(epoch));
            take(input, &bins, sizeof(bins));
            take(input, &absolute, sizeof(absolute));
            take(input, &residual, sizeof(residual));
            require(lane < 2, "invalid physical receive lane");
            if (lane != previous_lane) {
                mark = now(CLOCK_PROCESS_CPUTIME_ID);
                for (int sample = 0; sample < PORTABLE_FINE_SAMPLES; ++sample) {
                    size_t index = 4 * (size_t)sample + 2 * lane;
                    samples[sample] = (PortableFineComplex){iq[index], iq[index + 1]};
                }
                conversion_ns += now(CLOCK_PROCESS_CPUTIME_ID) - mark;
                previous_lane = lane;
            }
            PortableFinePeak result;
            unsigned frames;
            mark = now(CLOCK_PROCESS_CPUTIME_ID);
            require(portable_fine_score(workspace, samples, reference, epoch, absolute,
                                        bins, scores, &frames) == 0, "unsupported fine score");
            score_ns += now(CLOCK_PROCESS_CPUTIME_ID) - mark;
            mark = now(CLOCK_PROCESS_CPUTIME_ID);
            require(portable_fine_peak(scores, residual, bins, &result) == 0,
                    "unsupported peak fit");
            rank_ns += now(CLOCK_PROCESS_CPUTIME_ID) - mark;
            result.frames = frames;
            emit(scores, bins * sizeof(double));
            emit(&result, sizeof(result));
            ++calls;
        }
    }
    require(fgetc(input) == EOF && !ferror(input) && fflush(stdout) == 0,
            "fixture or score output did not terminate cleanly");
    fclose(input);
    fprintf(stderr,
            "{\"visits\":%u,\"calls\":%u,\"workspace_bytes\":%zu,"
            "\"input_allocation_bytes\":%zu,\"score_setup_cpu_ns\":%" PRIu64 ","
            "\"iq_conversion_cpu_ns\":%" PRIu64 ",\"score_cpu_ns\":%" PRIu64 ","
            "\"peak_cpu_ns\":%" PRIu64 ",\"process_cpu_ns\":%" PRIu64 ","
            "\"elapsed_ns\":%" PRIu64 "}\n",
            visits, calls, sizeof(*workspace), iq_bytes + converted_bytes + template_bytes,
            setup_ns, conversion_ns, score_ns, rank_ns,
            now(CLOCK_PROCESS_CPUTIME_ID) - cpu, now(CLOCK_MONOTONIC) - start);
    free(iq);
    free(workspace);
    free(reference);
    free(samples);
    return 0;
}
