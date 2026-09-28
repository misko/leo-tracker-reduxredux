/* Let immutable probe.c establish its feature-test macros in normal builds. */
#ifndef RAM_PIPELINE_STANDALONE_TEST
#define main original_probe_main
#include "probe.c"
#undef main
#else
#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif

#include <errno.h>
#include <inttypes.h>
#include <math.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

/*
 * Saved-IQ RAM pipeline benchmark. Normal builds find immutable probe.c through
 * the selected source tree's include path; standalone builds exclude all DSP.
 */

#define MAX_JOBS 500U
#define MAX_CASES 32U
#define MAX_CONTEXTS 4U
#define MAX_RING_SLOTS 8U
#define MAX_OWNED_BYTES (160U * 1024U * 1024U)
#define CAPTURE_MS 120.0
#define CHUNK_MS 10.0
#define CHUNK_COUNT 12U

typedef enum {
    SLOT_FREE = 0,
    SLOT_FILLING = 1,
    SLOT_READY = 2,
    SLOT_PROCESSING = 3
} slot_state;

typedef struct {
    slot_state state;
    unsigned job_id;
    unsigned case_index;
    uint64_t generation;
    uint8_t *data;
} ring_slot;

typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t ready_cond;
    ring_slot *slots;
    unsigned slot_count;
    size_t slot_bytes;
    unsigned occupied;
    unsigned ready;
    unsigned occupied_highwater;
    unsigned ready_highwater;
    unsigned queue_full_overruns;
    int producer_done;
} bounded_ring;

static int ring_init(bounded_ring *ring, unsigned slots, size_t slot_bytes)
{
    memset(ring, 0, sizeof(*ring));
    if (slots < 1 || slots > MAX_RING_SLOTS || slot_bytes == 0)
        return -1;
    ring->slots = calloc(slots, sizeof(*ring->slots));
    if (!ring->slots)
        return -1;
    ring->slot_count = slots;
    ring->slot_bytes = slot_bytes;
    for (unsigned k = 0; k < slots; ++k) {
        ring->slots[k].data = malloc(slot_bytes);
        if (!ring->slots[k].data)
            goto fail;
        /* Allocate and fault every ring page before the measured interval. */
        memset(ring->slots[k].data, 0, slot_bytes);
    }
    if (pthread_mutex_init(&ring->mutex, NULL))
        goto fail;
    if (pthread_cond_init(&ring->ready_cond, NULL)) {
        pthread_mutex_destroy(&ring->mutex);
        goto fail;
    }
    return 0;
fail:
    for (unsigned k = 0; k < slots; ++k)
        free(ring->slots[k].data);
    free(ring->slots);
    memset(ring, 0, sizeof(*ring));
    return -1;
}

static void ring_destroy(bounded_ring *ring)
{
    if (!ring->slots)
        return;
    pthread_cond_destroy(&ring->ready_cond);
    pthread_mutex_destroy(&ring->mutex);
    for (unsigned k = 0; k < ring->slot_count; ++k)
        free(ring->slots[k].data);
    free(ring->slots);
    memset(ring, 0, sizeof(*ring));
}

/* Reserve never waits.  Full means this arrival is irreversibly dropped. */
static int ring_reserve(bounded_ring *ring, unsigned job_id,
                        unsigned case_index, unsigned *slot_index,
                        uint64_t *generation)
{
    int found = -1;
    pthread_mutex_lock(&ring->mutex);
    for (unsigned k = 0; k < ring->slot_count; ++k) {
        if (ring->slots[k].state == SLOT_FREE) {
            found = (int)k;
            break;
        }
    }
    if (found < 0) {
        ++ring->queue_full_overruns;
    } else {
        ring_slot *slot = &ring->slots[found];
        slot->state = SLOT_FILLING;
        slot->job_id = job_id;
        slot->case_index = case_index;
        ++slot->generation;
        ++ring->occupied;
        if (ring->occupied > ring->occupied_highwater)
            ring->occupied_highwater = ring->occupied;
        *slot_index = (unsigned)found;
        *generation = slot->generation;
    }
    pthread_mutex_unlock(&ring->mutex);
    return found < 0 ? -1 : 0;
}

static int ring_publish(bounded_ring *ring, unsigned slot_index,
                        unsigned job_id, uint64_t generation)
{
    int rc = 0;
    pthread_mutex_lock(&ring->mutex);
    if (slot_index >= ring->slot_count ||
        ring->slots[slot_index].state != SLOT_FILLING ||
        ring->slots[slot_index].job_id != job_id ||
        ring->slots[slot_index].generation != generation) {
        rc = -1;
    } else {
        ring->slots[slot_index].state = SLOT_READY;
        ++ring->ready;
        if (ring->ready > ring->ready_highwater)
            ring->ready_highwater = ring->ready;
        pthread_cond_signal(&ring->ready_cond);
    }
    pthread_mutex_unlock(&ring->mutex);
    return rc;
}

/* Select the oldest published job, independent of physical slot reuse. */
static int ring_take_ready(bounded_ring *ring, unsigned *slot_index,
                           unsigned *job_id, unsigned *case_index,
                           uint64_t *generation)
{
    int found = -1;
    unsigned oldest = UINT32_MAX;
    pthread_mutex_lock(&ring->mutex);
    for (;;) {
        for (unsigned k = 0; k < ring->slot_count; ++k) {
            if (ring->slots[k].state == SLOT_READY &&
                (found < 0 || ring->slots[k].job_id < oldest)) {
                found = (int)k;
                oldest = ring->slots[k].job_id;
            }
        }
        if (found >= 0 || ring->producer_done)
            break;
        pthread_cond_wait(&ring->ready_cond, &ring->mutex);
    }
    if (found >= 0) {
        ring_slot *slot = &ring->slots[found];
        slot->state = SLOT_PROCESSING;
        --ring->ready;
        *slot_index = (unsigned)found;
        *job_id = slot->job_id;
        *case_index = slot->case_index;
        *generation = slot->generation;
    }
    pthread_mutex_unlock(&ring->mutex);
    return found < 0 ? 0 : 1;
}

