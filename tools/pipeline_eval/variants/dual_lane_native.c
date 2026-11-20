#define _GNU_SOURCE
#include "native_hotpath.h"
#include "native_hotpath_rank.h"
#include "single_rx_glrt.h"
#include "short_window_glrt.h"

#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <time.h>

/* The one-lane export is the existing scout arithmetic with one loop index selected. */
#define leo_differential_scout_create dual_scout_create
#define leo_differential_scout_destroy dual_scout_destroy
#define leo_differential_scout dual_scout_both
#define leo_differential_scout_one_v1 dual_scout_one
#include "dual_lane_scout.c"

int leo_single_rx_glrt_center_union_short_v1(leo_single_rx_glrt *, const int16_t *,
    size_t, int32_t, leo_native_glrt_result *, leo_center_union_trace *);

typedef struct {
    int32_t cpu;
    int32_t hint;
    uint64_t cpu_ns;
    uint64_t wall_ns;
    leo_center_union_lane union_lane;
} lane_measurement;

typedef struct {
    lane_measurement lanes[2];
} dual_lane_trace;

typedef struct {
    leo_single_rx_glrt *kernel;
    scout_context *scout;
    int16_t *packed;
    double *scores;
    leo_native_glrt_result *result;
    lane_measurement measured;
    int status;
} detector_lane;

typedef struct {
    detector_lane lanes[2];
    fftwf_complex *filters;
    double *energy;
    pthread_t helper;
    pthread_mutex_t mutex;
    pthread_cond_t work;
    atomic_int busy;
    int helper_ready, mutex_ready, cond_ready;
    int pending, closed, mode;
    const int16_t *iq;
} dual_lane;

static uint64_t nanos(clockid_t clock)
{
    struct timespec value;
    if (clock_gettime(clock, &value)) return 0;
    return (uint64_t)value.tv_sec * UINT64_C(1000000000) + (uint64_t)value.tv_nsec;
}

static void detect(dual_lane *ctx, int lane, const int16_t *iq, int mode)
{
    detector_lane *own = &ctx->lanes[lane];
    const uint64_t wall = nanos(CLOCK_MONOTONIC), cpu = nanos(CLOCK_THREAD_CPUTIME_ID);
    own->measured = (lane_measurement){.cpu = sched_getcpu(), .hint = -1};
    for (size_t i = 0; i < times; ++i) {
        own->packed[2*i] = iq[4*i + 2*lane];
        own->packed[2*i + 1] = iq[4*i + 2*lane + 1];
    }
    own->status = LEO_NATIVE_GLRT_OK;
    if (mode == LEO_HOTPATH_FIFTH) {
        dual_scout_one(own->scout, iq, ctx->filters, ctx->energy, own->scores, lane);
        int hint;
        if (native_hotpath_first(own->scores, frame, &hint))
            own->status = LEO_NATIVE_GLRT_KERNEL;
        else own->measured.hint = hint;
    }
    if (own->status == LEO_NATIVE_GLRT_OK) {
        if (mode == LEO_HOTPATH_STOCK) {
            own->status = leo_single_rx_glrt_analyze_short_window_profiled(
                own->kernel, own->packed, times, own->result, NULL);
        } else {
            leo_center_union_trace trace = {0};
            own->status = leo_single_rx_glrt_center_union_short_v1(own->kernel, own->packed,
                times, own->measured.hint, own->result, &trace);
            own->measured.union_lane = trace.lanes[0];
        }
    }
    if (own->status == LEO_NATIVE_GLRT_OK &&
        (own->result->row_count != 1 || own->result->rows[0].receiver_id != 0))
        own->status = LEO_NATIVE_GLRT_KERNEL;
    own->measured.cpu_ns = nanos(CLOCK_THREAD_CPUTIME_ID) - cpu;
    own->measured.wall_ns = nanos(CLOCK_MONOTONIC) - wall;
}

static void *second_lane(void *argument)
{
    dual_lane *ctx = argument;
    pthread_mutex_lock(&ctx->mutex);
    for (;;) {
        while (!ctx->pending && !ctx->closed) pthread_cond_wait(&ctx->work, &ctx->mutex);
        if (ctx->closed) break;
        const int16_t *iq = ctx->iq;
        const int mode = ctx->mode;
        pthread_mutex_unlock(&ctx->mutex);
        detect(ctx, 1, iq, mode);
        pthread_mutex_lock(&ctx->mutex);
        ctx->pending = 0;
        pthread_cond_signal(&ctx->work);
    }
    pthread_mutex_unlock(&ctx->mutex);
    return NULL;
}

void leo_dual_lane_destroy_v1(dual_lane *ctx)
{
    if (!ctx) return;
    if (ctx->helper_ready) {
        pthread_mutex_lock(&ctx->mutex);
        ctx->closed = 1;
        pthread_cond_signal(&ctx->work);
        pthread_mutex_unlock(&ctx->mutex);
        pthread_join(ctx->helper, NULL);
    }
    if (ctx->cond_ready) pthread_cond_destroy(&ctx->work);
    if (ctx->mutex_ready) pthread_mutex_destroy(&ctx->mutex);
    for (int lane = 0; lane < receivers; ++lane) {
        detector_lane *own = &ctx->lanes[lane];
        if (own->kernel) leo_single_rx_glrt_destroy(own->kernel);
        dual_scout_destroy(own->scout);
        free(own->packed);
        free(own->scores);
        free(own->result);
    }
    free(ctx->filters);
    free(ctx->energy);
    free(ctx);
}

