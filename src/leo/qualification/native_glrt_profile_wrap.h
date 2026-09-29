#ifndef LEO_QUALIFICATION_NATIVE_GLRT_PROFILE_WRAP_H
#define LEO_QUALIFICATION_NATIVE_GLRT_PROFILE_WRAP_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint64_t malloc_calls, calloc_calls, realloc_calls, free_calls;
    uint64_t allocation_requested_bytes;
    double allocation_cpu_ms, allocation_wall_ms;
    uint64_t fft_plan_calls, fftf_plan_calls;
    double fft_plan_cpu_ms, fft_plan_wall_ms;
    double fftf_plan_cpu_ms, fftf_plan_wall_ms;
    uint64_t fft_execute_calls, fftf_execute_calls;
    double fft_execute_cpu_ms, fft_execute_wall_ms;
    double fftf_execute_cpu_ms, fftf_execute_wall_ms;
} leo_native_glrt_wrap_profile;

/* Diagnostic state is process-global and intentionally not thread-safe. The
 * inclusive totals include nested allocator work performed by wrapped FFTW
 * calls and therefore must not be added as disjoint stage measurements. */
void leo_native_glrt_wrap_profile_reset(void);
leo_native_glrt_wrap_profile leo_native_glrt_wrap_profile_snapshot(void);

#endif
