#include "location.h"
#include "score_stencil_internal.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <new>
#include <vector>
#ifdef LEO_RESEARCH_SCORE_PROFILE
#include <chrono>
#include <cstdio>
#endif
#ifdef LEO_RESEARCH_HORIZON_PREFIX
#include "research/horizon_prefix.hpp"
#endif
#ifdef LEO_RESEARCH_HELDOUT_BOUND
#include "research/heldout_bound.hpp"
#endif
#ifdef LEO_RESEARCH_IMMUTABLE_ORBIT
#include "research/immutable_orbit.hpp"
#endif

namespace leo::location::internal {
#if defined(__GNUC__)
struct __attribute__((visibility("hidden"))) ScoreStencilScratch {
#else
struct ScoreStencilScratch {
#endif
    InterpolationStencil *stencils;
    size_t capacity;
    bool force_allocation_failure;

    ~ScoreStencilScratch() {
        delete[] stencils;
    }
};
}  // namespace leo::location::internal

#if defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wattributes"
#endif
struct leo_score_context {
    uint32_t max_observations;
    uint32_t max_taus;
    std::vector<double> residuals;
    leo::location::internal::ScoreStencilScratch *stencil_scratch;
#ifdef LEO_RESEARCH_BOUND_CACHE
    leo::location::research::BoundStateCache bound_cache;
#endif
#ifdef LEO_RESEARCH_ENDPOINT_BANK
    leo::location::research::EndpointStateBank endpoint_bank;
#endif
#ifdef LEO_RESEARCH_IMMUTABLE_ORBIT
    leo_orbit_snapshot immutable_snapshot{};
    bool immutable_enabled=false,immutable_bounded=false;
#endif
#if defined(LEO_RESEARCH_BOUND_CACHE) || defined(LEO_RESEARCH_ENDPOINT_BANK)
    leo_score_context():max_observations(0),max_taus(0),stencil_scratch(nullptr) {}
#endif
};
#if defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

namespace {
double dot3(const double *left, const double *right) {
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2];
}

bool finite3(const double *value) {
    return std::isfinite(value[0]) && std::isfinite(value[1]) && std::isfinite(value[2]);
}

bool valid_snapshot(const leo_orbit_snapshot *snapshot) {
    return snapshot != nullptr && snapshot->generation != 0 &&
        snapshot->satellite_count != 0 && snapshot->knot_count >= 2 &&
        snapshot->satellite_ids != nullptr && snapshot->states != nullptr &&
        std::isfinite(snapshot->knot_start_s) &&
        std::isfinite(snapshot->knot_step_s) && snapshot->knot_step_s > 0.0;
}

bool valid_config(const leo_score_config *config, uint32_t *tau_count = nullptr) {
    if (config == nullptr || !std::isfinite(config->carrier_hz) ||
        !std::isfinite(config->speed_of_light_km_s) ||
        !std::isfinite(config->unmatched_penalty_hz) || config->carrier_hz <= 0.0 ||
        config->speed_of_light_km_s <= 0.0 || config->unmatched_penalty_hz <= 0.0 ||
        config->tau_step_s <= 0 || config->tau_last_s < config->tau_first_s) {
        return false;
    }
    const int64_t span = static_cast<int64_t>(config->tau_last_s) - config->tau_first_s;
    if (span % config->tau_step_s != 0) {
        return false;
    }
    const int64_t count = span / config->tau_step_s + 1;
    if (count <= 0 || count > 1024) {
        return false;
    }
    if (tau_count != nullptr) {
        *tau_count = static_cast<uint32_t>(count);
    }
    return true;
}

leo_location_status interpolate(
    const leo_orbit_snapshot *snapshot,
    uint32_t satellite,
    double time_s,
    leo_orbit_state *state) {
    return leo_orbit_interpolate(snapshot, satellite, time_s, state);
}

bool satellite_track_possible(
    const leo_orbit_snapshot *snapshot,
    uint32_t satellite,
    const leo_location_track &track,
    const leo_location_site &site,
    const leo_score_config &config) {
    int lo = static_cast<int>(std::floor(
        (track.times_s[0] + config.tau_first_s - snapshot->knot_start_s) /
        snapshot->knot_step_s));
    int hi = static_cast<int>(std::floor(
        (track.times_s[track.observation_count - 1] + config.tau_last_s -
         snapshot->knot_start_s) / snapshot->knot_step_s));
    lo = std::max(lo, 0);
    hi = std::min(hi, static_cast<int>(snapshot->knot_count) - 2);
    const double plane = dot3(site.ecef_km, site.up);
    for (int knot = lo; knot <= hi; ++knot) {
        const leo_orbit_state &a = snapshot->states[
            static_cast<size_t>(satellite) * snapshot->knot_count + knot];
        const leo_orbit_state &b = snapshot->states[
            static_cast<size_t>(satellite) * snapshot->knot_count + knot + 1];
        const double x = dot3(a.position_km, site.up) - plane;
        const double y = dot3(b.position_km, site.up) - plane;
        if (x >= 0.0 || y >= 0.0 ||
            x + snapshot->knot_step_s * dot3(a.velocity_km_s, site.up) / 3.0 >= 0.0 ||
            y - snapshot->knot_step_s * dot3(b.velocity_km_s, site.up) / 3.0 >= 0.0) {
            return true;
        }
    }
    return false;
}

bool better(const leo_track_score &candidate, const leo_track_score &current) {
    if (!candidate.matched) {
        return false;
    }
    if (!current.matched) {
        return true;
    }
    if (candidate.heldout_rms_hz != current.heldout_rms_hz) {
        return candidate.heldout_rms_hz < current.heldout_rms_hz;
    }
    if (candidate.training_rms_hz != current.training_rms_hz) {
        return candidate.training_rms_hz < current.training_rms_hz;
    }
    return candidate.candidate_id < current.candidate_id;
}
}  // namespace

