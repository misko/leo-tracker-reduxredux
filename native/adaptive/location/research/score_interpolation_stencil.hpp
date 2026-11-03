#ifndef LEO_ADAPTIVE_LOCATION_RESEARCH_SCORE_INTERPOLATION_STENCIL_HPP
#define LEO_ADAPTIVE_LOCATION_RESEARCH_SCORE_INTERPOLATION_STENCIL_HPP

#include "location.h"

#include <cstdint>

/* Research-only implementation surface. This header is not part of the
 * location C ABI and is never included by the production build. */
namespace leo::location::research {

struct InterpolationStencil {
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

leo_location_status build_interpolation_stencil(
    const leo_orbit_snapshot *snapshot,
    double relative_time_s,
    InterpolationStencil *stencil);

leo_location_status interpolate_with_stencil(
    const leo_orbit_snapshot *snapshot,
    uint32_t satellite_index,
    const InterpolationStencil *stencil,
    leo_orbit_state *state);

}  // namespace leo::location::research

/* The research object retains the unmodified scorer under this symbol so one
 * process can compare it directly with the candidate implementation. */
extern "C" leo_location_status leo_score_partition_reference_research(
    leo_score_context *context,
    const leo_orbit_snapshot *snapshot,
    const leo_location_track *tracks,
    uint32_t track_count,
    const leo_location_site *site,
    const leo_score_config *config,
    uint32_t satellite_begin,
    uint32_t satellite_end,
    leo_track_score *scores,
    leo_score_stats *stats);

#endif
