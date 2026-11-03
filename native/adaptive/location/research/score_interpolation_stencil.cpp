#include "score_interpolation_stencil.hpp"

#include <cmath>
#include <limits>
#include <new>
#include <vector>

/* Compile the production scorer unchanged, but retain its partition entry
 * point as an in-process oracle. All other public definitions remain the same.
 * This research translation unit is used instead of score.cpp, never with it. */
#define leo_score_partition leo_score_partition_reference_research
#include "score_baseline_20260930.cpp"
#undef leo_score_partition

namespace leo::location::research {
namespace {
bool valid_stencil_snapshot(const leo_orbit_snapshot *snapshot) {
    if (!valid_snapshot(snapshot)) {
        return false;
    }
    const double end = snapshot->knot_start_s +
        snapshot->knot_step_s * static_cast<double>(snapshot->knot_count - 1);
    return std::isfinite(end);
}

bool finite_state(const leo_orbit_state &state) {
    for (unsigned component = 0; component < 3; ++component) {
        if (!std::isfinite(state.position_km[component]) ||
            !std::isfinite(state.velocity_km_s[component])) {
            return false;
        }
    }
    return true;
}
}  // namespace

leo_location_status build_interpolation_stencil(
    const leo_orbit_snapshot *snapshot,
    double relative_time_s,
    InterpolationStencil *stencil) {
    if (!valid_stencil_snapshot(snapshot) || stencil == nullptr ||
        !std::isfinite(relative_time_s)) {
        return LEO_LOCATION_INVALID;
    }
    const double coordinate =
        (relative_time_s - snapshot->knot_start_s) / snapshot->knot_step_s;
    if (coordinate < 0.0 || coordinate > static_cast<double>(snapshot->knot_count - 1)) {
        return LEO_LOCATION_INVALID;
    }
    uint32_t index = static_cast<uint32_t>(std::floor(coordinate));
    if (index >= snapshot->knot_count - 1) {
        index = snapshot->knot_count - 2;
    }
    const double u = coordinate - index;
    const double u2 = u * u;
    const double u3 = u2 * u;
    const double step = snapshot->knot_step_s;
    *stencil = InterpolationStencil{
        index,
        2.0 * u3 - 3.0 * u2 + 1.0,
        (u3 - 2.0 * u2 + u) * step,
        -2.0 * u3 + 3.0 * u2,
        (u3 - u2) * step,
        6.0 * u2 - 6.0 * u,
        -6.0 * u2 + 6.0 * u,
        3.0 * u2 - 4.0 * u + 1.0,
        3.0 * u2 - 2.0 * u,
    };
    return LEO_LOCATION_OK;
}

leo_location_status interpolate_with_stencil(
    const leo_orbit_snapshot *snapshot,
    uint32_t satellite_index,
    const InterpolationStencil *stencil,
    leo_orbit_state *state) {
    if (!valid_stencil_snapshot(snapshot) || stencil == nullptr || state == nullptr ||
        satellite_index >= snapshot->satellite_count ||
        stencil->knot_index >= snapshot->knot_count - 1) {
        return LEO_LOCATION_INVALID;
    }
    const leo_orbit_state &a = snapshot->states[
        static_cast<size_t>(satellite_index) * snapshot->knot_count + stencil->knot_index];
    const leo_orbit_state &b = snapshot->states[
        static_cast<size_t>(satellite_index) * snapshot->knot_count + stencil->knot_index + 1];
    const double step = snapshot->knot_step_s;
    for (unsigned component = 0; component < 3; ++component) {
        state->position_km[component] =
            stencil->position_a * a.position_km[component] +
            stencil->position_a_velocity * a.velocity_km_s[component] +
            stencil->position_b * b.position_km[component] +
            stencil->position_b_velocity * b.velocity_km_s[component];
        state->velocity_km_s[component] =
            (stencil->velocity_a_position * a.position_km[component] +
             stencil->velocity_b_position * b.position_km[component]) / step +
            stencil->velocity_a * a.velocity_km_s[component] +
            stencil->velocity_b * b.velocity_km_s[component];
    }
    return finite_state(*state) ? LEO_LOCATION_OK : LEO_LOCATION_ORBIT_ERROR;
}

}  // namespace leo::location::research

