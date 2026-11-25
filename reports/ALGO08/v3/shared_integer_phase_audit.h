#include <stdint.h>

typedef struct {
    unsigned epoch, flags;
    double carrier, offset, residual, exact, rolled;
} SharedPhaseAudit;

static _Thread_local SharedPhaseAudit last_phase;
static _Thread_local unsigned phase_records;

static void shared_phase_record(unsigned epoch, const PortableVerifierResult *out)
{
    last_phase = (SharedPhaseAudit){
        epoch, out->flags, out->acquired_hz, out->offset_samples,
        out->fractional_residual_hz, out->fractional_exact, out->fractional_control
    };
    ++phase_records;
}

int shared_phase_take(SharedPhaseAudit *out, uint64_t statistics[3])
{
    *out = last_phase;
    experimental_phase_free_stats(statistics, 1);
    int count = (int)phase_records;
    phase_records = 0;
    return count;
}
