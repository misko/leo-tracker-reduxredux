/* Qualification hook for two independently scoped signed native contexts. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>

enum { taps_expected = 81, stride_expected = 4, retained = 29990 };

typedef struct {
    const float *prefix, *coeff;
    int reused, full_scouts;
} FirReuse;

static _Thread_local FirReuse *active;

int __real_delay_decimate(const float *, const float *, int, int, float *);

#ifdef SHORT_APERTURE
void leo_escalation_capture(FirReuse *state) {
    active = state;
}

int __wrap_delay_decimate(const float *in, const float *coeff, int taps, int stride, float *out) {
    int status = __real_delay_decimate(in, coeff, taps, stride, out);
    if (!status && active && taps == taps_expected && stride == stride_expected) {
        active->prefix = out;
        active->coeff = coeff;
    }
    return status;
}
#else
void leo_escalation_fir_suffix(const float *, const float *, float *);

int __wrap_delay_decimate(const float *in, const float *coeff, int taps, int stride, float *out) {
    if (active && ++active->full_scouts == 1 && active->prefix && in && coeff && out &&
        taps == taps_expected && stride == stride_expected && __builtin_cpu_supports("avx2") &&
        !memcmp(active->coeff, coeff, taps_expected * sizeof(float))) {
        memcpy(out, active->prefix, 2 * retained * sizeof(float));
        leo_escalation_fir_suffix(in, coeff, out);
        active->reused = 1;
        return 0;
    }
    return __real_delay_decimate(in, coeff, taps, stride, out);
}

typedef struct {
    int rank, integer;
    double offset, hz, exact, control;
} Factor;

typedef int (*Measure)(void *, const int16_t *, int, double, double, Factor *);
typedef void (*Capture)(FirReuse *);

int cancellation_factors(void *, const int16_t *, int, double, double, Factor *);

enum { restart, resume, fresh };

/* The two calls share one immutable input, fixed lane and fixed signed interval.
   Scope the borrowed short workspace to this call, before either context can
   process another lane. Only the first full scout may consume the prefix. */
int leo_escalation_run(void *full, void *short_context, Measure short_measure, Capture capture,
                       const int16_t *input, int lane, double lo, double hi, int mode,
                       Factor *short_out, Factor *full_out, int stats[3]) {
    FirReuse state = {0};
    int short_count = 0;
    if (!full || !input || !full_out || !stats || mode < restart || mode > fresh || active)
        return -1;
    if (mode != fresh) {
        if (!short_context || !short_measure || !capture || !short_out || full == short_context)
            return -1;
        if (mode == resume)
            capture(&state);
        short_count = short_measure(short_context, input, lane, lo, hi, short_out);
        if (mode == resume)
            capture(NULL);
        if (short_count < 0 || short_count > 1)
            return -1;
    }
    active = &state;
    int count = cancellation_factors(full, input, lane, lo, hi, full_out);
    active = NULL;
    stats[0] = short_count;
    stats[1] = state.reused;
    stats[2] = state.full_scouts;
    return count;
}
#endif
