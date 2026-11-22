#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

enum { estimate_calls, wisdom_calls, fallback_calls, import_ns, planning_ns, setup_ns,
       timing_forward_calls, timing_backward_calls, carrier_forward_calls,
       timing_forward_ns, timing_backward_ns, carrier_forward_ns, wisdom_counters };
static _Atomic uint64_t wisdom_stats[wisdom_counters];
static _Atomic int profile_transforms;
static char *declared_wisdom;

static uint64_t fft_cpu_ns(void) {
    struct timespec clock;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &clock)) return 0;
    return (uint64_t)clock.tv_sec * UINT64_C(1000000000) + (uint64_t)clock.tv_nsec;
}

int experimental_receiver_fftw_configure(const char *wisdom, int profile) {
    char *copy = NULL;
    if (wisdom) {
        size_t length = strlen(wisdom) + 1;
        if (length > 65536 || !(copy = malloc(length))) return 0;
        memcpy(copy, wisdom, length);
    }
    pthread_mutex_lock(&planner_lock);
    free(declared_wisdom);
    declared_wisdom = copy;
    atomic_store_explicit(&profile_transforms, profile, memory_order_relaxed);
    pthread_mutex_unlock(&planner_lock);
    return 1;
}

unsigned experimental_receiver_fftw_stats(uint64_t *out, unsigned count) {
    if (count < wisdom_counters) return 0;
    for (unsigned i = 0; i < wisdom_counters; ++i)
        out[i] = atomic_load_explicit(&wisdom_stats[i], memory_order_relaxed);
    return wisdom_counters;
}

static int plan_set(TimingFirst *w, fftwf_complex *z, unsigned flags) {
    w->plans[timing_forward] = fftwf_plan_dft_1d(CORRELATION_SIZE(w), z, z, FFTW_FORWARD, flags);
    w->plans[timing_backward] = fftwf_plan_dft_1d(CORRELATION_SIZE(w), z, z, FFTW_BACKWARD, flags);
    w->plans[carrier_forward] = fftwf_plan_dft_1d(bins, z, z, FFTW_FORWARD, flags);
    return w->plans[timing_forward] && w->plans[timing_backward] && w->plans[carrier_forward];
}

static int prepare_fft(TimingFirst *w) {
    fftwf_complex *z = (fftwf_complex *)w->scratch;
    uint64_t begin = fft_cpu_ns();
    pthread_mutex_lock(&planner_lock);
    int ready = 0;
    if (declared_wisdom) {
        char *previous = fftwf_export_wisdom_to_string();
        if (previous) {
            fftwf_forget_wisdom();
            uint64_t started = fft_cpu_ns();
            int imported = fftwf_import_wisdom_from_string(declared_wisdom);
            wisdom_stats[import_ns] += fft_cpu_ns() - started;
            if (imported) {
                started = fft_cpu_ns();
                ready = plan_set(w, z, FFTW_MEASURE | FFTW_WISDOM_ONLY);
                wisdom_stats[planning_ns] += fft_cpu_ns() - started;
            }
            fftwf_forget_wisdom();
            fftwf_import_wisdom_from_string(previous);
            fftwf_free(previous);
        }
        if (ready) {
            ++wisdom_stats[wisdom_calls];
        } else {
            ++wisdom_stats[fallback_calls];
            for (int i = 0; i < fft_plans; ++i) {
                if (w->plans[i]) fftwf_destroy_plan(w->plans[i]);
                w->plans[i] = NULL;
            }
        }
    }
    if (!ready) {
        ++wisdom_stats[estimate_calls];
        uint64_t started = fft_cpu_ns();
        ready = plan_set(w, z, FFTW_ESTIMATE);
        wisdom_stats[planning_ns] += fft_cpu_ns() - started;
    }
    pthread_mutex_unlock(&planner_lock);
    wisdom_stats[setup_ns] += fft_cpu_ns() - begin;
    return ready;
}

static void execute_wisdom_profile(TimingFirst *w, int plan) {
    if (!atomic_load_explicit(&profile_transforms, memory_order_relaxed)) {
        fftwf_execute(w->plans[plan]);
        return;
    }
    uint64_t started = fft_cpu_ns();
    fftwf_execute(w->plans[plan]);
    wisdom_stats[timing_forward_ns + plan] += fft_cpu_ns() - started;
    ++wisdom_stats[timing_forward_calls + plan];
}