extern "C" leo_location_status leo_score_partition(
    leo_score_context *context,
    const leo_orbit_snapshot *snapshot,
    const leo_location_track *tracks,
    uint32_t track_count,
    const leo_location_site *site,
    const leo_score_config *config,
    uint32_t satellite_begin,
    uint32_t satellite_end,
    leo_track_score *scores,
    leo_score_stats *stats) {
    uint32_t tau_count = 0;
    if (context == nullptr || scores == nullptr ||
        leo_score_validate_inputs(snapshot, tracks, track_count, site, config) != LEO_LOCATION_OK ||
        !valid_config(config, &tau_count) || tau_count > context->max_taus ||
        satellite_begin > satellite_end || satellite_end > snapshot->satellite_count) {
        return LEO_LOCATION_INVALID;
    }
    for (uint32_t track_index = 0; track_index < track_count; ++track_index) {
        if (tracks[track_index].observation_count > context->max_observations) {
            return LEO_LOCATION_CAPACITY;
        }
    }

    std::vector<leo::location::research::InterpolationStencil> stencils;
    leo_score_stats local_stats{};
    for (uint32_t track_index = 0; track_index < track_count; ++track_index) {
        const leo_location_track &track = tracks[track_index];
        uint32_t training_count = 0;
        for (uint32_t observation = 0; observation < track.observation_count; ++observation) {
            training_count += track.training_mask[observation];
        }
        const uint32_t heldout_count = track.observation_count - training_count;

        bool stencils_ready = false;
        for (uint32_t satellite = satellite_begin; satellite < satellite_end; ++satellite) {
            if (!satellite_track_possible(snapshot, satellite, track, *site, *config)) {
                ++local_stats.rejected_satellite_tracks;
                continue;
            }
            if (!stencils_ready) {
                try {
                    stencils.resize(static_cast<size_t>(track.observation_count) * tau_count);
                } catch (...) {
                    return LEO_LOCATION_CAPACITY;
                }
                for (uint32_t tau_index = 0; tau_index < tau_count; ++tau_index) {
                    const int32_t tau = config->tau_first_s +
                        static_cast<int32_t>(tau_index) * config->tau_step_s;
                    for (uint32_t observation = 0; observation < track.observation_count;
                         ++observation) {
                        if (leo::location::research::build_interpolation_stencil(
                                snapshot,
                                track.times_s[observation] + tau,
                                &stencils[static_cast<size_t>(tau_index) *
                                              track.observation_count +
                                          observation]) != LEO_LOCATION_OK) {
                            return LEO_LOCATION_ORBIT_ERROR;
                        }
                    }
                }
                stencils_ready = true;
            }
            ++local_stats.evaluated_satellite_tracks;
            bool visible = false;
            double best_training = std::numeric_limits<double>::infinity();
            double best_heldout = std::numeric_limits<double>::infinity();
            double best_offset = 0.0;
            int32_t best_tau = config->tau_first_s;
            for (uint32_t tau_index = 0; tau_index < tau_count; ++tau_index) {
                const int32_t tau = config->tau_first_s +
                    static_cast<int32_t>(tau_index) * config->tau_step_s;
                double offset = 0.0;
                for (uint32_t observation = 0; observation < track.observation_count;
                     ++observation) {
                    leo_orbit_state state{};
                    if (leo::location::research::interpolate_with_stencil(
                            snapshot,
                            satellite,
                            &stencils[static_cast<size_t>(tau_index) * track.observation_count +
                                      observation],
                            &state) != LEO_LOCATION_OK) {
                        return LEO_LOCATION_ORBIT_ERROR;
                    }
                    double delta[3];
                    for (unsigned component = 0; component < 3; ++component) {
                        delta[component] =
                            state.position_km[component] - site->ecef_km[component];
                    }
                    if (dot3(delta, site->up) >= 0.0) {
                        visible = true;
                    }
                    const double range2 = dot3(delta, delta);
                    if (!(range2 > 0.0) || !std::isfinite(range2)) {
                        return LEO_LOCATION_ORBIT_ERROR;
                    }
                    const double predicted = -config->carrier_hz /
                        config->speed_of_light_km_s * dot3(delta, state.velocity_km_s) /
                        std::sqrt(range2);
                    const double residual = track.measured_hz[observation] - predicted;
                    context->residuals[observation] = residual;
                    if (track.training_mask[observation]) {
                        offset += residual;
                    }
                }
                offset /= training_count;
                double training_sum = 0.0;
                double heldout_sum = 0.0;
                for (uint32_t observation = 0; observation < track.observation_count;
                     ++observation) {
                    const double error = context->residuals[observation] - offset;
                    if (track.training_mask[observation]) {
                        training_sum += error * error;
                    } else {
                        heldout_sum += error * error;
                    }
                }
                const double training_rms = std::sqrt(training_sum / training_count);
                const double heldout_rms = std::sqrt(heldout_sum / heldout_count);
                if (training_rms < best_training) {
                    best_training = training_rms;
                    best_heldout = heldout_rms;
                    best_offset = offset;
                    best_tau = tau;
                }
            }
            const leo_track_score candidate{
                static_cast<uint8_t>(visible),
                snapshot->satellite_ids[satellite],
                best_tau,
                best_heldout,
                best_training,
                best_offset,
            };
            if (better(candidate, scores[track_index])) {
                scores[track_index] = candidate;
            }
        }
    }
    if (stats != nullptr) {
        *stats = local_stats;
    }
    return LEO_LOCATION_OK;
}
