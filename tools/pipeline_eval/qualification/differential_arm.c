/* Standalone replay of the unchanged differential FFTW proposal scorer. */
#define _POSIX_C_SOURCE 200809L
#include <inttypes.h>
#include <stdio.h>
#include <sys/resource.h>
#include <time.h>

#include "differential_runtime_fft.c"

enum { capacity = 16, max_repetitions = 8 };

typedef struct { double score; int epoch; } peak;
typedef struct { uint64_t cpu, wall; } stamp;

static void fail(const char *reason)
{
    fprintf(stderr, "%s\n", reason);
    exit(EXIT_FAILURE);
}

static uint64_t now(clockid_t clock)
{
    struct timespec t;
    if (clock_gettime(clock, &t)) fail("required clock is unavailable");
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

static stamp clock_pair(void) {
    return (stamp){now(CLOCK_PROCESS_CPUTIME_ID), now(CLOCK_MONOTONIC)};
}

static stamp elapsed(stamp begin, stamp end) {
    return (stamp){end.cpu - begin.cpu, end.wall - begin.wall};
}

static void *read_array(const char *path, size_t count, size_t size)
{
    void *data = malloc(count * size);
    FILE *file = fopen(path, "rb");
    if (!data || !file || fread(data, size, count, file) != count ||
        fgetc(file) != EOF || ferror(file) || fclose(file)) {
        fail("invalid replay file, byte order or fixed-size input");
    }
    return data;
}

static int order_peaks(const void *a, const void *b)
{
    const peak *left = a, *right = b;
    if (left->score > right->score) return -1;
    if (left->score < right->score) return 1;
    return left->epoch - right->epoch;
}

static int rank_centers(const double *scores, peak *scratch, int proposal[capacity])
{
    int n = 0, kept = 0;
    for (int i = 0; i < frame; ++i) {
        const double l = scores[i ? i - 1 : frame - 1];
        const double r = scores[i + 1 == frame ? 0 : i + 1];
        const double s = scores[i];
        if (!isfinite(s)) fail("nonfinite timing surface");
        if (s > 0 && s >= l && s >= r && (s > l || s > r)) scratch[n++] = (peak){s, i};
    }
    qsort(scratch, (size_t)n, sizeof(*scratch), order_peaks);
    for (int i = 0; i < n && kept < capacity; ++i) {
        int rejected = 0;
        for (int j = 0; j < kept; ++j) {
            const int d = abs(scratch[i].epoch - proposal[j]);
            if (min(d, frame - d) < 5) rejected = 1;
        }
        if (!rejected) proposal[kept++] = scratch[i].epoch;
    }
    return kept;
}

static void emit_stamp(stamp t)
{
    fprintf(stderr, "{\"cpu_ns\":%" PRIu64 ",\"wall_ns\":%" PRIu64 "}", t.cpu, t.wall);
}

int main(int argc, char **argv)
{
    const uint16_t little = 1;
    if (argc != 5 || *(const unsigned char *)&little != 1 ||
        sizeof(float) != 4 || sizeof(double) != 8 || sizeof(fftwf_complex) != 8) {
        fail("usage: differential-scout IQ.ci16 filters.c8 energies.f64 repetitions");
    }
    char *end = NULL;
    const long repetitions = strtol(argv[4], &end, 10);
    if (*end || repetitions < 1 || repetitions > max_repetitions) fail("repetition cap: 1 to 8");

    const stamp begin = clock_pair();
    int16_t *data = read_array(argv[1], times * receivers * 2u, sizeof(*data));
    fftwf_complex *filters = read_array(argv[2], 2u * branches * fft, sizeof(*filters));
    double *energy = read_array(argv[3], 2u * frame, sizeof(*energy));
    for (unsigned i = 0; i < 2u * branches * fft; ++i) {
        if (!isfinite(filters[i][0]) || !isfinite(filters[i][1])) fail("invalid filter coefficients");
    }
    for (unsigned i = 0; i < 2u * frame; ++i) {
        if (!isfinite(energy[i]) || energy[i] <= 0) fail("invalid normalization energy");
    }
    double *scores = malloc(receivers * frame * sizeof(*scores));
    peak *ranks = malloc(frame * sizeof(*ranks));
    if (!scores || !ranks) fail("could not allocate score and ranking workspace");
    const stamp loaded = clock_pair();
    scout_context *scout = leo_differential_scout_create();
    if (!scout) fail("cannot create FFTW context");
    const stamp planned = clock_pair();

    int proposals[receivers][capacity], counts[receivers];
    stamp scoring[max_repetitions], ranking[max_repetitions];
    for (long rep = 0; rep < repetitions; ++rep) {
        stamp start = clock_pair();
        leo_differential_scout(scout, data, filters, energy, scores);
        stamp scored = clock_pair();
        for (int rx = 0; rx < receivers; ++rx) {
            counts[rx] = rank_centers(scores + rx * frame, ranks, proposals[rx]);
        }
        stamp ranked = clock_pair();
        scoring[rep] = elapsed(start, scored);
        ranking[rep] = elapsed(scored, ranked);
    }
    if (fwrite(scores, sizeof(*scores), receivers * frame, stdout) != receivers * frame || fflush(stdout)) {
        fail("could not emit complete score surface");
    }
    struct rusage ru;
    if (getrusage(RUSAGE_SELF, &ru)) fail("resource accounting unavailable");
    const size_t kernel_bytes = (pairs + (branches + 1u) * fft) * sizeof(fftwf_complex) + sizeof(*scout);
    const size_t file_bytes = times * receivers * 2u * sizeof(*data)
        + 2u * branches * fft * sizeof(*filters) + 2u * frame * sizeof(*energy);
    const size_t output_bytes = receivers * frame * sizeof(*scores) + frame * sizeof(*ranks);

    fprintf(stderr, "{\"fftw_version\":\"%s\",\"peak_rss_kib\":%ld,"
            "\"kernel_workspace_bytes\":%zu,\"input_bytes\":%zu,\"output_workspace_bytes\":%zu,"
            "\"read_prepare\":", fftwf_version, ru.ru_maxrss, kernel_bytes, file_bytes, output_bytes);
    emit_stamp(elapsed(begin, loaded));
    fputs(",\"fftw_context\":", stderr);
    emit_stamp(elapsed(loaded, planned));
    fputs(",\"calls\":[", stderr);
    for (long rep = 0; rep < repetitions; ++rep) {
        if (rep) fputc(',', stderr);
        fputs("{\"scoring\":", stderr);
        emit_stamp(scoring[rep]);
        fputs(",\"ranking\":", stderr);
        emit_stamp(ranking[rep]);
        fputc('}', stderr);
    }
    fputs("],\"top_16\":[", stderr);
    for (int rx = 0; rx < receivers; ++rx) {
        fputs(rx ? ",[" : "[", stderr);
        for (int i = 0; i < counts[rx]; ++i) fprintf(stderr, "%s%d", i ? "," : "", proposals[rx][i]);
        fputc(']', stderr);
    }
    fputs("]}\n", stderr);

    leo_differential_scout_destroy(scout);
    free(ranks);
    free(scores);
    free(energy);
    free(filters);
    free(data);
    return EXIT_SUCCESS;
}
