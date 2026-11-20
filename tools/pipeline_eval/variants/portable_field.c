#define _POSIX_C_SOURCE 200809L
#include "portable_coarse.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {
    unsigned epoch, coarse_epoch, seed_index, flags;
    double coarse_cfo, coarse_score, acquired_cfo, acquisition_score;
    double integer_exact, integer_control, integer_residual;
    double fractional_offset, fractional_exact, fractional_control, fractional_residual;
} Candidate;

typedef struct {
    unsigned lane, anchors, count;
    uint64_t coarse_cpu, coarse_wall, verify_cpu, verify_wall;
    Candidate candidates[PORTABLE_VERIFIER_MAX_SEEDS];
} Group;

typedef struct {
    PortableCoarse *coarse;
    PortableVerifier *verifier;
    unsigned edge;
} Field;

static uint64_t now(clockid_t clock) {
    struct timespec t;
    if (clock_gettime(clock, &t)) abort();
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

void portable_field_free(Field *field) {
    if (!field) return;
    portable_verifier_free(field->verifier);
    portable_coarse_free(field->coarse);
    free(field);
}

Field *portable_field_create(unsigned edge) {
    Field *field = calloc(1, sizeof(*field));
    if (!field) return NULL;
    field->edge = edge;
    field->coarse = portable_coarse_create(edge);
    if (field->coarse)
        field->verifier = portable_verifier_create(portable_coarse_template(field->coarse, 0),
                                                   portable_coarse_template(field->coarse, 1));
    if (field->verifier) return field;
    portable_field_free(field);
    return NULL;
}

static int run_group(Field *field, const int16_t *iq, const PortableCoarseCapture *capture,
                     unsigned lane, unsigned anchors, Group *group) {
    PortableVerifierSeed seeds[PORTABLE_VERIFIER_MAX_SEEDS];
    PortableCoarsePeak peaks[PORTABLE_VERIFIER_MAX_SEEDS];
    PortableVerifierResult results[PORTABLE_VERIFIER_MAX_SEEDS];
    uint64_t wall = now(CLOCK_MONOTONIC), cpu = now(CLOCK_PROCESS_CPUTIME_ID);
    group->lane = lane;
    group->anchors = anchors;
    if (portable_coarse_acquire(field->coarse, iq, capture, lane, anchors, seeds, peaks,
                                &group->count)) return -1;
    group->coarse_cpu = now(CLOCK_PROCESS_CPUTIME_ID) - cpu;
    group->coarse_wall = now(CLOCK_MONOTONIC) - wall;
    if (!group->count) return 0;

    wall = now(CLOCK_MONOTONIC);
    cpu = now(CLOCK_PROCESS_CPUTIME_ID);
    if (portable_verifier_load(field->verifier, iq, lane) ||
        portable_verifier_acquire(field->verifier, seeds, group->count,
                                  capture->center_hz[lane], capture->low_hz,
                                  capture->high_hz, results)) return -1;
    int positive = 0;
    for (unsigned i = 0; i < group->count; ++i) {
        PortableVerifierResult *r = &results[i];
        const unsigned j = r->seed_index;
        if (j >= group->count || portable_verifier_glrt(field->verifier, seeds[j].epoch, r))
            return -1;
        positive |= (r->flags & PORTABLE_VERIFIER_FRACTIONAL_GATE) != 0;
        group->candidates[i] = (Candidate){
            seeds[j].epoch, peaks[j].original_epoch, j, r->flags,
            peaks[j].residual_hz, peaks[j].score, r->acquired_hz, r->acquire,
            r->integer_exact, r->integer_control, r->integer_residual_hz,
            r->offset_samples, r->fractional_exact, r->fractional_control, r->fractional_residual_hz
        };
    }
    group->verify_cpu = now(CLOCK_PROCESS_CPUTIME_ID) - cpu;
    group->verify_wall = now(CLOCK_MONOTONIC) - wall;
    return positive;
}

int portable_field_detect(Field *field, const int16_t *iq, double center, double width,
                          Group groups[3]) {
    if (!field || !iq || !groups || !isfinite(center) || !isfinite(width) || width <= 0)
        return -1;
    memset(groups, 0, 3 * sizeof(*groups));
    const PortableCoarseCapture capture = {
        PORTABLE_FINE_SAMPLES, field->edge, 3, {center, center}, -width, width
    };
    const int first = run_group(field, iq, &capture, 0, PORTABLE_COARSE_PRIMARY, &groups[0]);
    if (first < 0) return -1;
    const int second = run_group(field, iq, &capture, 1, PORTABLE_COARSE_PRIMARY, &groups[1]);
    if (second < 0) return -1;
    if (first == second) return 2;
    return run_group(field, iq, &capture, first ? 1 : 0, PORTABLE_COARSE_RETRY, &groups[2]) < 0
        ? -1 : 3;
}

size_t portable_field_workspace_bytes(void) {
    return sizeof(Field) + portable_coarse_workspace_bytes() + portable_verifier_workspace_bytes();
}

size_t portable_field_group_bytes(void) { return sizeof(Group); }