static int ring_release(bounded_ring *ring, unsigned slot_index,
                        unsigned job_id, uint64_t generation)
{
    int rc = 0;
    pthread_mutex_lock(&ring->mutex);
    if (slot_index >= ring->slot_count ||
        ring->slots[slot_index].state != SLOT_PROCESSING ||
        ring->slots[slot_index].job_id != job_id ||
        ring->slots[slot_index].generation != generation) {
        rc = -1;
    } else {
        ring->slots[slot_index].state = SLOT_FREE;
        --ring->occupied;
    }
    pthread_mutex_unlock(&ring->mutex);
    return rc;
}

static void ring_finish_producer(bounded_ring *ring)
{
    pthread_mutex_lock(&ring->mutex);
    ring->producer_done = 1;
    pthread_cond_broadcast(&ring->ready_cond);
    pthread_mutex_unlock(&ring->mutex);
}

static int ring_self_test(void)
{
    bounded_ring ring;
    unsigned a, b, j, c;
    uint64_t ga, gb, g;
    if (ring_init(&ring, 2, 64))
        return 1;
    if (ring_reserve(&ring, 7, 1, &a, &ga) ||
        ring_reserve(&ring, 8, 2, &b, &gb) || a == b)
        return 1;
    memset(ring.slots[a].data, 0x71, ring.slot_bytes);
    memset(ring.slots[b].data, 0x82, ring.slot_bytes);
    unsigned rejected_slot = 99;
    uint64_t rejected_generation = 99;
    if (ring_reserve(&ring, 9, 3, &rejected_slot,
                     &rejected_generation) == 0 ||
        ring.queue_full_overruns != 1)
        return 1;
    if (ring_publish(&ring, b, 8, gb) || ring_publish(&ring, a, 7, ga))
        return 1;
    unsigned taken;
    if (ring_take_ready(&ring, &taken, &j, &c, &g) != 1 ||
        taken != a || j != 7 || c != 1 || g != ga ||
        ring.slots[taken].data[0] != 0x71 ||
        ring.slots[taken].data[63] != 0x71)
        return 1;
    if (ring_release(&ring, taken, j, g))
        return 1;
    uint64_t ga2;
    if (ring_reserve(&ring, 10, 4, &a, &ga2) || ga2 == ga)
        return 1;
    memset(ring.slots[a].data, 0xa4, ring.slot_bytes);
    if (ring_publish(&ring, a, 10, ga2))
        return 1;
    if (ring_take_ready(&ring, &taken, &j, &c, &g) != 1 ||
        j != 8 || ring.slots[taken].data[0] != 0x82)
        return 1;
    if (ring_release(&ring, taken, j, g))
        return 1;
    if (ring_take_ready(&ring, &taken, &j, &c, &g) != 1 ||
        j != 10 || c != 4 || g != ga2 ||
        ring.slots[taken].data[0] != 0xa4 ||
        ring.slots[taken].data[63] != 0xa4)
        return 1;
    if (ring_release(&ring, taken, j, g))
        return 1;
    ring_finish_producer(&ring);
    if (ring_take_ready(&ring, &taken, &j, &c, &g) != 0 ||
        ring.occupied != 0 || ring.ready != 0 ||
        ring.occupied_highwater != 2 || ring.ready_highwater != 2)
        return 1;
    printf("{\"schema\":\"org.leo.research.ram-ring-self-test/v1\","
           "\"status\":\"pass\",\"forced_overruns\":%u,"
           "\"occupied_highwater\":%u,\"ready_highwater\":%u,"
           "\"generation_reuse_checked\":true,"
           "\"fresh_payload_checked\":true}\n",
           ring.queue_full_overruns, ring.occupied_highwater,
           ring.ready_highwater);
    ring_destroy(&ring);
    return 0;
}

#ifdef RAM_PIPELINE_STANDALONE_TEST
int main(int argc, char **argv)
{
    if (argc != 2 || strcmp(argv[1], "--ring-self-test")) {
        fprintf(stderr, "usage: %s --ring-self-test\n", argv[0]);
        return 2;
    }
    return ring_self_test();
}
#else

typedef struct {
    uint8_t *data;
    size_t size;
} owned_file;

typedef struct {
    owned_file raw;
    char id[160];
    unsigned context;
    uint8_t first[16];
    uint8_t last[16];
    uint64_t full_signature;
} input_case;

typedef struct {
    char exact_path[512];
    char control_path[512];
    owned_file exact;
    owned_file control;
    probe_work work;
} input_context;

typedef enum {
    JOB_PENDING = 0,
    JOB_PROCESSED = 1,
    JOB_DROPPED = 2,
    JOB_FAILED = 3
} job_status;

typedef struct {
    job_status status;
    unsigned case_index;
    unsigned slot_index;
    uint64_t slot_generation;
    double arrival_ms;
    double ready_ms;
    double start_ms;
    double end_ms;
    double consumer_cpu_ms;
    double packing_cpu_ms[2];
    double packing_wall_ms[2];
    double detector_process_cpu_ms[2];
    double detector_wall_ms[2];
    leo_presence_dwell_result dwell[2];
    leo_presence_rank_screens screens[2];
    int run_rc;
} job_result;

typedef struct {
    unsigned long long user;
    unsigned long long nice;
    unsigned long long system;
    unsigned long long idle;
    unsigned long long iowait;
    unsigned long long irq;
    unsigned long long softirq;
    unsigned long long steal;
    int valid;
} cpu_stat;

