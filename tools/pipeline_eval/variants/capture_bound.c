/* Magnitude-only bound on the original physical folded normalized score. */
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

enum { LIMIT_TAPS = 64, BLOCKS = 4 };

int leo_capture_bound(const double *iq, size_t count, const double *reference,
    size_t ref_count, const ptrdiff_t *starts, const ptrdiff_t *ends, size_t symbols,
    const ptrdiff_t *offsets, size_t frames, size_t epochs, int per_tap, double *upper,
    uint64_t *support_sum, uint64_t *term_sum)
{
    if (!count || count > 200000 || !symbols || symbols > 22 || !frames || frames > 16
        || !epochs || epochs > 13334 || (per_tap != 0 && per_tap != 1)) return 1;
    int result = 1;
    double *prefix = malloc((count + 1) * sizeof(*prefix));
    double *amplitude = per_tap ? malloc(count * sizeof(*amplitude)) : NULL;
    uint16_t *support = calloc(epochs, sizeof(*support));
    if (!prefix || (per_tap && !amplitude) || !support) goto done;
    prefix[0] = 0;
    *support_sum = *term_sum = 0;
    for (size_t j = 0; j < count; ++j) {
        const double a = iq[2*j], b = iq[2*j+1];
        if (!isfinite(a) || !isfinite(b) || fabs(a) > 32768 || fabs(b) > 32768
            || a != trunc(a) || b != trunc(b)) goto done;
        const double power = a*a + b*b;
        prefix[j+1] = prefix[j] + power;
        if (per_tap) amplitude[j] = sqrt(power);
    }
    for (size_t e = 0; e < epochs; ++e) upper[e] = 0;
    for (size_t s = 0; s < symbols; ++s) {
        if (starts[s] < 0 || ends[s] <= starts[s] || (size_t)ends[s] > ref_count) goto done;
        const size_t taps = (size_t)(ends[s] - starts[s]);
        if (taps > LIMIT_TAPS || taps > count) goto done;
        double powers[LIMIT_TAPS + 1] = {0};
        double weight[LIMIT_TAPS] = {0};
        for (size_t t = 0; t < taps; ++t) {
            const size_t i = (size_t)starts[s] + t;
            const double a = reference[2*i], b = reference[2*i+1];
            if (!isfinite(a) || !isfinite(b) || fabs(a) > 16 || fabs(b) > 16) goto done;
            const double power = a*a + b*b;
            powers[t+1] = powers[t] + power;
            if (per_tap) weight[t] = sqrt(power);
        }
        if (powers[taps] < 1e-12) goto done;
        const size_t cut[BLOCKS + 1] = {0, taps/4, taps/2, (3*taps)/4, taps};
        if (!per_tap) {
            for (size_t b = 0; b < BLOCKS; ++b) {
                /* This interval is small. Sum directly to avoid cancellation. */
                double energy = 0;
                for (size_t t = cut[b]; t < cut[b+1]; ++t) {
                    const size_t i = (size_t)starts[s]+t;
                    energy += reference[2*i]*reference[2*i] + reference[2*i+1]*reference[2*i+1];
                }
                weight[b] = sqrt(energy);
            }
        }
        for (size_t f = 0; f < frames; ++f) {
            if (offsets[f] < 0 || (size_t)offsets[f] >= count) goto done;
            const size_t base = (size_t)starts[s]+(size_t)offsets[f];
            if (base+taps > count) break;
            const size_t valid = count + 1 - base - taps;
            const size_t end = valid < epochs ? valid : epochs;
            *support_sum += end;
            *term_sum += end*(per_tap ? taps : BLOCKS);
            for (size_t e = 0; e < end; ++e) {
                const size_t x = base+e;
                ++support[e];
                const double energy = prefix[x+taps]-prefix[x];
                if (energy == 0) continue;
                double sum = 0;
                if (per_tap) {
                    for (size_t t = 0; t < taps; ++t) sum += amplitude[x+t]*weight[t];
                } else {
                    for (size_t b = 0; b < BLOCKS; ++b) {
                        sum += sqrt(prefix[x+cut[b+1]]-prefix[x+cut[b]])*weight[b];
                    }
                }
                upper[e] += sum / sqrt(energy*powers[taps]);
            }
        }
    }
    for (size_t e = 0; e < epochs; ++e) {
        /* Audit allowance for the installed floating rotations and arithmetic.
         * The active detector only bypasses when the raw vector is exactly zero. */
        if (upper[e] > 0 && support[e]) upper[e] = upper[e] / support[e] + 1e-10;
    }
    result = 0;
done:
    free(support);
    free(amplitude);
    free(prefix);
    return result;
}