#ifdef LEO_RESEARCH_IMMUTABLE_ORBIT
namespace leo::location::research {
bool bind_immutable_orbit(leo_score_context* context,const leo_orbit_snapshot* snapshot) {
    if(!context)return false;
    context->immutable_enabled=false;context->endpoint_bank.invalidate();
    if(!snapshot)return true;
    if(!valid_snapshot(snapshot))return false;
    context->immutable_snapshot=*snapshot;
    context->immutable_bounded=bounded_orbit_partition(*snapshot);
    context->immutable_enabled=true;return true;
}
bool immutable_orbit_matches(const leo_score_context* context,const leo_orbit_snapshot* s) {
    if(!context || !s || !context->immutable_enabled)return false;
    const auto& a=context->immutable_snapshot;
    return a.generation==s->generation && a.start_utc_ns==s->start_utc_ns &&
        a.knot_start_s==s->knot_start_s && a.knot_step_s==s->knot_step_s &&
        a.knot_count==s->knot_count && a.satellite_count==s->satellite_count &&
        a.states==s->states && a.satellite_ids==s->satellite_ids;
}
}
#endif

namespace leo::location::internal {
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
    return interpolate_with_prevalidated_stencil(snapshot,satellite_index,stencil,state);
}

leo_location_status interpolate_with_prevalidated_stencil(
    const leo_orbit_snapshot *snapshot,uint32_t satellite_index,
    const InterpolationStencil *stencil,leo_orbit_state *state) {
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

void force_stencil_allocation_failure_for_test(leo_score_context *context, bool force) {
    if (context != nullptr && context->stencil_scratch != nullptr) {
        context->stencil_scratch->force_allocation_failure = force;
    }
}

size_t stencil_capacity_for_test(const leo_score_context *context) {
    return context == nullptr || context->stencil_scratch == nullptr
        ? 0
        : context->stencil_scratch->capacity;
}
}  // namespace leo::location::internal

extern "C" leo_score_context *leo_score_context_create(
    uint32_t max_observations, uint32_t max_taus) {
    if (max_observations < 6 || max_observations > 100000 || max_taus == 0 ||
        max_taus > 1024) {
        return nullptr;
    }
    leo_score_context *context = nullptr;
    try {
        context = new leo_score_context{};
        context->stencil_scratch = new leo::location::internal::ScoreStencilScratch{};
        context->max_observations = max_observations;
        context->max_taus = max_taus;
        context->residuals.resize(max_observations);
        return context;
    } catch (...) {
        if (context != nullptr) {
            delete context->stencil_scratch;
            delete context;
        }
        return nullptr;
    }
}