typedef struct {
    bounded_ring *ring;
    input_case *cases;
    unsigned case_count;
    job_result *results;
    const double *offsets;
    unsigned jobs;
    double epoch_ms;
    size_t raw_bytes;
    int core;
    int consumer_core;
    int stat_other_core;
    uint8_t *discard;
    unsigned discard_last_case;
    int discard_valid;
    pthread_mutex_t start_mutex;
    pthread_cond_t start_cond;
    int start_released;
    double cpu_ms;
    double end_ms;
    cpu_stat consumer_stat_end;
    cpu_stat other_stat_end;
    double max_chunk_late_ms;
    unsigned late_chunks;
    unsigned produced;
    unsigned dropped;
    int fatal;
} producer_args;

static double local_millis(clockid_t id)
{
    struct timespec value;
    if (clock_gettime(id, &value))
        return NAN;
    return 1000.0 * (double)value.tv_sec + 1e-6 * (double)value.tv_nsec;
}

static int sleep_until_ms(double when_ms)
{
    struct timespec when;
    when.tv_sec = (time_t)(when_ms / 1000.0);
    when.tv_nsec = (long)(fmod(when_ms, 1000.0) * 1000000.0);
    int rc;
    do {
        rc = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &when, NULL);
    } while (rc == EINTR);
    return rc;
}

static int pin_current_thread(int core)
{
    cpu_set_t selected, actual;
    if (core < 0 || core >= CPU_SETSIZE)
        return -1;
    CPU_ZERO(&selected);
    CPU_SET(core, &selected);
    if (pthread_setaffinity_np(pthread_self(), sizeof(selected), &selected) ||
        pthread_getaffinity_np(pthread_self(), sizeof(actual), &actual) ||
        CPU_COUNT(&actual) != 1 || !CPU_ISSET(core, &actual))
        return -1;
    return 0;
}

static int parse_unsigned(const char *text, unsigned *out)
{
    char *end = NULL;
    errno = 0;
    unsigned long value = strtoul(text, &end, 10);
    if (errno || !end || *end || value > UINT32_MAX)
        return -1;
    *out = (unsigned)value;
    return 0;
}

static int parse_int(const char *text, int *out)
{
    char *end = NULL;
    errno = 0;
    long value = strtol(text, &end, 10);
    if (errno || !end || *end || value < INT32_MIN || value > INT32_MAX)
        return -1;
    *out = (int)value;
    return 0;
}

static int valid_id(const char *id)
{
    if (!*id)
        return 0;
    for (const unsigned char *p = (const unsigned char *)id; *p; ++p) {
        if (!( (*p >= 'a' && *p <= 'z') || (*p >= 'A' && *p <= 'Z') ||
               (*p >= '0' && *p <= '9') || *p == '-' || *p == '_' ||
               *p == '.' ))
            return 0;
    }
    return 1;
}

static int load_owned(const char *path, owned_file *out, size_t *owned_bytes)
{
    struct stat st;
    FILE *file = NULL;
    memset(out, 0, sizeof(*out));
    if (stat(path, &st) || st.st_size <= 0 ||
        (uintmax_t)st.st_size > SIZE_MAX)
        return -1;
    size_t size = (size_t)st.st_size;
    if (size > MAX_OWNED_BYTES || *owned_bytes > MAX_OWNED_BYTES - size)
        return -1;
    out->data = malloc(size);
    if (!out->data)
        return -1;
    file = fopen(path, "rb");
    if (!file || fread(out->data, 1, size, file) != size ||
        fgetc(file) != EOF) {
        if (file)
            fclose(file);
        free(out->data);
        memset(out, 0, sizeof(*out));
        return -1;
    }
    fclose(file);
    out->size = size;
    *owned_bytes += size;
    return 0;
}

static int read_cpu_stat(int core, cpu_stat *out)
{
    char wanted[32], line[512];
    snprintf(wanted, sizeof(wanted), "cpu%d", core);
    FILE *file = fopen("/proc/stat", "r");
    if (!file)
        return -1;
    memset(out, 0, sizeof(*out));
    while (fgets(line, sizeof(line), file)) {
        char label[32];
        cpu_stat value = {0};
        int fields = sscanf(line,
            "%31s %llu %llu %llu %llu %llu %llu %llu %llu",
            label, &value.user, &value.nice, &value.system, &value.idle,
            &value.iowait, &value.irq, &value.softirq, &value.steal);
        if (fields == 9 && !strcmp(label, wanted)) {
            value.valid = 1;
            *out = value;
            fclose(file);
            return 0;
        }
    }
    fclose(file);
    return -1;
}

static uint64_t full_signature(const uint8_t *data, size_t size)
{
    uint64_t hash = UINT64_C(14695981039346656037);
    for (size_t k = 0; k < size; ++k) {
        hash ^= data[k];
        hash *= UINT64_C(1099511628211);
    }
    return hash;
}

static unsigned long long cpu_stat_total(const cpu_stat *value)
{
    return value->user + value->nice + value->system + value->idle +
           value->iowait + value->irq + value->softirq + value->steal;
}

static unsigned long long cpu_stat_busy(const cpu_stat *value)
{
    return cpu_stat_total(value) - value->idle - value->iowait;
}

static void json_cpu_stat(const cpu_stat *value)
{
    if (!value->valid) {
        printf("null");
        return;
    }
    printf("{\"user\":%llu,\"nice\":%llu,\"system\":%llu,"
           "\"idle\":%llu,\"iowait\":%llu,\"irq\":%llu,"
           "\"softirq\":%llu,\"steal\":%llu}",
           value->user, value->nice, value->system, value->idle,
           value->iowait, value->irq, value->softirq, value->steal);
}

