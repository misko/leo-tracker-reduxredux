#ifndef LEO_ADAPTIVE_CORRECTED_GEOMETRY_HPP
#define LEO_ADAPTIVE_CORRECTED_GEOMETRY_HPP

#include "../scanner/scanner_profile.h"
#include <array>
#include <cstdint>

namespace leo::adaptive::application {

struct CorrectedTargetGeometry {
    std::uint32_t target_key{};
    std::uint64_t tuned_if_hz{};
    std::array<double, 2> pilot_if_hz{};
    double template_min_hz{}, template_max_hz{};
};

/* Composition-owned immutable authority. Pilot IF and template extents must
 * come from the maintained signal contract, never from detector answers.
 * The manifest binds their derivation, including RF/LO calibration. */
struct CorrectedGeometryProfile {
    std::array<std::uint8_t, 32> manifest_digest{};
    std::uint32_t sample_rate_hz{7500000};
    std::uint32_t bandwidth_hz{7500000};
    double policy_half_width_hz{800000};
    std::uint32_t target_count{};
    std::array<CorrectedTargetGeometry, LEO_SCANNER_MAX_TARGETS> targets{};
};

/* Borrow profile unchanged until scanner drain completes. Output is committed
 * only on success; the callback retains no visit or output pointers. */
int derive_corrected_geometry(void* profile,
    const leo_scanner_visit_authority* visit,
    leo_scanner_detector_geometry* output);

}
#endif
