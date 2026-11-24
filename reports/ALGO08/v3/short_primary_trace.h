#ifndef LEO_SHORT_PRIMARY_TRACE_H
#define LEO_SHORT_PRIMARY_TRACE_H

#include <stdint.h>
#include <time.h>

typedef enum {
    sp_input, sp_fir, sp_modes, sp_timing, sp_carrier, sp_prepare,
    sp_refine, sp_confirm, sp_load, sp_integer, sp_vertex,
    sp_frac_corr, sp_fractional_spectra, sp_residual, sp_stages
} ShortStage;

typedef struct {
    uint64_t ns[sp_stages], total;
    int attempts[3];
    uint64_t gate_ns[3];
    int witness, confirmed_epoch, verifier_epoch, requests, residual_reads, winner_request;
    int seed_epoch[16];
    double seed_hz[16], confirmed_hz, verifier_hz;
} ShortTrace;

extern _Thread_local __attribute__((visibility("hidden"))) ShortTrace sp_trace;

static inline uint64_t sp_now(void) {
    struct timespec tick;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &tick);
    return UINT64_C(1000000000) * tick.tv_sec + tick.tv_nsec;
}

static inline uint64_t sp_mark(uint64_t start, ShortStage phase) {
    uint64_t end = sp_now();
    sp_trace.ns[phase] += end - start;
    return end;
}

#endif