static void *producer_main(void *opaque)
{
    producer_args *args = opaque;
    if (pin_current_thread(args->core)) {
        args->fatal = 1;
        ring_finish_producer(args->ring);
        return NULL;
    }
    pthread_mutex_lock(&args->start_mutex);
    while (!args->start_released)
        pthread_cond_wait(&args->start_cond, &args->start_mutex);
    pthread_mutex_unlock(&args->start_mutex);
    double cpu0 = local_millis(CLOCK_THREAD_CPUTIME_ID);
    const size_t chunk_bytes = args->raw_bytes / CHUNK_COUNT;
    for (unsigned job = 0; job < args->jobs; ++job) {
        const unsigned case_index = job % args->case_count;
        const double arrival = args->epoch_ms + args->offsets[job];
        if (sleep_until_ms(arrival)) {
            args->fatal = 1;
            break;
        }
        args->results[job].arrival_ms = arrival;
        args->results[job].case_index = case_index;
        unsigned slot_index = 0;
        uint64_t generation = 0;
        int dropped = ring_reserve(args->ring, job, case_index, &slot_index,
                                   &generation) != 0;
        uint8_t *destination;
        if (dropped) {
            args->results[job].status = JOB_DROPPED;
            ++args->dropped;
            destination = args->discard;
            args->discard_last_case = case_index;
            args->discard_valid = 1;
        } else {
            args->results[job].slot_index = slot_index;
            args->results[job].slot_generation = generation;
            destination = args->ring->slots[slot_index].data;
        }
        const uint8_t *source = args->cases[case_index].raw.data;
        for (unsigned chunk = 0; chunk < CHUNK_COUNT; ++chunk) {
            const double chunk_due = arrival + CHUNK_MS * (double)chunk;
            if (sleep_until_ms(chunk_due)) {
                args->fatal = 1;
                break;
            }
            double late = local_millis(CLOCK_MONOTONIC) - chunk_due;
            if (late > args->max_chunk_late_ms)
                args->max_chunk_late_ms = late;
            if (late > 1.0)
                ++args->late_chunks;
            memcpy(destination + chunk * chunk_bytes,
                   source + chunk * chunk_bytes, chunk_bytes);
        }
        if (args->fatal)
            break;
        if (sleep_until_ms(arrival + CAPTURE_MS)) {
            args->fatal = 1;
            break;
        }
        args->results[job].ready_ms = local_millis(CLOCK_MONOTONIC);
        if (dropped)
            continue;
        if (ring_publish(args->ring, slot_index, job, generation)) {
            args->fatal = 1;
            break;
        }
        ++args->produced;
    }
    args->cpu_ms = local_millis(CLOCK_THREAD_CPUTIME_ID) - cpu0;
    args->end_ms = local_millis(CLOCK_MONOTONIC);
    read_cpu_stat(args->consumer_core, &args->consumer_stat_end);
    read_cpu_stat(args->stat_other_core, &args->other_stat_end);
    ring_finish_producer(args->ring);
    return NULL;
}

static int verify_slot_sentinels(const input_case *input, const uint8_t *data)
{
    return !memcmp(input->first, data, sizeof(input->first)) &&
           !memcmp(input->last, data + input->raw.size - sizeof(input->last),
                   sizeof(input->last));
}

static int process_one(job_result *result, input_case *cases,
                       input_context *contexts, const int16_t *raw,
                       size_t sample_count, int receivers)
{
    input_case *input = &cases[result->case_index];
    input_context *context = &contexts[input->context];
    double cpu0 = local_millis(CLOCK_THREAD_CPUTIME_ID);
    result->start_ms = local_millis(CLOCK_MONOTONIC);
    for (int rx = 0; rx < receivers; ++rx) {
        int rc = run_rx(&context->work, raw, sample_count, (unsigned)rx,
                        &result->dwell[rx], &result->screens[rx],
                        &result->packing_cpu_ms[rx],
                        &result->packing_wall_ms[rx],
                        &result->detector_process_cpu_ms[rx],
                        &result->detector_wall_ms[rx]);
        if (rc) {
            result->run_rc = rc;
            result->status = JOB_FAILED;
            break;
        }
    }
    result->consumer_cpu_ms =
        local_millis(CLOCK_THREAD_CPUTIME_ID) - cpu0;
    result->end_ms = local_millis(CLOCK_MONOTONIC);
    if (!result->run_rc)
        result->status = JOB_PROCESSED;
    return result->run_rc;
}

static int create_context_work(input_context *context, unsigned rate,
                               int receivers)
{
    size_t template_count = context->exact.size / sizeof(leo_presence_complex);
    for (int rx = 0; rx < receivers; ++rx) {
#if PROBE_ALIGNED
        context->work.work[rx] = leo_blind_aligned_v5_create(
            rate, (const leo_presence_complex *)context->exact.data,
            (const leo_presence_complex *)context->control.data,
            template_count, 512, 0);
#else
        context->work.work[rx] = leo_presence_dwell_create(
            rate, (const leo_presence_complex *)context->exact.data,
            (const leo_presence_complex *)context->control.data,
            template_count, 512);
#endif
        if (!context->work.work[rx])
            return -1;
    }
#if !PROBE_ALIGNED
    size_t count = (size_t)rate * 120U / 1000U;
    context->work.packed = malloc(count * 2U * sizeof(int16_t));
    if (!context->work.packed)
        return -1;
#endif
    return 0;
}

static void destroy_context_work(input_context *context, int receivers)
{
    for (int rx = 0; rx < receivers; ++rx) {
        if (!context->work.work[rx])
            continue;
#if PROBE_ALIGNED
        leo_blind_aligned_v5_destroy(context->work.work[rx]);
#else
        leo_presence_dwell_destroy(context->work.work[rx]);
#endif
    }
#if !PROBE_ALIGNED
    free(context->work.packed);
#endif
}

