#define _POSIX_C_SOURCE 200809L
#include "native_hotpath.h"
#include "native_hotpath_rank.h"
#include "short_window_glrt.h"

#include <fenv.h>
#include <stdatomic.h>
#include <time.h>

/* Retain the native lag-44 scorer intact. Both releases use the same workspace,
 * FFTW arithmetic and spectral input. The alternative is in ranking/dispatch. */
#include "differential_runtime_fft.c"

#ifdef LEO_HOTPATH_REFERENCE
typedef struct { double score; int epoch; } native_hotpath_ranked;

static int rank_compare(const void *a, const void *b)
{
    const native_hotpath_ranked *left = a, *right = b;
    if (left->score > right->score) return -1;
    if (left->score < right->score) return 1;
    return left->epoch - right->epoch;
}

static int sorted_first(const double *scores, native_hotpath_ranked *scratch, int *epoch)
{
    size_t length = 0;
    for (int i = 0; i < frame; ++i) {
        if (!isfinite(scores[i])) return -1;
        if (native_hotpath_peak(scores, frame, i))
            scratch[length++] = (native_hotpath_ranked){scores[i], i};
    }
    qsort(scratch, length, sizeof(*scratch), rank_compare);
    *epoch = length ? scratch[0].epoch : -1;
    return 0;
}
#endif

struct leo_native_hotpath {
    leo_native_glrt *glrt;
    scout_context *scout;
    fftwf_complex *filter;
    double *energy, *scores;
#ifdef LEO_HOTPATH_REFERENCE
    native_hotpath_ranked *ranking;
#endif
    atomic_int busy;
};

size_t leo_native_hotpath_trace_size_v1(void) { return sizeof(leo_native_hotpath_trace_v1); }
size_t leo_native_hotpath_result_size_v1(void) { return sizeof(leo_native_glrt_result); }

static int clock_pair(double *cpu, double *wall)
{
    struct timespec a, b;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &a) || clock_gettime(CLOCK_MONOTONIC, &b))
        return LEO_NATIVE_GLRT_KERNEL;
    *cpu = 1000.0 * (double)a.tv_sec + 1.e-6 * (double)a.tv_nsec;
    *wall = 1000.0 * (double)b.tv_sec + 1.e-6 * (double)b.tv_nsec;
    return LEO_NATIVE_GLRT_OK;
}

void leo_native_hotpath_destroy_v1(leo_native_hotpath *ctx)
{
    if (!ctx) return;
    leo_differential_scout_destroy(ctx->scout);
    if (ctx->glrt) leo_native_glrt_destroy(ctx->glrt);
    free(ctx->filter);
    free(ctx->energy);
    free(ctx->scores);
#ifdef LEO_HOTPATH_REFERENCE
    free(ctx->ranking);
#endif
    free(ctx);
}