extern "C" void leo_score_context_destroy(leo_score_context *context) {
    if (context != nullptr) {
        delete context->stencil_scratch;
    }
    delete context;
}

extern "C" leo_score_config leo_score_default_config(void) {
    return leo_score_config{11200000000.0, 299792.458, 800.0, -5, 5, 1};
}

extern "C" leo_location_status leo_score_validate_inputs(
    const leo_orbit_snapshot *snapshot,
    const leo_location_track *tracks,
    uint32_t track_count,
    const leo_location_site *site,
    const leo_score_config *config) {
    if (!valid_snapshot(snapshot) || tracks == nullptr || track_count == 0 || site == nullptr ||
        !finite3(site->ecef_km) || !finite3(site->up) || dot3(site->up, site->up) <= 0.0 ||
        !valid_config(config)) {
        return LEO_LOCATION_INVALID;
    }
    const double first = snapshot->knot_start_s;
    const double last = first + snapshot->knot_step_s * (snapshot->knot_count - 1);
    for (uint32_t track_index = 0; track_index < track_count; ++track_index) {
        const leo_location_track &track = tracks[track_index];
        if (track.observation_count < 6 || track.weight_s == 0 || track.times_s == nullptr ||
            track.measured_hz == nullptr || track.training_mask == nullptr) {
            return LEO_LOCATION_INVALID;
        }
        uint32_t training = 0;
        for (uint32_t observation = 0; observation < track.observation_count; ++observation) {
            if (!std::isfinite(track.times_s[observation]) ||
                !std::isfinite(track.measured_hz[observation]) ||
                track.training_mask[observation] > 1 ||
                (observation != 0 &&
                 track.times_s[observation] < track.times_s[observation - 1])) {
                return LEO_LOCATION_INVALID;
            }
            training += track.training_mask[observation];
        }
        if (training == 0 || training == track.observation_count ||
            track.times_s[0] + config->tau_first_s < first ||
            track.times_s[track.observation_count - 1] + config->tau_last_s > last) {
            return LEO_LOCATION_INVALID;
        }
    }
    return LEO_LOCATION_OK;
}

extern "C" void leo_track_scores_clear(leo_track_score *scores, uint32_t track_count) {
    if (scores == nullptr) {
        return;
    }
    for (uint32_t index = 0; index < track_count; ++index) {
        scores[index] = leo_track_score{
            0, 0, 0,
            std::numeric_limits<double>::infinity(),
            std::numeric_limits<double>::infinity(),
            0.0,
        };
    }
}

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
    leo_score_stats local_stats{};
#ifdef LEO_RESEARCH_SCORE_PROFILE
    using ProfileClock=std::chrono::steady_clock;
    const auto profile_begin=ProfileClock::now();
    double profile_bound_s=0;uint64_t profile_rejected=0,profile_full=0;
#endif
#ifdef LEO_RESEARCH_HORIZON_PREFIX
    leo::location::research::HorizonPrefix horizon;
    const bool use_horizon=horizon.build(*snapshot,*site,satellite_begin,satellite_end);
#endif
#ifdef LEO_RESEARCH_HELDOUT_BOUND
#ifdef LEO_RESEARCH_IMMUTABLE_ORBIT
    const bool immutable=leo::location::research::immutable_orbit_matches(context,snapshot);
#else
    const bool immutable=false;
#endif
    const bool allow_bound=
#ifdef LEO_RESEARCH_IMMUTABLE_ORBIT
        immutable ? context->immutable_bounded && leo::location::research::bounded_site(*site,*config) :
#endif
        leo::location::research::bounded_snapshot(*snapshot,*site,*config,satellite_begin,satellite_end);
#ifdef LEO_RESEARCH_ENDPOINT_BANK
    // Single-satellite warm-start calls neither use nor invalidate the bank.
    const bool use_endpoint_bank=allow_bound && satellite_end-satellite_begin>1 &&
        context->endpoint_bank.prepare(*snapshot,tracks,track_count,*config,satellite_begin,satellite_end,immutable);