static void print_job(unsigned index, const job_result *result,
                      const input_case *cases, int receivers)
{
    const char *status = result->status == JOB_PROCESSED ? "processed" :
                         result->status == JOB_DROPPED ? "dropped_queue_full" :
                         result->status == JOB_FAILED ? "detector_failed" :
                         "pending";
    printf("{\"type\":\"job\",\"index\":%u,\"case_id\":\"%s\","
           "\"status\":\"%s\",\"arrival_ms\":%.9f,"
           "\"capture_complete_due_ms\":%.9f,\"ready_ms\":%.9f,",
           index, cases[result->case_index].id, status, result->arrival_ms,
           result->arrival_ms + CAPTURE_MS, result->ready_ms);
    printf("\"capture_late_ms\":%.9f,",
           result->ready_ms - (result->arrival_ms + CAPTURE_MS));
    if (result->status == JOB_DROPPED) {
        printf("\"start_ms\":null,\"end_ms\":null,\"queue_ms\":null,"
               "\"response_ms\":null,\"consumer_thread_cpu_ms\":0,"
               "\"slot_index\":null,\"slot_generation\":null");
    } else {
        printf("\"start_ms\":%.9f,\"end_ms\":%.9f,\"queue_ms\":%.9f,"
               "\"response_ms\":%.9f,\"consumer_thread_cpu_ms\":%.9f,"
               "\"slot_index\":%u,\"slot_generation\":%" PRIu64,
               result->start_ms, result->end_ms,
               result->start_ms - result->ready_ms,
               result->end_ms - result->arrival_ms,
               result->consumer_cpu_ms, result->slot_index,
               result->slot_generation);
    }
    if (result->status == JOB_FAILED)
        printf(",\"run_rc\":%d", result->run_rc);
    if (result->status == JOB_PROCESSED) {
        printf(",\"receivers\":[");
        for (int rx = 0; rx < receivers; ++rx) {
            printf("%s{\"receiver\":%d,\"packing_cpu_ms\":%.9f,"
                   "\"packing_wall_ms\":%.9f,"
                   "\"probe_process_cpu_ms\":%.9f,"
                   "\"detector_wall_ms\":%.9f,\"result\":",
                   rx ? "," : "", rx, result->packing_cpu_ms[rx],
                   result->packing_wall_ms[rx],
                   result->detector_process_cpu_ms[rx],
                   result->detector_wall_ms[rx]);
            json_dwell(&result->dwell[rx]);
            printf(",\"screens\":");
            json_screens(&result->screens[rx]);
            putchar('}');
        }
        putchar(']');
    }
    printf("}\n");
}

static int load_offsets(const char *path, double *offsets, unsigned jobs)
{
    FILE *file = fopen(path, "r");
    if (!file)
        return -1;
    for (unsigned k = 0; k < jobs; ++k) {
        if (fscanf(file, "%lf", &offsets[k]) != 1 ||
            !isfinite(offsets[k]) || offsets[k] < 0.0 ||
            (k && offsets[k] - offsets[k - 1] < CAPTURE_MS)) {
            fclose(file);
            return -1;
        }
    }
    double extra;
    if (fscanf(file, "%lf", &extra) == 1) {
        fclose(file);
        return -1;
    }
    fclose(file);
    if (fabs(offsets[0]) > 1e-9 || offsets[jobs - 1] + CAPTURE_MS > 90000.0)
        return -1;
    return 0;
}