int leo_native_hotpath_create_v1(leo_native_hotpath **out,
    const leo_native_glrt_complex *exact, const leo_native_glrt_complex *control,
    const float *filter, const double *energy)
{
    const uint16_t little = 1;
    if (!out) return LEO_NATIVE_GLRT_INVALID;
    *out = NULL;
    if (!exact || !control || (!!filter != !!energy) || *(const uint8_t *)&little != 1)
        return LEO_NATIVE_GLRT_INVALID;
    if (filter) {
        for (size_t i = 0; i < LEO_NATIVE_HOTPATH_FILTER_FLOATS; ++i)
            if (!isfinite(filter[i])) return LEO_NATIVE_GLRT_INVALID;
        for (size_t i = 0; i < 2u * frame; ++i)
            if (!isfinite(energy[i]) || energy[i] <= 0.0) return LEO_NATIVE_GLRT_INVALID;
    }
    leo_native_hotpath *ctx = calloc(1, sizeof(*ctx));
    if (!ctx) return LEO_NATIVE_GLRT_NOMEM;
    atomic_init(&ctx->busy, 0);
    int status = leo_native_glrt_create_with_mode(&ctx->glrt, 10000000u, exact, control,
        frame, LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH);
    if (!status && filter) {
        ctx->scout = leo_differential_scout_create();
        ctx->filter = malloc(LEO_NATIVE_HOTPATH_FILTER_FLOATS * sizeof(*filter));
        ctx->energy = malloc(2u * frame * sizeof(*energy));
        ctx->scores = malloc(2u * frame * sizeof(*ctx->scores));
        if (!ctx->scout || !ctx->filter || !ctx->energy || !ctx->scores)
            status = LEO_NATIVE_GLRT_NOMEM;
#ifdef LEO_HOTPATH_REFERENCE
        ctx->ranking = malloc(frame * sizeof(*ctx->ranking));
        if (!ctx->ranking) status = LEO_NATIVE_GLRT_NOMEM;
#endif
        if (!status) {
            memcpy(ctx->filter, filter, LEO_NATIVE_HOTPATH_FILTER_FLOATS * sizeof(*filter));
            memcpy(ctx->energy, energy, 2u * frame * sizeof(*energy));
        }
    }
    if (status) leo_native_hotpath_destroy_v1(ctx);
    else *out = ctx;
    return status;
}

int leo_native_hotpath_analyze_v1(leo_native_hotpath *ctx, int mode,
    const int16_t *iq, size_t count, leo_native_glrt_result *out,
    leo_native_hotpath_trace_v1 *trace)
{
    if (!ctx || !iq || !out || count != times || mode < LEO_HOTPATH_STOCK ||
        mode > LEO_HOTPATH_ABSENT || (mode == LEO_HOTPATH_FIFTH && !ctx->scout) ||
        fegetround() != FE_TONEAREST) return LEO_NATIVE_GLRT_INVALID;
    int expected = 0;
    if (!atomic_compare_exchange_strong(&ctx->busy, &expected, 1)) return LEO_NATIVE_GLRT_BUSY;
    leo_native_hotpath_trace_v1 result = {.hints = {-1, -1}};
    double a = 0, b = 0, c = 0, d = 0;
    int status = LEO_NATIVE_GLRT_OK;
    if (mode == LEO_HOTPATH_FIFTH) {
        if (trace && (status = clock_pair(&a, &b))) goto done;
        leo_differential_scout(ctx->scout, iq, ctx->filter, ctx->energy, ctx->scores);
        if (trace && (status = clock_pair(&c, &d))) goto done;
        result.scout_cpu_ms = c - a;
        result.scout_wall_ms = d - b;
        for (int lane = 0; lane < receivers; ++lane) {
            const double *scores = ctx->scores + lane * frame;
            int epoch;
#ifdef LEO_HOTPATH_REFERENCE
            status = sorted_first(scores, ctx->ranking, &epoch);
#else
            status = native_hotpath_first(scores, frame, &epoch);
#endif
            if (status) { status = LEO_NATIVE_GLRT_KERNEL; goto done; }
            result.hints[lane] = epoch;
        }
        if (trace && (status = clock_pair(&a, &b))) goto done;
        result.rank_cpu_ms = a - c;
        result.rank_wall_ms = b - d;
    }
    if (trace && (status = clock_pair(&a, &b))) goto done;
    if (mode == LEO_HOTPATH_STOCK)
        status = leo_native_glrt_analyze_short_window_profiled(ctx->glrt, iq, count, out,
            trace ? &result.stock_profile : NULL);
    else
        status = leo_native_glrt_analyze_center_union_v1(ctx->glrt, iq, count, result.hints,
            out, &result.union_trace);
    if (!status && trace && !(status = clock_pair(&c, &d))) {
        result.detector_cpu_ms = c - a;
        result.detector_wall_ms = d - b;
        *trace = result;
    }
done:
    atomic_store(&ctx->busy, 0);
    return status;
}