int leo_dual_lane_create_v1(dual_lane **out, const leo_native_glrt_complex *exact,
    const leo_native_glrt_complex *control, const float *filters, const double *energy, int helper_cpu)
{
    if (!out || !exact || !control || !filters || !energy || helper_cpu >= CPU_SETSIZE ||
        helper_cpu < -1) return LEO_NATIVE_GLRT_INVALID;
    *out = NULL;
    for (size_t i = 0; i < LEO_NATIVE_HOTPATH_FILTER_FLOATS; ++i)
        if (!isfinite(filters[i])) return LEO_NATIVE_GLRT_INVALID;
    for (size_t i = 0; i < 2u * frame; ++i)
        if (!isfinite(energy[i]) || energy[i] <= 0.0) return LEO_NATIVE_GLRT_INVALID;
    dual_lane *ctx = calloc(1, sizeof(*ctx));
    if (!ctx) return LEO_NATIVE_GLRT_NOMEM;
    atomic_init(&ctx->busy, 0);
    int status = LEO_NATIVE_GLRT_NOMEM;
    ctx->filters = malloc(LEO_NATIVE_HOTPATH_FILTER_FLOATS * sizeof(*filters));
    ctx->energy = malloc(2u * frame * sizeof(*energy));
    if (!ctx->filters || !ctx->energy) goto error;
    memcpy(ctx->filters, filters, LEO_NATIVE_HOTPATH_FILTER_FLOATS * sizeof(*filters));
    memcpy(ctx->energy, energy, 2u * frame * sizeof(*energy));
    for (int lane = 0; lane < receivers; ++lane) {
        detector_lane *own = &ctx->lanes[lane];
        own->packed = malloc(2u * times * sizeof(*own->packed));
        own->scores = malloc(frame * sizeof(*own->scores));
        own->result = malloc(sizeof(*own->result));
        own->scout = dual_scout_create();
        if (!own->packed || !own->scores || !own->result || !own->scout) goto error;
        status = leo_single_rx_glrt_create_with_mode(&own->kernel, 10000000u, exact, control,
            frame, LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH);
        if (status) goto error;
        status = LEO_NATIVE_GLRT_NOMEM;
    }
    if (helper_cpu >= 0) {
        status = LEO_NATIVE_GLRT_KERNEL;
        if (pthread_mutex_init(&ctx->mutex, NULL)) goto error;
        ctx->mutex_ready = 1;
        if (pthread_cond_init(&ctx->work, NULL)) goto error;
        ctx->cond_ready = 1;
        pthread_attr_t attr;
        if (pthread_attr_init(&attr)) goto error;
        cpu_set_t cpus;
        CPU_ZERO(&cpus);
        CPU_SET(helper_cpu, &cpus);
        int failed = pthread_attr_setaffinity_np(&attr, sizeof(cpus), &cpus) ||
            pthread_create(&ctx->helper, &attr, second_lane, ctx);
        pthread_attr_destroy(&attr);
        if (failed) goto error;
        ctx->helper_ready = 1;
    }
    *out = ctx;
    return LEO_NATIVE_GLRT_OK;
error:
    leo_dual_lane_destroy_v1(ctx);
    return status;
}

size_t leo_dual_lane_trace_size_v1(void) { return sizeof(dual_lane_trace); }

int leo_dual_lane_analyze_v1(dual_lane *ctx, int mode, const int16_t *iq, size_t count,
    leo_native_glrt_result *out, dual_lane_trace *trace)
{
    if (!ctx || !iq || !out || count != times || mode < LEO_HOTPATH_STOCK ||
        mode > LEO_HOTPATH_ABSENT) return LEO_NATIVE_GLRT_INVALID;
    int expected = 0;
    if (!atomic_compare_exchange_strong(&ctx->busy, &expected, 1)) return LEO_NATIVE_GLRT_BUSY;
    if (ctx->helper_ready) {
        pthread_mutex_lock(&ctx->mutex);
        ctx->pending = 1;
        ctx->mode = mode;
        ctx->iq = iq;
        pthread_cond_signal(&ctx->work);
        pthread_mutex_unlock(&ctx->mutex);
        detect(ctx, 0, iq, mode);
        pthread_mutex_lock(&ctx->mutex);
        while (ctx->pending) pthread_cond_wait(&ctx->work, &ctx->mutex);
        pthread_mutex_unlock(&ctx->mutex);
    } else {
        detect(ctx, 0, iq, mode);
        detect(ctx, 1, iq, mode);
    }
    int status = ctx->lanes[0].status ? ctx->lanes[0].status : ctx->lanes[1].status;
    if (!status) {
        out->row_count = receivers;
        out->detector_cpu_ms = 0;
        for (int lane = 0; lane < receivers; ++lane) {
            out->rows[lane] = ctx->lanes[lane].result->rows[0];
            out->rows[lane].receiver_id = lane;
            out->detector_cpu_ms += ctx->lanes[lane].result->detector_cpu_ms;
            if (trace) trace->lanes[lane] = ctx->lanes[lane].measured;
        }
    }
    atomic_store(&ctx->busy, 0);
    return status;
}
