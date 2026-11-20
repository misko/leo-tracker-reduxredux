#define _POSIX_C_SOURCE 200809L
#include "../variants/portable_verifier.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

_Static_assert(sizeof(PortableVerifierSeed) == 24 && sizeof(PortableVerifierResult) == 896,
               "unexpected evidence ABI");

static void require(int ok, const char *message) {
    if (!ok) { fprintf(stderr, "%s\n", message); exit(2); }
}

static uint64_t now(clockid_t clock) {
    struct timespec t;
    require(clock_gettime(clock, &t) == 0, "clock unavailable");
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

static void take(FILE *stream, void *data, size_t bytes) {
    require(fread(data, 1, bytes, stream) == bytes, "truncated authenticated verifier fixture");
}

static long memory_peak(void) {
    FILE *status = fopen("/proc/self/status", "r");
    if (!status) return -1;
    char line[128];
    long kib = -1;
    while (fgets(line, sizeof(line), status)) if (sscanf(line, "VmHWM: %ld kB", &kib) == 1) break;
    fclose(status);
    return kib;
}

static int self_test(void) {
    double offset, curve;
    const double flat[] = {0,0,0,0,0}, tied[] = {0.1,0.1,0.2,0.2,0.1};
    const double bad[] = {0,0,-0.1,0,0}, end[] = {1,0.5,0.2,0.2,0.2};
    require(portable_verifier_fractional_peak(flat,&offset,&curve) == 0, "flat peak must fail closed");
    require(portable_verifier_fractional_peak(end,&offset,&curve) == 0, "unbracketed endpoint");
    require(portable_verifier_fractional_peak(bad,&offset,&curve) == -1, "negative GLRT surface accepted");
    require(portable_verifier_fractional_peak(tied,&offset,&curve) == 1 && offset == 0.5 && curve < 0,
            "first tied log-peak must retain circular ordering");
    size_t iq_size = 4 * PORTABLE_FINE_SAMPLES * sizeof(int16_t);
    int16_t *zero = calloc(1, iq_size);
    PortableFineComplex *template = calloc(PORTABLE_FINE_EPOCHS, sizeof(*template));
    require(zero && template, "self-test allocation failed");
    for (int i = 0; i < PORTABLE_FINE_EPOCHS; ++i) template[i].r = 1;
    PortableVerifier *w = portable_verifier_create(template, template);
    PortableVerifierSeed seed = {0, 161, -40000, -40000};
    PortableVerifierResult result;
    require(w && portable_verifier_load(w, zero, 1) == 0 &&
            portable_verifier_acquire(w, &seed, 1, 0, -800000, 800000, &result) == 0 &&
            portable_verifier_glrt(w, seed.epoch, &result) == 0, "zero-input replay failed");
    require(result.acquired_hz == 0 && result.integer_exact == 0 && result.integer_control == 0 &&
            result.flags == (PORTABLE_VERIFIER_FINE_GUARD | PORTABLE_VERIFIER_CONDITIONED_TIE),
            "zero input produced a resolved or positive score");
    portable_verifier_free(w);
    free(template);
    free(zero);
    puts("standalone verifier sentinels passed");
    return 0;
}

int main(int argc, char **argv) {
    require(argc == 2, "usage: portable-verifier capture.bin | --self-test");
    if (strcmp(argv[1], "--self-test") == 0) return self_test();
    const uint32_t one = 1;
    require(*(const unsigned char *)&one == 1, "evidence ABI is little-endian");
    uint64_t start = now(CLOCK_MONOTONIC), cpu = now(CLOCK_PROCESS_CPUTIME_ID);
    FILE *stream = fopen(argv[1], "rb");
    require(stream != NULL, "cannot open verified fixture");
    char magic[8];
    uint32_t visits;
    take(stream, magic, sizeof(magic));
    take(stream, &visits, sizeof(visits));
    require(memcmp(magic, "LEOVRF01", 8) == 0 && visits > 0 && visits <= 32,
            "incorrect portable verifier fixture ABI");
    const size_t iq_size = 4 * PORTABLE_FINE_SAMPLES * sizeof(int16_t);
    const size_t template_size = PORTABLE_FINE_EPOCHS * sizeof(PortableFineComplex);
    PortableFineComplex *templates = malloc(2 * template_size);
    int16_t *iq = malloc(iq_size);
    require(templates && iq, "could not allocate bounded verifier input buffers");
    take(stream, templates, 2 * template_size);
    uint64_t mark = now(CLOCK_PROCESS_CPUTIME_ID);
    PortableVerifier *verifier = portable_verifier_create(templates, templates + PORTABLE_FINE_EPOCHS);
    require(verifier != NULL, "could not initialize portable verifier");
    uint64_t setup = now(CLOCK_PROCESS_CPUTIME_ID) - mark, load = 0, acquire = 0, glrt = 0;
    unsigned count = 0, total_groups = 0;
    for (uint32_t v = 0; v < visits; ++v) {
        uint32_t visit, groups;
        take(stream, &visit, sizeof(visit));
        take(stream, &groups, sizeof(groups));
        require(groups >= 2 && groups <= 4, "incorrect group count");
        take(stream, iq, iq_size);
        unsigned loaded = 2;
        for (uint32_t g = 0; g < groups; ++g) {
            uint32_t lane, num;
            double bounds[3];
            take(stream, &lane, sizeof(lane));
            take(stream, &num, sizeof(num));
            take(stream, bounds, sizeof(bounds));
            require(lane < 2 && num && num <= PORTABLE_VERIFIER_MAX_SEEDS,
                    "invalid physical lane or candidate count");
            PortableVerifierSeed seeds[PORTABLE_VERIFIER_MAX_SEEDS];
            PortableVerifierResult results[PORTABLE_VERIFIER_MAX_SEEDS];
            take(stream, seeds, num*sizeof(*seeds));
            if (lane != loaded) {
                mark = now(CLOCK_PROCESS_CPUTIME_ID);
                require(portable_verifier_load(verifier, iq, lane) == 0, "cannot load lane");
                load += now(CLOCK_PROCESS_CPUTIME_ID) - mark;
                loaded = lane;
            }
            mark = now(CLOCK_PROCESS_CPUTIME_ID);
            require(portable_verifier_acquire(verifier, seeds, num, bounds[0], bounds[1], bounds[2],
                                             results) == 0, "unsupported acquisition geometry");
            acquire += now(CLOCK_PROCESS_CPUTIME_ID) - mark;
            mark = now(CLOCK_PROCESS_CPUTIME_ID);
            for (uint32_t i = 0; i < num; ++i)
                require(portable_verifier_glrt(verifier, seeds[results[i].seed_index].epoch,
                                               &results[i]) == 0, "GLRT refinement failed");
            glrt += now(CLOCK_PROCESS_CPUTIME_ID) - mark;
            require(fwrite(results, sizeof(*results), num, stdout) == num, "cannot write results");
            count += num;
            ++total_groups;
        }
    }
    require(fgetc(stream) == EOF && !ferror(stream) && fflush(stdout) == 0,
            "verifier input or output did not terminate cleanly");
    struct rusage usage;
    require(getrusage(RUSAGE_SELF, &usage) == 0, "cannot measure process RSS");
    fprintf(stderr,
            "{\"visits\":%u,\"groups\":%u,\"candidates\":%u,\"workspace_bytes\":%zu,"
            "\"input_alloc_bytes\":%zu,\"setup_cpu_ns\":%" PRIu64 ",\"load_cpu_ns\":%" PRIu64 ","
            "\"acquire_cpu_ns\":%" PRIu64 ",\"glrt_cpu_ns\":%" PRIu64 ",\"process_cpu_ns\":%" PRIu64 ","
            "\"elapsed_ns\":%" PRIu64 ",\"peak_rss_kib\":%ld,\"rusage_maxrss_kib\":%ld}\n",
            visits,total_groups,count,portable_verifier_workspace_bytes(),iq_size+2*template_size,
            setup,load,acquire,glrt,now(CLOCK_PROCESS_CPUTIME_ID)-cpu,now(CLOCK_MONOTONIC)-start,
            memory_peak(),usage.ru_maxrss);
    fclose(stream);
    portable_verifier_free(verifier);
    free(iq);
    free(templates);
    return 0;
}
