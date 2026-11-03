#include "location.h"
#include "score_stencil_internal.hpp"

#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <utility>
#include <vector>

namespace {
static_assert(sizeof(leo::location::internal::InterpolationStencil) == 72);
static_assert(
    leo::location::internal::kMaximumInterpolationStencils *
            sizeof(leo::location::internal::InterpolationStencil) ==
        1179648);

uint64_t bits(double value) {
    uint64_t result = 0;
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

void assert_state_exact(const leo_orbit_state &left, const leo_orbit_state &right) {
    for (unsigned component = 0; component < 3; ++component) {
        assert(bits(left.position_km[component]) == bits(right.position_km[component]));
        assert(bits(left.velocity_km_s[component]) == bits(right.velocity_km_s[component]));
    }
}

void assert_score_exact(const leo_track_score &left, const leo_track_score &right) {
    assert(left.matched == right.matched);
    assert(left.candidate_id == right.candidate_id);
    assert(left.tau_s == right.tau_s);
    assert(bits(left.heldout_rms_hz) == bits(right.heldout_rms_hz));
    assert(bits(left.training_rms_hz) == bits(right.training_rms_hz));
    assert(bits(left.frequency_offset_hz) == bits(right.frequency_offset_hz));
}

leo_orbit_snapshot make_snapshot(leo_orbit_state *states, const int32_t *ids) {
    for (unsigned satellite = 0; satellite < 2; ++satellite) {
        for (unsigned knot = 0; knot < 4; ++knot) {
            leo_orbit_state &state = states[satellite * 4 + knot];
            state.position_km[0] = 7000.125 + 7.25 * satellite + 0.375 * knot;
            state.position_km[1] = -1200.5 + 3.125 * knot - 1.5 * satellite;
            state.position_km[2] = 800.25 - 2.75 * knot + 0.625 * satellite;
            state.velocity_km_s[0] = 0.015625 + 0.00125 * knot;
            state.velocity_km_s[1] = 7.375 - 0.025 * knot + 0.0125 * satellite;
            state.velocity_km_s[2] = -1.125 + 0.03125 * knot;
        }
    }
    return leo_orbit_snapshot{17, 0, -10.0, 10.0, 2, 4, ids, states};
}

void test_interpolation_matches_generic_oracle() {
    const int32_t ids[2] = {101, 202};
    leo_orbit_state states[8]{};
    const leo_orbit_snapshot snapshot = make_snapshot(states, ids);
    const double times[] = {
        -10.0,
        std::nextafter(-10.0, 0.0),
        -5.125,
        0.0,
        7.25,
        std::nextafter(20.0, 0.0),
        20.0,
    };
    for (double time : times) {
        leo::location::internal::InterpolationStencil stencil{};
        assert(leo::location::internal::build_interpolation_stencil(
                   &snapshot, time, &stencil) == LEO_LOCATION_OK);
        for (uint32_t satellite = 0; satellite < 2; ++satellite) {
            leo_orbit_state generic{};
            leo_orbit_state planned{};
            assert(leo_orbit_interpolate(&snapshot, satellite, time, &generic) ==
                   LEO_LOCATION_OK);
            assert(leo::location::internal::interpolate_with_stencil(
                       &snapshot, satellite, &stencil, &planned) == LEO_LOCATION_OK);
            assert_state_exact(planned, generic);
        }
    }
}

void test_interpolation_boundaries_and_errors() {
    const int32_t ids[2] = {101, 202};
    leo_orbit_state states[8]{};
    leo_orbit_snapshot snapshot = make_snapshot(states, ids);
    const double invalid_times[] = {
        std::nextafter(-10.0, -std::numeric_limits<double>::infinity()),
        std::nextafter(20.0, std::numeric_limits<double>::infinity()),
        std::numeric_limits<double>::quiet_NaN(),
        std::numeric_limits<double>::infinity(),
    };
    for (double time : invalid_times) {
        leo::location::internal::InterpolationStencil stencil{};
        leo_orbit_state ignored{};
        assert(leo::location::internal::build_interpolation_stencil(
                   &snapshot, time, &stencil) ==
               leo_orbit_interpolate(&snapshot, 0, time, &ignored));
    }

    leo_orbit_snapshot overflow = snapshot;
    overflow.knot_start_s = std::numeric_limits<double>::max();
    overflow.knot_step_s = std::numeric_limits<double>::max();
    leo::location::internal::InterpolationStencil ignored_stencil{};
    leo_orbit_state ignored_state{};
    assert(leo::location::internal::build_interpolation_stencil(
               &overflow, overflow.knot_start_s, &ignored_stencil) ==
           leo_orbit_interpolate(&overflow, 0, overflow.knot_start_s, &ignored_state));

    const int32_t rounding_id = 1;
    leo_orbit_state rounding_state{};
    const double rounding_start = -3.3601233514182593e-07;
    const double rounding_step = 6.357645875743825e-11;
    const uint32_t rounding_knots = 150;
    const double rounding_end =
        rounding_start + rounding_step * static_cast<double>(rounding_knots - 1);
    const leo_orbit_snapshot rounding{
        1,
        0,
        rounding_start,
        rounding_step,
        1,
        rounding_knots,
        &rounding_id,
        &rounding_state,
    };
    assert(leo::location::internal::build_interpolation_stencil(
               &rounding, rounding_end, &ignored_stencil) ==
           leo_orbit_interpolate(&rounding, 0, rounding_end, &ignored_state));
    assert(leo::location::internal::build_interpolation_stencil(
               &rounding, rounding_end, &ignored_stencil) == LEO_LOCATION_INVALID);

    leo::location::internal::InterpolationStencil stencil{};
    assert(leo::location::internal::build_interpolation_stencil(
               &snapshot, 0.25, &stencil) == LEO_LOCATION_OK);
    states[stencil.knot_index].velocity_km_s[1] =
        std::numeric_limits<double>::quiet_NaN();
    leo_orbit_state generic{};
    leo_orbit_state planned{};
    assert(leo_orbit_interpolate(&snapshot, 0, 0.25, &generic) ==
           LEO_LOCATION_ORBIT_ERROR);
    assert(leo::location::internal::interpolate_with_stencil(
               &snapshot, 0, &stencil, &planned) == LEO_LOCATION_ORBIT_ERROR);
}

void test_reusable_context_and_allocation_fallback() {
    const int32_t ids[2] = {101, 202};
    leo_orbit_state states[8]{};
    const leo_orbit_snapshot snapshot = make_snapshot(states, ids);
    const double times[7] = {-1.25, 0.0, 0.75, 1.5, 2.0, 3.125, 4.75};
    const double measured[7] = {-15.5, -12.25, -10.0, -7.75, -4.5, -2.0, 1.25};
    const uint8_t training[7] = {1, 0, 1, 0, 1, 0, 1};
    const leo_location_track track{77, 7, 7, times, measured, training};
    const leo_location_site site{{6378.0, 0.0, 0.0}, {1.0, 0.0, 0.0}};
    leo_score_config config = leo_score_default_config();
    config.tau_first_s = -1;
    config.tau_last_s = 1;

    leo_score_context *planned_context = leo_score_context_create(7, 3);
    leo_score_context *fallback_context = leo_score_context_create(7, 3);
    assert(planned_context != nullptr && fallback_context != nullptr);
    leo::location::internal::force_stencil_allocation_failure_for_test(
        fallback_context, true);
    assert(leo::location::internal::stencil_capacity_for_test(planned_context) == 0);
    assert(leo::location::internal::stencil_capacity_for_test(fallback_context) == 0);

    leo_track_score planned[1];
    leo_track_score fallback[1];
    leo_track_scores_clear(planned, 1);
    leo_track_scores_clear(fallback, 1);
    leo_score_stats planned_stats{};
    leo_score_stats fallback_stats{};
    assert(leo_score_partition(
               planned_context,
               &snapshot,
               &track,
               1,
               &site,
               &config,
               0,
               2,
               planned,
               &planned_stats) == LEO_LOCATION_OK);
    const size_t first_capacity =
        leo::location::internal::stencil_capacity_for_test(planned_context);
    assert(first_capacity >= 21 && first_capacity <=
        leo::location::internal::kMaximumInterpolationStencils);
    assert(leo_score_partition(
               fallback_context,
               &snapshot,
               &track,
               1,
               &site,
               &config,
               0,
               2,
               fallback,
               &fallback_stats) == LEO_LOCATION_OK);
    assert(leo::location::internal::stencil_capacity_for_test(fallback_context) == 0);
    assert_score_exact(planned[0], fallback[0]);
    assert(planned_stats.rejected_satellite_tracks == fallback_stats.rejected_satellite_tracks);
    assert(planned_stats.evaluated_satellite_tracks ==
           fallback_stats.evaluated_satellite_tracks);

    leo_track_scores_clear(planned, 1);
    assert(leo_score_partition(
               planned_context,
               &snapshot,
               &track,
               1,
               &site,
               &config,
               0,
               2,
               planned,
               nullptr) == LEO_LOCATION_OK);
    assert(leo::location::internal::stencil_capacity_for_test(planned_context) ==
           first_capacity);
    leo_score_context_destroy(planned_context);
    leo_score_context_destroy(fallback_context);
}

void test_unused_interpolation_does_not_allocate() {
    const int32_t ids[2] = {101, 202};
    leo_orbit_state states[8]{};
    leo_orbit_snapshot snapshot = make_snapshot(states, ids);
    for (leo_orbit_state &state : states) {
        state.position_km[0] = -7000.0;
        state.velocity_km_s[0] = std::numeric_limits<double>::quiet_NaN();
    }
    const double times[6] = {0, 1, 2, 3, 4, 5};
    const double measured[6] = {0, 1, 2, 3, 4, 5};
    const uint8_t training[6] = {1, 0, 1, 0, 1, 0};
    const leo_location_track track{88, 6, 6, times, measured, training};
    const leo_location_site site{{6378.0, 0.0, 0.0}, {1.0, 0.0, 0.0}};
    const leo_score_config config = leo_score_default_config();
    leo_score_context *context = leo_score_context_create(6, 11);
    assert(context != nullptr);
    for (const auto range : {std::pair<uint32_t, uint32_t>{0, 0}, {0, 2}}) {
        leo_track_score score[1];
        leo_track_scores_clear(score, 1);
        leo_score_stats stats{};
        assert(leo_score_partition(
                   context,
                   &snapshot,
                   &track,
                   1,
                   &site,
                   &config,
                   range.first,
                   range.second,
                   score,
                   &stats) == LEO_LOCATION_OK);
        assert(!score[0].matched);
        assert(stats.evaluated_satellite_tracks == 0);
        assert(stats.rejected_satellite_tracks == range.second - range.first);
        assert(leo::location::internal::stencil_capacity_for_test(context) == 0);
    }
    leo_score_context_destroy(context);
}

void test_scratch_bound_falls_back_to_generic() {
    constexpr uint32_t kObservations = 17000;
    const int32_t id = 303;
    leo_orbit_state states[2]{};
    states[0].position_km[0] = 7000.0;
    states[1].position_km[0] = 7000.0;
    const leo_orbit_snapshot snapshot{21, 0, 0.0, 20000.0, 1, 2, &id, states};
    std::vector<double> times(kObservations);
    std::vector<double> measured(kObservations);
    std::vector<uint8_t> training(kObservations);
    for (uint32_t index = 0; index < kObservations; ++index) {
        times[index] = index;
        measured[index] = static_cast<double>(index % 31);
        training[index] = static_cast<uint8_t>(index % 2);
    }
    const leo_location_site site{{6378.0, 0.0, 0.0}, {1.0, 0.0, 0.0}};
    leo_score_config config = leo_score_default_config();
    config.tau_first_s = 0;
    config.tau_last_s = 0;
    leo_score_context *context = leo_score_context_create(kObservations, 1);
    assert(context != nullptr);
    const auto run = [&](uint32_t count) {
        const leo_location_track track{
            99,
            count,
            1,
            times.data(),
            measured.data(),
            training.data(),
        };
        leo_track_score score[1];
        leo_track_scores_clear(score, 1);
        assert(leo_score_partition(
                   context,
                   &snapshot,
                   &track,
                   1,
                   &site,
                   &config,
                   0,
                   1,
                   score,
                   nullptr) == LEO_LOCATION_OK);
        assert(score[0].matched && score[0].candidate_id == id);
    };
    run(9000);
    assert(leo::location::internal::stencil_capacity_for_test(context) == 9000);
    run(16000);
    assert(leo::location::internal::stencil_capacity_for_test(context) == 16000);
    run(kObservations);
    assert(leo::location::internal::stencil_capacity_for_test(context) == 16000);
    leo_score_context_destroy(context);
}
}  // namespace

int main() {
    test_interpolation_matches_generic_oracle();
    test_interpolation_boundaries_and_errors();
    test_reusable_context_and_allocation_fallback();
    test_unused_interpolation_does_not_allocate();
    test_scratch_bound_falls_back_to_generic();
    std::cout << "native score interpolation stencil tests passed\n";
    return 0;
}
