/* Standalone capture-era folded anchor grid, without Python, radio or FFTW. */
#define _POSIX_C_SOURCE 200809L
#include <complex.h>
#include <float.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

typedef double complex npy_cdouble;
typedef int32_t npy_intp;
typedef int32_t npy_int32;

typedef struct {
    const npy_cdouble *samples, *references;
    const double *frequencies;
    const npy_intp *starts, *stops, *offsets;
    const double *prefix;
    double *scores, *accumulated;
    npy_int32 *support;
    double *correlation_real, *correlation_imag, *rotated_real, *rotated_imag;
    npy_intp sample_count, cfo_count, symbol_count, offset_count;
    double sample_rate_hz;
    int epoch_count, fast_magnitude, invalid_geometry;
} FoldedAnchorGridKernel;

#define LEO_GRID_FUNCTION folded_anchor_grid_portable
#define LEO_GRID_TARGET
#include "_native_acquisition_grid.inc"

typedef struct {
    uint64_t wall, cpu;
} Stamp;

static uint64_t ns(struct timespec t) {
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

static void fail(const char *reason) {
    fprintf(stderr, "%s\n", reason);
    exit(2);
}

static Stamp stamp(void) {
    struct timespec wall, cpu;
    if (clock_gettime(CLOCK_MONOTONIC, &wall) || clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &cpu))
        fail("both Linux clocks are required");
    return (Stamp){ns(wall), ns(cpu)};
}

static size_t heap_bytes;
static uint64_t fixture_tag = UINT64_C(14695981039346656037);

static void *reserve(size_t count, size_t size, int zero) {
    void *p = zero ? calloc(count, size) : malloc(count * size);
    if (!p) fail("could not allocate bounded workspace");
    heap_bytes += count * size;
    return p;
}

static void read_exact(FILE *input, void *buffer, size_t bytes) {
    if (fread(buffer, 1, bytes, input) != bytes) fail("truncated fixture");
    const unsigned char *data = buffer;
    for (size_t i = 0; i < bytes; ++i) {
        fixture_tag ^= data[i];
        fixture_tag *= UINT64_C(1099511628211);
    }
}

static void *read_array(FILE *input, size_t count, size_t size) {
    void *p = reserve(count, size, 0);
    read_exact(input, p, count * size);
    return p;
}

static void elapsed(const char *name, Stamp begin, Stamp end) {
    if (end.wall < begin.wall || end.cpu < begin.cpu) fail("nonmonotonic stage clock");
    fprintf(stderr, "\"%s\":{\"wall_ns\":%" PRIu64 ",\"cpu_ns\":%" PRIu64 "}",
            name, end.wall - begin.wall, end.cpu - begin.cpu);
}

