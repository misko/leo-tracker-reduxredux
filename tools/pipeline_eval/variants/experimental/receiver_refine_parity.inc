#include "receiver_refine_parity.h"

static _Thread_local uint64_t parity_attempts, parity_pruned;

void experimental_receiver_parity_read(uint64_t out[2])
{
    out[0] = parity_attempts;
    out[1] = parity_pruned;
}

void experimental_receiver_parity_reset(void)
{
    parity_attempts = parity_pruned = 0;
}

/* The refined score is at most the normalized even-frame score. For any
   residual rotation, each sin/cos component has magnitude at most one.
   Thus Cauchy--Schwarz bounds the coherent sum's power by 16 times the
   incoherent block power (eight blocks and squared rotation norm <= 2).
   The factor 17 rounds this upward, including the binary64 arithmetic.
   The denominator follows the same arithmetic as finish_refine. */
static int below_incumbent(const BlockMatrix matrix, double energy, double incumbent)
{
    for (int epoch = 0; epoch < 9; ++epoch) {
        double power = 0., incoherent = 0.;
        for (int f = 0; f < frames; f += 2) {
            for (int b = 0; b < 8; ++b) {
                LateCorrelation value = matrix[epoch][f][b];
                double re = value.real, im = value.imag;
                incoherent += re*re + im*im;
                power += value.power;
            }
        }
        double upper = (17. * incoherent) / fmax(power * energy, 1e-15);
        if (!isfinite(power) || !isfinite(upper) || !(upper < incumbent)) return 0;
    }
    return 1;
}

__attribute__((target("avx2")))
static int refine_one_parity(const float *x, const float *h, RefineRequest seed,
                             double lo, double hi, double incumbent, double out[4])
{
    RefineRotation rotation;
    prepare_refine_rotation(h, seed.hz, &rotation);
    if (!(rotation.energy > 0.) || !isfinite(rotation.energy))
        return delay_refine_bank(x, h, &seed, 1, lo, hi, (double (*)[4])out);
    BlockMatrix matrix;
    const RefineRotation *rotations[] = {&rotation};
    correlate_group(x, rotations, 1, seed.epoch, &matrix, 0, 2);
    ++parity_attempts;
    if (below_incumbent(matrix, rotation.energy, incumbent)) {
        ++parity_pruned;
        return 1;
    }
    correlate_group(x, rotations, 1, seed.epoch, &matrix, 1, 2);
    return finish_refine(seed.epoch, seed.hz, lo, hi, rotation.energy, matrix, out);
}

int delay_refine_parity(const float *x, const float *h, RefineRequest seed,
                        double lo, double hi, double incumbent, double out[4])
{
    if (!x || !h || !out || !(hi > lo)) return -1;
    if (!safe_request(seed) || !isfinite(incumbent) || !(incumbent > 0.) ||
        !__builtin_cpu_supports("avx2"))
        return delay_refine_bank(x, h, &seed, 1, lo, hi, (double (*)[4])out);
    return refine_one_parity(x, h, seed, lo, hi, incumbent, out);
}