#endif
#ifdef LEO_RESEARCH_BOUND_CACHE
    const bool use_bound_cache=context->bound_cache.prepare(*snapshot,satellite_begin,satellite_end);
#endif
#endif
#ifdef LEO_RESEARCH_SCORE_PROFILE
    const double profile_setup_s=std::chrono::duration<double>(ProfileClock::now()-profile_begin).count();
#endif
#ifdef LEO_RESEARCH_VECTOR_PAIR_BOUND
    const auto packed_site=leo::location::research::pack_site(*site,-config->carrier_hz/config->speed_of_light_km_s);
#endif
    for (uint32_t track_index = 0; track_index < track_count; ++track_index) {
        const leo_location_track &track = tracks[track_index];
        uint32_t training_count = 0;
        for (uint32_t observation = 0; observation < track.observation_count; ++observation) {
            training_count += track.training_mask[observation];
        }
        const uint32_t heldout_count = track.observation_count - training_count;
#ifdef LEO_RESEARCH_PLANNED_BOUND
        const auto bound_subset=leo::location::research::select_subset(track,heldout_count);
#endif
#ifdef LEO_RESEARCH_HORIZON_PREFIX
        const auto horizon_range=use_horizon?horizon.range(*snapshot,track,*config):
            leo::location::research::HorizonPrefix::Range{};
#endif
        bool stencils_ready = false;
        bool use_stencils = false;
        for (uint32_t satellite = satellite_begin; satellite < satellite_end; ++satellite) {
            if (!(
#ifdef LEO_RESEARCH_HORIZON_PREFIX
                use_horizon?horizon.possible(satellite,horizon_range):
#endif
                satellite_track_possible(snapshot, satellite, track, *site, *config))) {
                ++local_stats.rejected_satellite_tracks;
                continue;
            }
            if (!stencils_ready) {
                stencils_ready = true;
                const size_t needed = static_cast<size_t>(track.observation_count) * tau_count;
                use_stencils = !context->stencil_scratch->force_allocation_failure &&
                    needed <= leo::location::internal::kMaximumInterpolationStencils;
                if (use_stencils && needed > context->stencil_scratch->capacity) {
                    delete[] context->stencil_scratch->stencils;
                    context->stencil_scratch->stencils = nullptr;
                    context->stencil_scratch->capacity = 0;
                    try {
                        context->stencil_scratch->stencils =
                            new leo::location::internal::InterpolationStencil[needed];
                        context->stencil_scratch->capacity = needed;
                    } catch (...) {
                        use_stencils = false;
                    }
                }
                if (use_stencils) {
                    for (uint32_t tau_index = 0; tau_index < tau_count; ++tau_index) {
                        const int32_t tau = config->tau_first_s +
                            static_cast<int32_t>(tau_index) * config->tau_step_s;
                        for (uint32_t observation = 0;
                             observation < track.observation_count;
                             ++observation) {
                            if (leo::location::internal::build_interpolation_stencil(
                                    snapshot,
                                    track.times_s[observation] + tau,
                                    &context->stencil_scratch->stencils[
                                        static_cast<size_t>(tau_index) *
                                            track.observation_count +
                                        observation]) != LEO_LOCATION_OK) {
                                return LEO_LOCATION_ORBIT_ERROR;
                            }
                        }
                    }
                }
            }
            ++local_stats.evaluated_satellite_tracks;
#ifdef LEO_RESEARCH_HELDOUT_BOUND
#ifdef LEO_RESEARCH_SCORE_PROFILE
            const auto bound_begin=ProfileClock::now();
#endif
            const bool bound_rejected=allow_bound && leo::location::research::cannot_win(*snapshot,satellite,track,*site,
                *config,heldout_count,scores[track_index]
#ifdef LEO_RESEARCH_PLANNED_BOUND
                ,&bound_subset,use_stencils?context->stencil_scratch->stencils:nullptr
#ifdef LEO_RESEARCH_BOUND_CACHE
                ,use_bound_cache?&context->bound_cache:nullptr
#elif defined(LEO_RESEARCH_ENDPOINT_BANK)
                ,nullptr
#endif
#ifdef LEO_RESEARCH_ENDPOINT_BANK
                ,use_endpoint_bank?context->endpoint_bank.block(track_index,satellite):nullptr
#ifdef LEO_RESEARCH_IMMUTABLE_ORBIT
                ,immutable && allow_bound
#ifdef LEO_RESEARCH_VECTOR_PAIR_BOUND
                ,&packed_site
#endif
#endif
#endif
#endif
                );
#ifdef LEO_RESEARCH_SCORE_PROFILE
            profile_bound_s+=std::chrono::duration<double>(ProfileClock::now()-bound_begin).count();
            profile_rejected+=bound_rejected;
#endif
            if(bound_rejected) continue;
#endif
#ifdef LEO_RESEARCH_SCORE_PROFILE
            ++profile_full;
#endif
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
                    const leo_location_status interpolation_status = use_stencils
                        ?
#ifdef LEO_RESEARCH_IMMUTABLE_ORBIT
                          (immutable && allow_bound
                              ? leo::location::internal::interpolate_with_prevalidated_stencil
                              : leo::location::internal::interpolate_with_stencil)(
#else
                          leo::location::internal::interpolate_with_stencil(
#endif
                              snapshot,
                              satellite,
                              &context->stencil_scratch->stencils[
                                  static_cast<size_t>(tau_index) * track.observation_count +
                                  observation],
                              &state)
                        : interpolate(
                              snapshot,
                              satellite,
                              track.times_s[observation] + tau,
                              &state);
                    if (interpolation_status != LEO_LOCATION_OK) {
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
#ifdef LEO_RESEARCH_SCORE_PROFILE
    std::fprintf(stderr,"{\"kind\":\"score_partition_profile\",\"begin\":%u,\"end\":%u,\"tracks\":%u,\"setup_s\":%.17g,\"bound_s\":%.17g,\"bound_rejected\":%llu,\"fully_scored\":%llu,\"wall_s\":%.17g}\n",
        satellite_begin,satellite_end,track_count,profile_setup_s,profile_bound_s,
        static_cast<unsigned long long>(profile_rejected),static_cast<unsigned long long>(profile_full),
        std::chrono::duration<double>(ProfileClock::now()-profile_begin).count());
#endif
    return LEO_LOCATION_OK;
}

extern "C" leo_location_status leo_track_scores_reduce(
    leo_track_score *destination,
    const leo_track_score *source,
    uint32_t track_count) {
    if (destination == nullptr || source == nullptr || track_count == 0) {
        return LEO_LOCATION_INVALID;
    }
    for (uint32_t index = 0; index < track_count; ++index) {
        if (better(source[index], destination[index])) {
            destination[index] = source[index];
        }
    }
    return LEO_LOCATION_OK;
}

extern "C" leo_location_status leo_point_score_finish(
    const leo_location_track *tracks,
    uint32_t track_count,
    const leo_track_score *scores,
    const leo_score_config *config,
    leo_point_score *point_score) {
    if (tracks == nullptr || track_count == 0 || scores == nullptr || point_score == nullptr ||
        !valid_config(config)) {
        return LEO_LOCATION_INVALID;
    }
    double loss = 0.0;
    uint64_t weight = 0;
    uint32_t matched = 0;
    for (uint32_t index = 0; index < track_count; ++index) {
        if (tracks[index].weight_s == 0) {
            return LEO_LOCATION_INVALID;
        }
        const double heldout = scores[index].matched ? scores[index].heldout_rms_hz
                                                     : config->unmatched_penalty_hz;
        if (!std::isfinite(heldout)) {
            return LEO_LOCATION_INVALID;
        }
        const double capped = std::min(heldout, config->unmatched_penalty_hz);
        loss += tracks[index].weight_s * capped * capped;
        weight += tracks[index].weight_s;
        matched += scores[index].matched != 0;
    }
    if (weight == 0 || !std::isfinite(loss)) {
        return LEO_LOCATION_INVALID;
    }
    point_score->weighted_mse_hz2 = loss / static_cast<double>(weight);
    point_score->residual_rmse_hz = std::sqrt(point_score->weighted_mse_hz2);
    point_score->matched_track_count = matched;
    point_score->unmatched_track_count = track_count - matched;
    return LEO_LOCATION_OK;
}
