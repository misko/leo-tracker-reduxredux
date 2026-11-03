#include "location.h"
#include "score_interpolation_stencil.hpp"

#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>

namespace {
static_assert(sizeof(leo::location::research::InterpolationStencil) == 72);

uint64_t bits(double value) {
    uint64_t result = 0;
    static_assert(sizeof(result) == sizeof(value));
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

void assert_state_exact(const leo_orbit_state &left, const leo_orbit_state &right) {
    for (unsigned component = 0; component < 3; ++component) {
        assert(bits(left.position_km[component]) == bits(right.position_km[component]));
        assert(bits(left.velocity_km_s[component]) == bits(right.velocity_km_s[component]));
    }
}

void assert_track_score_exact(const leo_track_score &left, const leo_track_score &right) {
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

void test_stencil_matches_generic_interpolator() {
    const int32_t ids[2] = {101, 202};
    leo_orbit_state states[8]{};
    leo_orbit_snapshot snapshot = make_snapshot(states, ids);
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
        leo::location::research::InterpolationStencil stencil{};
        assert(leo::location::research::build_interpolation_stencil(
                   &snapshot, time, &stencil) == LEO_LOCATION_OK);
        for (uint32_t satellite = 0; satellite < 2; ++satellite) {
            leo_orbit_state expected{};
            leo_orbit_state actual{};
            assert(leo_orbit_interpolate(&snapshot, satellite, time, &expected) ==
                   LEO_LOCATION_OK);
            assert(leo::location::research::interpolate_with_stencil(
                       &snapshot, satellite, &stencil, &actual) == LEO_LOCATION_OK);
            assert_state_exact(actual, expected);
        }
    }
}

void test_stencil_boundaries_and_errors() {
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
        leo::location::research::InterpolationStencil stencil{};
        leo_orbit_state ignored{};
        assert(leo::location::research::build_interpolation_stencil(
                   &snapshot, time, &stencil) ==
               leo_orbit_interpolate(&snapshot, 0, time, &ignored));
    }

    leo_orbit_snapshot overflow = snapshot;
    overflow.knot_start_s = std::numeric_limits<double>::max();
    overflow.knot_step_s = std::numeric_limits<double>::max();
    leo::location::research::InterpolationStencil ignored_stencil{};
    leo_orbit_state ignored_state{};
    assert(leo::location::research::build_interpolation_stencil(
               &overflow, overflow.knot_start_s, &ignored_stencil) ==
           leo_orbit_interpolate(&overflow, 0, overflow.knot_start_s, &ignored_state));

    /* This exact final time passes an end-time comparison made from the same
     * expression, but cancellation makes its normalized coordinate exceed the
     * last knot by about 2e-13. Preserve the generic interpolator's rejection. */
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
    assert(leo::location::research::build_interpolation_stencil(
               &rounding, rounding_end, &ignored_stencil) ==
           leo_orbit_interpolate(&rounding, 0, rounding_end, &ignored_state));
    assert(leo::location::research::build_interpolation_stencil(
               &rounding, rounding_end, &ignored_stencil) == LEO_LOCATION_INVALID);

    leo::location::research::InterpolationStencil stencil{};
    assert(leo::location::research::build_interpolation_stencil(
               &snapshot, 0.25, &stencil) == LEO_LOCATION_OK);
    states[stencil.knot_index].velocity_km_s[1] =
        std::numeric_limits<double>::quiet_NaN();
    leo_orbit_state expected{};
    leo_orbit_state actual{};
    assert(leo_orbit_interpolate(&snapshot, 0, 0.25, &expected) ==
           LEO_LOCATION_ORBIT_ERROR);
    assert(leo::location::research::interpolate_with_stencil(
               &snapshot, 0, &stencil, &actual) == LEO_LOCATION_ORBIT_ERROR);
}

void test_partition_matches_reference() {
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

    leo_score_context *candidate_context = leo_score_context_create(7, 3);
    leo_score_context *reference_context = leo_score_context_create(7, 3);
    assert(candidate_context != nullptr && reference_context != nullptr);
    leo_track_score candidate[1];
    leo_track_score reference[1];
    leo_track_scores_clear(candidate, 1);
    leo_track_scores_clear(reference, 1);
    leo_score_stats candidate_stats{};
    leo_score_stats reference_stats{};
    assert(leo_score_partition(
               candidate_context,
               &snapshot,
               &track,
               1,
               &site,
               &config,
               0,
               2,
               candidate,
               &candidate_stats) == LEO_LOCATION_OK);
    assert(leo_score_partition_reference_research(
               reference_context,
               &snapshot,
               &track,
               1,
               &site,
               &config,
               0,
               2,
               reference,
               &reference_stats) == LEO_LOCATION_OK);
    assert_track_score_exact(candidate[0], reference[0]);
    assert(candidate_stats.rejected_satellite_tracks ==
           reference_stats.rejected_satellite_tracks);
    assert(candidate_stats.evaluated_satellite_tracks ==
           reference_stats.evaluated_satellite_tracks);
    leo_score_context_destroy(candidate_context);
    leo_score_context_destroy(reference_context);
}

void test_unused_interpolation_preserves_reference_behavior() {
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
    leo_score_context *candidate_context = leo_score_context_create(6, 11);
    leo_score_context *reference_context = leo_score_context_create(6, 11);
    assert(candidate_context != nullptr && reference_context != nullptr);

    for (const auto range : {std::pair<uint32_t, uint32_t>{0, 0}, {0, 2}}) {
        leo_track_score candidate[1];
        leo_track_score reference[1];
        leo_track_scores_clear(candidate, 1);
        leo_track_scores_clear(reference, 1);
        leo_score_stats candidate_stats{};
        leo_score_stats reference_stats{};
        assert(leo_score_partition(
                   candidate_context,
                   &snapshot,
                   &track,
                   1,
                   &site,
                   &config,
                   range.first,
                   range.second,
                   candidate,
                   &candidate_stats) == LEO_LOCATION_OK);
        assert(leo_score_partition_reference_research(
                   reference_context,
                   &snapshot,
                   &track,
                   1,
                   &site,
                   &config,
                   range.first,
                   range.second,
                   reference,
                   &reference_stats) == LEO_LOCATION_OK);
        assert_track_score_exact(candidate[0], reference[0]);
        assert(candidate_stats.rejected_satellite_tracks ==
               reference_stats.rejected_satellite_tracks);
        assert(candidate_stats.evaluated_satellite_tracks ==
               reference_stats.evaluated_satellite_tracks);
    }
    leo_score_context_destroy(candidate_context);
    leo_score_context_destroy(reference_context);
}
}  // namespace

int main() {
    test_stencil_matches_generic_interpolator();
    test_stencil_boundaries_and_errors();
    test_partition_matches_reference();
    test_unused_interpolation_preserves_reference_behavior();
    std::cout << "research interpolation stencil tests passed\n";
    return 0;
}
