#ifndef LEO_ADAPTIVE_LOCATION_SCORE_STENCIL_INTERNAL_HPP
#define LEO_ADAPTIVE_LOCATION_SCORE_STENCIL_INTERNAL_HPP

#include "location.h"

#include <cstddef>
#include <cstdint>

/* Private component surface. It is not part of the location C ABI. */
namespace leo::location::internal {

#if defined(__GNUC__)
#define LEO_LOCATION_INTERNAL_VISIBILITY __attribute__((visibility("hidden")))
#else
#define LEO_LOCATION_INTERNAL_VISIBILITY
#endif

struct LEO_LOCATION_INTERNAL_VISIBILITY InterpolationStencil {
    uint32_t knot_index;
    double position_a;
    double position_a_velocity;
    double position_b;
    double position_b_velocity;
    double velocity_a_position;
    double velocity_b_position;
    double velocity_a;
    double velocity_b;
};

constexpr size_t kMaximumInterpolationStencils = 16384;

LEO_LOCATION_INTERNAL_VISIBILITY leo_location_status build_interpolation_stencil(
    const leo_orbit_snapshot *snapshot,
    double relative_time_s,
    InterpolationStencil *stencil);

LEO_LOCATION_INTERNAL_VISIBILITY leo_location_status interpolate_with_stencil(
    const leo_orbit_snapshot *snapshot,
    uint32_t satellite_index,
    const InterpolationStencil *stencil,
    leo_orbit_state *state);

/* Private fast path for scorer-owned stencils constructed against a validated,
 * unchanged snapshot. Pointers, satellite index and knot index must already be
 * checked. Arithmetic and output finiteness checks are identical to the checked
 * entry point. Never use for caller-supplied stencils or mutable snapshots. */
LEO_LOCATION_INTERNAL_VISIBILITY leo_location_status interpolate_with_prevalidated_stencil(
    const leo_orbit_snapshot*, uint32_t, const InterpolationStencil*, leo_orbit_state*);

/* Component-test fault injection. A forced failure takes the same generic
 * interpolation fallback as an allocation failure. */
LEO_LOCATION_INTERNAL_VISIBILITY void force_stencil_allocation_failure_for_test(
    leo_score_context *context, bool force);
LEO_LOCATION_INTERNAL_VISIBILITY size_t stencil_capacity_for_test(
    const leo_score_context *context);

#undef LEO_LOCATION_INTERNAL_VISIBILITY

}  // namespace leo::location::internal

#endif
