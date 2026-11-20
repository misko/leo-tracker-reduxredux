/* Warm chronological offline dual-RX replay of the sealed stock and fifth detector. */
#include <stdbool.h>
#define LEO_NATIVE_GLRT_SHORT_WINDOW_CLI 1
#define main leo_prior_ordinary_main
#include "native_glrt_cli.c"
#undef main
#undef _POSIX_C_SOURCE

#define main leo_prior_differential_main
#include "differential_arm.c"
#undef main
#include "center_union.h"

static void print_stamp(stamp clock)
{
    printf("{\"cpu_ns\":%" PRIu64 ",\"wall_ns\":%" PRIu64 "}", clock.cpu, clock.wall);
}

static void read_visit(const char *path, int16_t *destination)
{
    FILE *f = fopen(path, "rb");
    if (!f) fail("opening packed dual CI16 visit");
    const size_t count = (size_t)times * receivers * 2u;
    const bool good = fread(destination, sizeof(*destination), count, f) == count &&
        fgetc(f) == EOF && !ferror(f);
    if (fclose(f) || !good) fail("unexpected packed dual CI16 size or read failure");
}

int main(int argc, char **argv)
{
    const uint16_t little = 1;
    if (argc < 8 || argc > 46 || *(const uint8_t *)&little != 1 || DBL_MANT_DIG != 53 ||
        sizeof(int16_t) != 2 || sizeof(leo_native_glrt_complex) != 16 ||
        sizeof(fftwf_complex) != 8) {
        fail("usage: arm-receiver stock|fifth exact.c16 control.c16 filters.c8 energies.f64 repeats visit.ci16 ...");
    }
    const bool use_fifth = !strcmp(argv[1], "fifth");
    if (!use_fifth && strcmp(argv[1], "stock")) fail("unsupported mode");
    uint32_t repeats;
    if (number(argv[6], &repeats) || repeats < 1 || repeats > 3) fail("repeats must be 1–3");
    const stamp start = clock_pair();
    leo_native_glrt_complex *exact = read_array(argv[2], frame, sizeof(*exact));
    leo_native_glrt_complex *control = read_array(argv[3], frame, sizeof(*control));
    int16_t *samples = malloc((size_t)times * receivers * 2u * sizeof(*samples));
    if (!samples) fail("allocating one packed dual CI16 visit");
    fftwf_complex *filters = NULL;
    double *energy = NULL, *scores = NULL;
    peak *ranking = NULL;
    if (use_fifth) {
        filters = read_array(argv[4], 2u * branches * fft, sizeof(*filters));
        energy = read_array(argv[5], 2u * frame, sizeof(*energy));
        scores = calloc(receivers * frame, sizeof(*scores));
        ranking = malloc(frame * sizeof(*ranking));
        if (!scores || !ranking) fail("allocating scout ranking");
        for (unsigned i = 0; i < 2u * branches * fft; ++i)
            if (!isfinite(filters[i][0]) || !isfinite(filters[i][1])) fail("nonfinite scout filter");
        for (unsigned i = 0; i < 2u * frame; ++i)
            if (!isfinite(energy[i]) || energy[i] <= 0) fail("invalid scout energy");
    }
    const stamp loaded = clock_pair();
    leo_native_glrt *detector = NULL;
    if (leo_native_glrt_create_with_mode(&detector, 10000000u, exact, control, frame,
            LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH)) fail("initializing stock GLRT");
    const stamp ready = clock_pair();
    scout_context *scout = use_fifth ? leo_differential_scout_create() : NULL;
    if (use_fifth && !scout) fail("initializing differential FFTW scout");
    const stamp scout_ready = clock_pair();
    printf("{\"kind\":\"setup\",\"mode\":\"%s\",\"template_read\":", argv[1]);
    print_stamp(elapsed(start, loaded));
    fputs(",\"detector_context\":", stdout); print_stamp(elapsed(loaded, ready));
    fputs(",\"scout_context\":", stdout); print_stamp(elapsed(ready, scout_ready));
    printf(",\"visits_per_repeat\":%d,\"repetitions\":%u}\n", argc - 7, repeats);
    for (unsigned repeat = 0; repeat < repeats; ++repeat) {
        for (int i = 7; i < argc; ++i) {
            const stamp entered = clock_pair();
            read_visit(argv[i], samples);
            const stamp buffered = clock_pair();
            int chosen[receivers][capacity], length[receivers] = {0};
            int32_t hints[receivers] = {-1, -1};
            if (scout) {
                leo_differential_scout(scout, samples, filters, energy, scores);
                for (int rx = 0; rx < receivers; ++rx) {
                    length[rx] = rank_centers(scores + rx * frame, ranking, chosen[rx]);
                    if (length[rx]) hints[rx] = chosen[rx][0];
                }
            }
            const stamp proposed = clock_pair();
            leo_native_glrt_result output = {0};
            leo_center_union_trace trace = {0};
            const int status = use_fifth ? leo_native_glrt_analyze_center_union_v1(
                detector, samples, times, hints, &output, &trace) :
                leo_native_glrt_analyze_short_window(detector, samples, times, &output);
            const stamp finished = clock_pair();
            if (status || output.row_count != 2) fail("dual RX detector failed");
            printf("{\"kind\":\"visit\",\"index\":%d,\"repeat\":%u,\"read\":", i - 7, repeat);
            print_stamp(elapsed(entered, buffered));
            fputs(",\"scout\":", stdout); print_stamp(elapsed(buffered, proposed));
            fputs(",\"detector\":", stdout); print_stamp(elapsed(proposed, finished));
            fputs(",\"top16\":[", stdout);
            for (int rx = 0; rx < receivers; ++rx) {
                fputs(rx ? ",[" : "[", stdout);
                for (int j = 0; j < length[rx]; ++j) printf("%s%d", j ? "," : "", chosen[rx][j]);
                putchar(']');
            }
            fputs("],\"added_epochs\":[", stdout);
            printf("%d,%d],\"rows\":[", trace.lanes[0].added_epochs, trace.lanes[1].added_epochs);
            row(&output.rows[0]); putchar(','); row(&output.rows[1]);
            fputs("]}\n", stdout);
        }
    }
    fflush(stdout);
    leo_differential_scout_destroy(scout);
    if (leo_native_glrt_destroy(detector)) fail("destroying stock GLRT");
    free(ranking); free(scores); free(energy); free(filters);
    free(samples); free(control); free(exact);
    return EXIT_SUCCESS;
}