int main(int argc, char **argv) {
    const uint16_t endian = 1;
    if (argc != 2 || *(const unsigned char *)&endian != 1 ||
        sizeof(double) != 8 || sizeof(npy_cdouble) != 16)
        fail("usage: capture-board-folded fixture.bin (little-endian IEEE binary64)");

    const Stamp begin = stamp();
    FILE *input = fopen(argv[1], "rb");
    if (!input) fail("could not open fixture read-only");
    char magic[8];
    uint32_t dims[6];
    double rate;
    read_exact(input, magic, sizeof(magic));
    read_exact(input, dims, sizeof(dims));
    read_exact(input, &rate, sizeof(rate));
    if (memcmp(magic, "LEOFOLD1", 8) != 0 || !isfinite(rate) || rate <= 0 ||
        dims[0] < 1 || dims[0] > 200000 || dims[1] < 1 || dims[1] > 200000 ||
        dims[2] < 1 || dims[2] > 21 || dims[3] < 1 || dims[3] > 22 ||
        dims[4] < 1 || dims[4] > 16 || dims[5] < 1 || dims[5] > 13333)
        fail("invalid or unsupported fixture geometry");

    FoldedAnchorGridKernel k = {
        .sample_count = (npy_intp)dims[0], .cfo_count = (npy_intp)dims[2],
        .symbol_count = (npy_intp)dims[3], .offset_count = (npy_intp)dims[4],
        .sample_rate_hz = rate, .epoch_count = (int)dims[5],
    };
    k.samples = read_array(input, dims[0], sizeof(npy_cdouble));
    k.references = read_array(input, dims[1], sizeof(npy_cdouble));
    k.frequencies = read_array(input, dims[2], sizeof(double));
    k.starts = read_array(input, dims[3], sizeof(npy_intp));
    k.stops = read_array(input, dims[3], sizeof(npy_intp));
    k.offsets = read_array(input, dims[4], sizeof(npy_intp));
    k.prefix = read_array(input, dims[0] + 1, sizeof(double));
    if (fgetc(input) != EOF || ferror(input) || fclose(input)) fail("unexpected fixture suffix");

    npy_intp max_length = 0;
    for (npy_intp i = 0; i < k.symbol_count; ++i) {
        if (k.starts[i] < 0 || k.stops[i] < 0 || (uint32_t)k.stops[i] > dims[1] ||
            k.stops[i] <= k.starts[i] || k.stops[i] - k.starts[i] > k.sample_count ||
            k.stops[i] - k.starts[i] > 64)
            fail("invalid template interval");
        if (k.stops[i] - k.starts[i] > max_length) max_length = k.stops[i] - k.starts[i];
    }
    for (npy_intp i = 0; i < k.offset_count; ++i) {
        if (k.offsets[i] < -k.sample_count || k.offsets[i] > k.sample_count ||
            (i && k.offsets[i] < k.offsets[i - 1]))
            fail("invalid frame offsets");
    }
    for (npy_intp i = 0; i < k.cfo_count; ++i) {
        if (!isfinite(k.frequencies[i])) fail("invalid coarse frequency");
    }
    uint64_t operations = 0;
    for (npy_intp symbol = 0; symbol < k.symbol_count; ++symbol) {
        const npy_intp length = k.stops[symbol] - k.starts[symbol];
        for (npy_intp frame = 0; frame < k.offset_count; ++frame) {
            const npy_intp base = k.starts[symbol] + k.offsets[frame];
            if (base < 0) fail("negative frame start");
            npy_intp epochs = k.sample_count - length + 1 - base;
            if (epochs <= 0) break;
            if (epochs > k.epoch_count) epochs = k.epoch_count;
            operations += (uint64_t)epochs * length * k.cfo_count;
        }
    }
    if (operations > UINT64_C(2300000000)) fail("fixture exceeds the capture work budget");
    const Stamp parsed = stamp();
    const size_t grid = (size_t)k.cfo_count * (size_t)k.epoch_count;
    const size_t rotated = (size_t)k.cfo_count * (size_t)max_length;
    k.scores = reserve(grid, sizeof(double), 0);
    k.accumulated = reserve(grid, sizeof(double), 1);
    k.support = reserve(k.epoch_count, sizeof(npy_int32), 1);
    k.correlation_real = reserve(k.cfo_count, sizeof(double), 0);
    k.correlation_imag = reserve(k.cfo_count, sizeof(double), 0);
    k.rotated_real = reserve(rotated, sizeof(double), 0);
    k.rotated_imag = reserve(rotated, sizeof(double), 0);
    const Stamp allocated = stamp();

    /* Preserve the production extension's pre-body overflow decision. */
    double sample_max = 0.0, template_max = 0.0;
    for (npy_intp i = 0; i < k.sample_count; ++i) {
        if (!isfinite(creal(k.samples[i])) || !isfinite(cimag(k.samples[i])))
            fail("non-finite samples");
        sample_max = fmax(sample_max, fmax(fabs(creal(k.samples[i])), fabs(cimag(k.samples[i]))));
    }
    for (uint32_t i = 0; i < dims[1]; ++i) {
        if (!isfinite(creal(k.references[i])) || !isfinite(cimag(k.references[i])))
            fail("non-finite template");
        template_max = fmax(template_max,
                            fmax(fabs(creal(k.references[i])), fabs(cimag(k.references[i]))));
    }
    double bound = 2.0 * max_length * sample_max * template_max;
    k.fast_magnitude = isfinite(bound) && bound <= sqrt(DBL_MAX / 2.0);
    const Stamp prepared = stamp();
    folded_anchor_grid_portable(&k);
    const Stamp computed = stamp();
    if (k.invalid_geometry) fail("folded grid rejected geometry");
    if (fwrite(k.scores, sizeof(double), grid, stdout) != grid || fflush(stdout))
        fail("could not emit complete score grid");
    const Stamp ended = stamp();

    struct timespec wall_resolution, cpu_resolution;
    struct rusage resources;
    if (clock_getres(CLOCK_MONOTONIC, &wall_resolution) ||
        clock_getres(CLOCK_PROCESS_CPUTIME_ID, &cpu_resolution) ||
        getrusage(RUSAGE_SELF, &resources))
        fail("clock or memory accounting is unavailable");
    fprintf(stderr, "{\"wall_clock\":\"CLOCK_MONOTONIC\","
            "\"cpu_clock\":\"CLOCK_PROCESS_CPUTIME_ID\","
            "\"wall_resolution_ns\":%" PRIu64 ",\"cpu_resolution_ns\":%" PRIu64 ","
            "\"heap_bytes\":%zu,\"process_maxrss_kib\":%ld,"
            "\"cells\":%zu,\"complex_accumulation_steps\":%" PRIu64
            ",\"fixture_tag\":\"%016" PRIx64 "\",\"stages\":{",
            ns(wall_resolution), ns(cpu_resolution), heap_bytes, resources.ru_maxrss,
            grid, operations, fixture_tag);
    elapsed("input_and_validation", begin, parsed);
    fputc(',', stderr);
    elapsed("workspace", parsed, allocated);
    fputc(',', stderr);
    elapsed("magnitude_preparation", allocated, prepared);
    fputc(',', stderr);
    elapsed("folded_grid_body", prepared, computed);
    fputc(',', stderr);
    elapsed("score_output", computed, ended);
    fputs("},\"total\":{", stderr);
    elapsed("observed", begin, ended);
    fputs("}}\n", stderr);
    return 0;
}