static void usage(const char *program)
{
    fprintf(stderr,
        "usage: %s CASE_LIST RATE JOBS PERIOD_MS CONSUMER_CORE "
        "PRODUCER_CORE RX_COUNT RING_SLOTS [ARRIVAL_OFFSETS_MS]\n"
        "       PRODUCER_CORE=-1 selects isolated resident-input mode\n",
        program);
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--ring-self-test"))
        return ring_self_test();
    if (argc != 9 && argc != 10) {
        usage(argv[0]);
        return 2;
    }
    unsigned rate, jobs, receivers, ring_slots;
    int consumer_core, producer_core;
    char *period_end = NULL;
    errno = 0;
    double period_ms = strtod(argv[4], &period_end);
    if (parse_unsigned(argv[2], &rate) || parse_unsigned(argv[3], &jobs) ||
        errno || !period_end || *period_end || !isfinite(period_ms) ||
        parse_int(argv[5], &consumer_core) ||
        parse_int(argv[6], &producer_core) ||
        parse_unsigned(argv[7], &receivers) ||
        parse_unsigned(argv[8], &ring_slots) ||
        (rate != 2500000U && rate != 5000000U &&
         rate != 7500000U && rate != 10000000U) ||
        jobs < 1 || jobs > MAX_JOBS || period_ms < CAPTURE_MS ||
        period_ms > 1000.0 || consumer_core < 0 ||
        consumer_core >= CPU_SETSIZE || producer_core < -1 ||
        producer_core >= CPU_SETSIZE || producer_core == consumer_core ||
        (receivers != 1 && receivers != 2) || ring_slots < 1 ||
        ring_slots > MAX_RING_SLOTS) {
        usage(argv[0]);
        return 2;
    }
    const int isolated = producer_core == -1;
    alarm(120);

    double *offsets = calloc(jobs, sizeof(*offsets));
    job_result *results = calloc(jobs, sizeof(*results));
    if (!offsets || !results)
        return 2;
    for (unsigned k = 0; k < jobs; ++k)
        offsets[k] = (double)k * period_ms;
    if ((argc == 10 && load_offsets(argv[9], offsets, jobs)) ||
        (argc == 9 && offsets[jobs - 1] + CAPTURE_MS > 90000.0)) {
        fprintf(stderr, "invalid arrival schedule\n");
        return 2;
    }

    cpu_set_t initially_allowed;
    if (sched_getaffinity(0, sizeof(initially_allowed), &initially_allowed) ||
        !CPU_ISSET(consumer_core, &initially_allowed) ||
        (!isolated && !CPU_ISSET(producer_core, &initially_allowed))) {
        fprintf(stderr, "requested cores are not allowed\n");
        return 2;
    }
    int stat_other_core = producer_core;
    if (stat_other_core < 0) {
        for (int core = 0; core < CPU_SETSIZE; ++core) {
            if (core != consumer_core && CPU_ISSET(core, &initially_allowed)) {
                stat_other_core = core;
                break;
            }
        }
    }
    if (stat_other_core < 0)
        stat_other_core = consumer_core;

    input_case cases[MAX_CASES] = {0};
    input_context contexts[MAX_CONTEXTS] = {0};
    unsigned case_count = 0, context_count = 0;
    size_t owned_bytes = 0;
    const size_t sample_count = (size_t)rate * 120U / 1000U;
    const size_t raw_bytes = sample_count * 4U * sizeof(int16_t);
    FILE *case_list = fopen(argv[1], "r");
    if (!case_list) {
        perror("case list");
        return 2;
    }
    char line[2048];
    while (fgets(line, sizeof(line), case_list)) {
        char raw_path[512], exact_path[512], control_path[512], id[160], extra;
        if (line[0] == '#' || line[0] == '\n')
            continue;
        if (sscanf(line, "%511s %511s %511s %159s %c", raw_path,
                   exact_path, control_path, id, &extra) != 4 ||
            !valid_id(id) || case_count == MAX_CASES) {
            fprintf(stderr, "invalid case-list row\n");
            return 2;
        }
        unsigned context_index = 0;
        while (context_index < context_count &&
               (strcmp(contexts[context_index].exact_path, exact_path) ||
                strcmp(contexts[context_index].control_path, control_path)))
            ++context_index;
        if (context_index == context_count) {
            if (context_count == MAX_CONTEXTS) {
                fprintf(stderr, "too many template contexts\n");
                return 2;
            }
            input_context *context = &contexts[context_count++];
            strcpy(context->exact_path, exact_path);
            strcpy(context->control_path, control_path);
            if (load_owned(exact_path, &context->exact, &owned_bytes) ||
                load_owned(control_path, &context->control, &owned_bytes) ||
                context->exact.size != context->control.size ||
                context->exact.size % sizeof(leo_presence_complex)) {
                fprintf(stderr, "invalid template files\n");
                return 2;
            }
        }
        input_case *input = &cases[case_count];
        input->context = context_index;
        strcpy(input->id, id);
        if (load_owned(raw_path, &input->raw, &owned_bytes) ||
            input->raw.size != raw_bytes || input->raw.size < 32) {
            fprintf(stderr, "invalid raw input\n");
            return 2;
        }
        memcpy(input->first, input->raw.data, sizeof(input->first));
        memcpy(input->last,
               input->raw.data + input->raw.size - sizeof(input->last),
               sizeof(input->last));
        input->full_signature = full_signature(input->raw.data,
                                               input->raw.size);
        ++case_count;
    }
    fclose(case_list);
    if (!case_count) {
        fprintf(stderr, "empty case list\n");
        return 2;
    }

    /* Concurrent mode owns one additional prefaulted queue-full sink. */
    size_t ring_owned_bytes = isolated ? 0 : raw_bytes * (ring_slots + 1U);
    if (ring_owned_bytes > MAX_OWNED_BYTES ||
        owned_bytes > MAX_OWNED_BYTES - ring_owned_bytes) {
        fprintf(stderr, "owned input plus ring exceeds 160 MiB\n");
        return 2;
    }
    for (unsigned k = 0; k < context_count; ++k) {
        if (create_context_work(&contexts[k], rate, (int)receivers)) {
            fprintf(stderr, "workspace initialization failed\n");
            return 2;
        }
    }
    if (pin_current_thread(consumer_core)) {
        fprintf(stderr, "consumer affinity failed\n");
        return 2;
    }
    /* Warm every case/context path from owned RAM before the timed interval. */
    for (unsigned k = 0; k < case_count; ++k) {
        job_result warm = {0};
        warm.case_index = k;
        if (process_one(&warm, cases, contexts,
                        (const int16_t *)cases[k].raw.data,
                        sample_count, (int)receivers)) {
            fprintf(stderr, "warmup failed\n");
            return 2;
        }
    }

    bounded_ring ring = {0};
    if (!isolated && ring_init(&ring, ring_slots, raw_bytes)) {
        fprintf(stderr, "ring allocation failed\n");
        return 2;
    }
    uint8_t *discard = NULL;
    if (!isolated) {
        discard = malloc(raw_bytes);
        if (!discard) {
            fprintf(stderr, "discard allocation failed\n");
            return 2;
        }
        memset(discard, 0, raw_bytes);
    }
    struct rusage usage_before, usage_after;
    getrusage(RUSAGE_SELF, &usage_before);
    double start_not_before_ms = local_millis(CLOCK_MONOTONIC) + 500.0;
    printf("{\"type\":\"ready\","
           "\"schema\":\"org.leo.research.arm-ram-pipeline/v1\","
           "\"method\":\"%s\",\"fft_backend\":\"%s\","
           "\"profile\":\"saved-iq-rank6-confirm1-dual-ci16-120ms\","
           "\"scientific_scope\":\"native-rank6-plus-confirm1;not-full-server-11x8\","
           "\"mode\":\"%s\",\"rate_hz\":%u,\"jobs\":%u,"
           "\"period_ms\":%.9g,\"schedule_kind\":\"%s\","
           "\"capture_ms\":120,\"chunk_ms\":10,"
           "\"consumer_core\":%d,\"producer_core\":%d,"
           "\"stat_other_core\":%d,\"receivers\":%u,"
           "\"ring_slots\":%u,\"case_count\":%u,"
           "\"owned_input_bytes\":%zu,\"owned_ring_bytes\":%zu,"
           "\"start_not_before_ms\":%.9f}\n",
           PROBE_METHOD, leo_fft_backend_identity(),
           isolated ? "isolated" : "concurrent", rate, jobs, period_ms,
           argc == 10 ? "saved-arrival-offsets" : "fixed-period",
           consumer_core, producer_core, stat_other_core, receivers,
           isolated ? 0U : ring_slots, case_count, owned_bytes,
           ring_owned_bytes, start_not_before_ms);
    fflush(stdout);

    producer_args producer = {
        .ring = &ring,
        .cases = cases,
        .case_count = case_count,
        .results = results,
        .offsets = offsets,
        .jobs = jobs,
        .epoch_ms = start_not_before_ms,
        .raw_bytes = raw_bytes,
        .core = producer_core,
        .consumer_core = consumer_core,
        .stat_other_core = stat_other_core,
        .discard = discard
    };
    if (!isolated &&
        (pthread_mutex_init(&producer.start_mutex, NULL) ||
         pthread_cond_init(&producer.start_cond, NULL))) {
        fprintf(stderr, "start gate initialization failed\n");
        return 2;
    }
    pthread_t producer_thread;
    if (!isolated && pthread_create(&producer_thread, NULL,
                                     producer_main, &producer)) {
        fprintf(stderr, "producer thread creation failed\n");
        return 2;
    }

    sleep_until_ms(start_not_before_ms);
    cpu_stat consumer_stat_start = {0}, other_stat_start = {0};
    cpu_stat consumer_stat_end = {0}, other_stat_end = {0};
    read_cpu_stat(consumer_core, &consumer_stat_start);
    read_cpu_stat(stat_other_core, &other_stat_start);
    const double timed_start_ms = local_millis(CLOCK_MONOTONIC);
    const double process_cpu_start = local_millis(CLOCK_PROCESS_CPUTIME_ID);
    const double consumer_cpu_start = local_millis(CLOCK_THREAD_CPUTIME_ID);
    const double epoch_ms = local_millis(CLOCK_MONOTONIC);
    if (!isolated) {
        pthread_mutex_lock(&producer.start_mutex);
        producer.epoch_ms = epoch_ms;
        producer.start_released = 1;
        pthread_cond_signal(&producer.start_cond);
        pthread_mutex_unlock(&producer.start_mutex);
    }
    unsigned consumed = 0, failures = 0;
    int ownership_error = 0;
    if (isolated) {
        for (unsigned job = 0; job < jobs; ++job) {
            job_result *result = &results[job];
            result->case_index = job % case_count;
            result->slot_index = UINT32_MAX;
            result->arrival_ms = epoch_ms + offsets[job];
            result->ready_ms = result->arrival_ms + CAPTURE_MS;
            if (sleep_until_ms(result->ready_ms)) {
                ownership_error = 1;
                break;
            }
            if (process_one(result, cases, contexts,
                            (const int16_t *)cases[result->case_index].raw.data,
                            sample_count, (int)receivers))
                ++failures;
            ++consumed;
        }
    } else {
        for (;;) {
            unsigned slot_index, job, case_index;
            uint64_t generation;
            int available = ring_take_ready(&ring, &slot_index, &job,
                                            &case_index, &generation);
            if (!available)
                break;
            job_result *result = &results[job];
            if (result->case_index != case_index ||
                result->slot_index != slot_index ||
                result->slot_generation != generation ||
                !verify_slot_sentinels(&cases[case_index],
                                       ring.slots[slot_index].data)) {
                result->status = JOB_FAILED;
                result->run_rc = -1001;
                ++failures;
                ownership_error = 1;
            } else if (process_one(result, cases, contexts,
                                   (const int16_t *)ring.slots[slot_index].data,
                                   sample_count, (int)receivers)) {
                ++failures;
            }
            ++consumed;
            if (ring_release(&ring, slot_index, job, generation)) {
                ownership_error = 1;
                break;
            }
        }
        pthread_join(producer_thread, NULL);
    }
    const double consumer_cpu_ms =
        local_millis(CLOCK_THREAD_CPUTIME_ID) - consumer_cpu_start;
    const double process_cpu_ms =
        local_millis(CLOCK_PROCESS_CPUTIME_ID) - process_cpu_start;
    const double timed_end_ms = local_millis(CLOCK_MONOTONIC);
    read_cpu_stat(consumer_core, &consumer_stat_end);
    read_cpu_stat(stat_other_core, &other_stat_end);
    getrusage(RUSAGE_SELF, &usage_after);

    /* Full-buffer integrity checks occur after all timed snapshots. */
    unsigned post_timing_signature_mismatches = 0;
    if (!isolated) {
        for (unsigned k = 0; k < ring.slot_count; ++k) {
            ring_slot *slot = &ring.slots[k];
            if (slot->generation &&
                full_signature(slot->data, raw_bytes) !=
                    cases[slot->case_index].full_signature)
                ++post_timing_signature_mismatches;
        }
        if (producer.discard_valid &&
            full_signature(discard, raw_bytes) !=
                cases[producer.discard_last_case].full_signature)
            ++post_timing_signature_mismatches;
    }

    unsigned processed = 0, dropped = 0, pending = 0;
    for (unsigned job = 0; job < jobs; ++job) {
        if (results[job].status == JOB_PROCESSED)
            ++processed;
        else if (results[job].status == JOB_DROPPED)
            ++dropped;
        else if (results[job].status == JOB_PENDING)
            ++pending;
        print_job(job, &results[job], cases, (int)receivers);
    }
    unsigned long long consumer_total_delta = 0, consumer_busy_delta = 0;
    unsigned long long other_total_delta = 0, other_busy_delta = 0;
    unsigned long long producer_consumer_total_delta = 0;
    unsigned long long producer_consumer_busy_delta = 0;
    unsigned long long producer_other_total_delta = 0;
    unsigned long long producer_other_busy_delta = 0;
    if (consumer_stat_start.valid && consumer_stat_end.valid) {
        consumer_total_delta = cpu_stat_total(&consumer_stat_end) -
                               cpu_stat_total(&consumer_stat_start);
        consumer_busy_delta = cpu_stat_busy(&consumer_stat_end) -
                              cpu_stat_busy(&consumer_stat_start);
    }
    if (other_stat_start.valid && other_stat_end.valid) {
        other_total_delta = cpu_stat_total(&other_stat_end) -
                            cpu_stat_total(&other_stat_start);
        other_busy_delta = cpu_stat_busy(&other_stat_end) -
                           cpu_stat_busy(&other_stat_start);
    }
    if (!isolated && consumer_stat_start.valid &&
        producer.consumer_stat_end.valid) {
        producer_consumer_total_delta =
            cpu_stat_total(&producer.consumer_stat_end) -
            cpu_stat_total(&consumer_stat_start);
        producer_consumer_busy_delta =
            cpu_stat_busy(&producer.consumer_stat_end) -
            cpu_stat_busy(&consumer_stat_start);
    }
    if (!isolated && other_stat_start.valid && producer.other_stat_end.valid) {
        producer_other_total_delta = cpu_stat_total(&producer.other_stat_end) -
                                     cpu_stat_total(&other_stat_start);
        producer_other_busy_delta = cpu_stat_busy(&producer.other_stat_end) -
                                    cpu_stat_busy(&other_stat_start);
    }
    long ticks = sysconf(_SC_CLK_TCK);
    const int complete = !ownership_error && !producer.fatal && !failures &&
        !post_timing_signature_mismatches &&
        !pending && processed + dropped == jobs && consumed == processed + failures &&
        (isolated || (producer.produced == consumed && producer.dropped == dropped &&
                      ring.occupied == 0 && ring.ready == 0));
    printf("{\"type\":\"complete\","
           "\"schema\":\"org.leo.research.arm-ram-pipeline/v1\","
           "\"complete\":%s,\"mode\":\"%s\","
           "\"jobs\":%u,\"processed\":%u,\"consumed\":%u,"
           "\"dropped_queue_full\":%u,\"pending\":%u,"
           "\"detector_failures\":%u,\"ownership_error\":%s,"
           "\"producer_fatal\":%s,\"timed_start_ms\":%.9f,"
           "\"arrival_epoch_ms\":%.9f,"
           "\"timed_end_ms\":%.9f,\"actual_duration_ms\":%.9f,"
           "\"consumer_thread_cpu_ms\":%.9f,"
           "\"producer_thread_cpu_ms\":%.9f,"
           "\"process_cpu_ms\":%.9f,\"producer_end_ms\":%.9f,"
           "\"producer_late_chunks_over_1ms\":%u,"
           "\"producer_max_chunk_late_ms\":%.9f,"
           "\"queue_full_overruns\":%u,"
           "\"ring_occupied_highwater\":%u,"
           "\"ready_queue_highwater\":%u,"
           "\"post_timing_full_signature_mismatches\":%u,"
           "\"maxrss_kib_before\":%ld,\"maxrss_kib_after\":%ld,"
           "\"clock_ticks_per_second\":%ld,"
           "\"consumer_core_stat_start\":",
           complete ? "true" : "false", isolated ? "isolated" : "concurrent",
           jobs, processed, consumed, dropped, pending, failures,
           ownership_error ? "true" : "false",
           producer.fatal ? "true" : "false", timed_start_ms, epoch_ms,
           timed_end_ms,
           timed_end_ms - timed_start_ms, consumer_cpu_ms,
           isolated ? 0.0 : producer.cpu_ms, process_cpu_ms,
           isolated ? 0.0 : producer.end_ms,
           isolated ? 0U : producer.late_chunks,
           isolated ? 0.0 : producer.max_chunk_late_ms,
           isolated ? 0U : ring.queue_full_overruns,
           isolated ? 0U : ring.occupied_highwater,
           isolated ? 0U : ring.ready_highwater,
           post_timing_signature_mismatches,
           usage_before.ru_maxrss, usage_after.ru_maxrss, ticks);
    json_cpu_stat(&consumer_stat_start);
    printf(",\"consumer_core_stat_end\":");
    json_cpu_stat(&consumer_stat_end);
    printf(",\"consumer_core_total_ticks\":%llu,"
           "\"consumer_core_busy_ticks\":%llu,"
           "\"consumer_core_busy_fraction\":%.9f,"
           "\"other_core\":%d,\"other_core_stat_start\":",
           consumer_total_delta, consumer_busy_delta,
           consumer_total_delta ? (double)consumer_busy_delta /
                                  (double)consumer_total_delta : 0.0,
           stat_other_core);
    json_cpu_stat(&other_stat_start);
    printf(",\"producer_end_consumer_core_stat\":");
    if (isolated)
        printf("null");
    else
        json_cpu_stat(&producer.consumer_stat_end);
    printf(",\"producer_end_other_core_stat\":");
    if (isolated)
        printf("null");
    else
        json_cpu_stat(&producer.other_stat_end);
    printf(",\"producer_window_consumer_core_total_ticks\":%llu,"
           "\"producer_window_consumer_core_busy_ticks\":%llu,"
           "\"producer_window_consumer_core_busy_fraction\":%.9f,"
           "\"producer_window_other_core_total_ticks\":%llu,"
           "\"producer_window_other_core_busy_ticks\":%llu,"
           "\"producer_window_other_core_busy_fraction\":%.9f",
           producer_consumer_total_delta, producer_consumer_busy_delta,
           producer_consumer_total_delta ?
               (double)producer_consumer_busy_delta /
                   (double)producer_consumer_total_delta : 0.0,
           producer_other_total_delta, producer_other_busy_delta,
           producer_other_total_delta ?
               (double)producer_other_busy_delta /
                   (double)producer_other_total_delta : 0.0);
    printf(",\"other_core_stat_end\":");
    json_cpu_stat(&other_stat_end);
    printf(",\"other_core_total_ticks\":%llu,"
           "\"other_core_busy_ticks\":%llu,"
           "\"other_core_busy_fraction\":%.9f}\n",
           other_total_delta, other_busy_delta,
           other_total_delta ? (double)other_busy_delta /
                               (double)other_total_delta : 0.0);

    if (!isolated) {
        pthread_cond_destroy(&producer.start_cond);
        pthread_mutex_destroy(&producer.start_mutex);
    }
    free(discard);
    ring_destroy(&ring);
    for (unsigned k = 0; k < context_count; ++k) {
        destroy_context_work(&contexts[k], (int)receivers);
        free(contexts[k].exact.data);
        free(contexts[k].control.data);
    }
    for (unsigned k = 0; k < case_count; ++k)
        free(cases[k].raw.data);
    free(offsets);
    free(results);
    return complete ? 0 : 1;
}
#endif
