/* One post-coarse crossing per antenna evaluation in the original scanner. */
#include "portable_verifier.h"

int verifier_integration_batch(PortableVerifier *workspace, const int16_t *new_stereo_iq,
                               unsigned lane, const PortableVerifierSeed *seeds,
                               unsigned count, double center, double minimum, double maximum,
                               PortableVerifierResult *results) {
    if (lane > 1 || (new_stereo_iq && portable_verifier_load(workspace, new_stereo_iq, lane)))
        return -1;
    if (portable_verifier_acquire(workspace, seeds, count, center, minimum, maximum, results))
        return -1;
    for (unsigned rank = 0; rank < count; ++rank) {
        unsigned index = results[rank].seed_index;
        if (index >= count || portable_verifier_glrt(workspace, seeds[index].epoch, &results[rank]))
            return -1;
    }
    return 0;
}
