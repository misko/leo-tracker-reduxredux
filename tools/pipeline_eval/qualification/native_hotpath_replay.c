/* Offline JSON inspection of the typed native detector. */
#define LEO_NATIVE_GLRT_SHORT_WINDOW_CLI 1
#define main leo_previous_cli_main
#include "native_glrt_cli.c"
#undef main
#include "native_hotpath.h"

int main(int argc, char **argv)
{
    if (argc != 7) {
        fputs("usage: native-hotpath stock|fifth|absent IQ exact control filter energy\n", stderr);
        return 2;
    }
    const char *modes[] = {"stock", "fifth", "absent"};
    int mode = 0;
    while (mode < 3 && strcmp(modes[mode], argv[1])) ++mode;
    if (mode == 3) return 2;
    int16_t *iq = read_exact(argv[2], 4u * LEO_NATIVE_HOTPATH_TIMES, sizeof(*iq));
    leo_native_glrt_complex *exact = read_exact(argv[3], LEO_NATIVE_HOTPATH_FRAME, sizeof(*exact));
    leo_native_glrt_complex *control = read_exact(argv[4], LEO_NATIVE_HOTPATH_FRAME, sizeof(*control));
    float *filter = mode == LEO_HOTPATH_FIFTH
        ? read_exact(argv[5], LEO_NATIVE_HOTPATH_FILTER_FLOATS, sizeof(*filter)) : NULL;
    double *energy = mode == LEO_HOTPATH_FIFTH
        ? read_exact(argv[6], 2u * LEO_NATIVE_HOTPATH_FRAME, sizeof(*energy)) : NULL;
    leo_native_hotpath *ctx = NULL;
    leo_native_glrt_result *out = calloc(1, sizeof(*out));
    leo_native_hotpath_trace_v1 trace;
    int status = LEO_NATIVE_GLRT_INVALID;
    if (iq && exact && control && out && (mode != LEO_HOTPATH_FIFTH || (filter && energy))) {
        status = leo_native_hotpath_create_v1(&ctx, exact, control, filter, energy);
        if (!status) status = leo_native_hotpath_analyze_v1(ctx, mode, iq,
            LEO_NATIVE_HOTPATH_TIMES, out, &trace);
    }
    if (status) fprintf(stderr, "offline detector failed: %s\n", leo_native_glrt_status_string(status));
    else {
        printf("{\"hints\":[%d,%d],\"rows\":[", trace.hints[0], trace.hints[1]);
        for (size_t i = 0; i < out->row_count; ++i) {
            if (i) putchar(',');
            row(&out->rows[i]);
        }
        puts("]}");
    }
    leo_native_hotpath_destroy_v1(ctx);
    free(out); free(iq); free(exact); free(control); free(filter); free(energy);
    return status ? 1 : 0;
}
