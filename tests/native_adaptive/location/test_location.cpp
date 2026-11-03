#include "location.h"

#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <thread>
#include <tuple>
#include <vector>

namespace {
void copy_line(char destination[70], const char *source) {
    assert(std::strlen(source) == 69);
    std::memcpy(destination, source, 69);
    destination[69] = '\0';
}

void test_orbit_context() {
    leo_tle_record tle{};
    tle.satellite_id = 44714;
    copy_line(tle.line1, "1 44714U 19074B   26270.09087237  .00034246  00000-0  33881-3 0  9999");
    copy_line(tle.line2, "2 44714  53.1459 294.7156 0002678  78.6558 281.4759 15.65554847380103");
    leo_orbit_context *context = leo_orbit_context_create(1, 4);
    assert(context != nullptr);
    leo_orbit_snapshot first{};
    assert(leo_orbit_build_tle(
               context, 41, 1790557997299661326LL, -10.0, 10.0, 4, &tle, 1, &first) ==
           LEO_LOCATION_OK);
    assert(first.generation == 41 && first.satellite_ids[0] == 44714);
    leo_orbit_state interpolated{};
    assert(leo_orbit_interpolate(&first, 0, 5.0, &interpolated) == LEO_LOCATION_OK);
    for (unsigned component = 0; component < 3; ++component) {
        assert(std::isfinite(interpolated.position_km[component]));
        assert(std::isfinite(interpolated.velocity_km_s[component]));
    }
    const leo_orbit_state saved = first.states[0];
    leo_tle_record invalid = tle;
    invalid.line1[0] = 'x';
    leo_orbit_snapshot rejected{};
    assert(leo_orbit_build_tle(
               context, 42, first.start_utc_ns, -10.0, 10.0, 4, &invalid, 1, &rejected) ==
           LEO_LOCATION_INVALID);
    assert(first.states[0].position_km[0] == saved.position_km[0]);
    leo_orbit_snapshot second{};
    assert(leo_orbit_build_tle(
               context, 43, first.start_utc_ns, -10.0, 10.0, 4, &tle, 1, &second) ==
           LEO_LOCATION_OK);
    assert(second.generation == 43 && second.states != first.states);
    leo_orbit_context_destroy(context);
}

void test_score_partition_and_penalty() {
    const int32_t ids[2] = {20, 10};
    leo_orbit_state states[8]{};
    for (unsigned satellite = 0; satellite < 2; ++satellite) {
        for (unsigned knot = 0; knot < 4; ++knot) {
            states[satellite * 4 + knot].position_km[0] = 7000.0;
        }
    }
    const leo_orbit_snapshot snapshot{1, 0, -10.0, 10.0, 2, 4, ids, states};
    const double times[6] = {0, 1, 2, 3, 4, 5};
    const double measured[6] = {0, 1, 2, 3, 4, 5};
    const uint8_t training[6] = {1, 0, 1, 0, 1, 0};
    const leo_location_track track{9, 6, 6, times, measured, training};
    const leo_location_site site{{6378.0, 0.0, 0.0}, {1.0, 0.0, 0.0}};
    leo_score_config config = leo_score_default_config();
    leo_score_context *left_context = leo_score_context_create(6, 11);
    leo_score_context *right_context = leo_score_context_create(6, 11);
    assert(left_context != nullptr && right_context != nullptr);
    leo_track_score left[1];
    leo_track_score right[1];
    leo_track_scores_clear(left, 1);
    leo_track_scores_clear(right, 1);
    leo_location_status left_status = LEO_LOCATION_STATE;
    leo_location_status right_status = LEO_LOCATION_STATE;
    std::thread left_worker([&] {
        left_status = leo_score_partition(
            left_context, &snapshot, &track, 1, &site, &config, 0, 1, left, nullptr);
    });
    std::thread right_worker([&] {
        right_status = leo_score_partition(
            right_context, &snapshot, &track, 1, &site, &config, 1, 2, right, nullptr);
    });
    left_worker.join();
    right_worker.join();
    assert(left_status == LEO_LOCATION_OK && right_status == LEO_LOCATION_OK);
    assert(left[0].candidate_id == 20 && right[0].candidate_id == 10);
    assert(leo_track_scores_reduce(left, right, 1) == LEO_LOCATION_OK);
    assert(left[0].matched && left[0].candidate_id == 10 && left[0].tau_s == -5);
    assert(std::abs(left[0].training_rms_hz - std::sqrt(8.0 / 3.0)) < 1e-12);
    assert(std::abs(left[0].heldout_rms_hz - std::sqrt(11.0 / 3.0)) < 1e-12);
    leo_point_score point{};
    assert(leo_point_score_finish(&track, 1, left, &config, &point) == LEO_LOCATION_OK);
    assert(std::abs(point.residual_rmse_hz - left[0].heldout_rms_hz) < 1e-12);

    for (leo_orbit_state &state : states) {
        state.position_km[0] = -7000.0;
    }
    leo_track_scores_clear(left, 1);
    leo_score_stats stats{};
    assert(leo_score_partition(
               left_context, &snapshot, &track, 1, &site, &config, 0, 2, left, &stats) ==
           LEO_LOCATION_OK);
    assert(!left[0].matched && stats.rejected_satellite_tracks == 2);
    assert(leo_point_score_finish(&track, 1, left, &config, &point) == LEO_LOCATION_OK);
    assert(point.residual_rmse_hz == 800.0 && point.unmatched_track_count == 1);
    leo_score_context_destroy(left_context);
    leo_score_context_destroy(right_context);
}

std::vector<std::tuple<double, double, unsigned>> run_search(uint64_t generation) {
    leo_search_context *context = leo_search_context_create(12);
    assert(context != nullptr);
    leo_search_policy policy{};
    policy.radius_km = 100.0;
    policy.region_size_km = 200.0;
    policy.level_count = 2;
    policy.levels_km[0] = 100.0;
    policy.levels_km[1] = 50.0;
    policy.budget_points = 12;
    assert(leo_search_begin(context, generation, &policy) == LEO_LOCATION_OK);
    leo_search_result initial{};
    assert(leo_search_get_result(context, generation + 1, &initial) == LEO_LOCATION_STALE);
    std::vector<std::tuple<double, double, unsigned>> trace;
    for (;;) {
        leo_search_point points[16];
        uint32_t count = 0;
        const leo_location_status status =
            leo_search_next(context, generation, points, 16, &count);
        if (status == LEO_LOCATION_DONE) {
            break;
        }
        assert(status == LEO_LOCATION_OK && count != 0);
        leo_search_result paused{};
        assert(leo_search_get_result(context, generation, &paused) == LEO_LOCATION_OK);
        std::vector<leo_search_evaluation> values(count);
        for (uint32_t index = 0; index < count; ++index) {
            trace.emplace_back(points[index].east_km, points[index].north_km, points[index].depth);
            const double de = points[index].east_km - 37.0;
            const double dn = points[index].north_km + 23.0;
            values[index] = {points[index].east_km, points[index].north_km, de * de + dn * dn};
        }
        assert(leo_search_submit(context, generation, values.data(), count) == LEO_LOCATION_OK);
    }
    leo_search_result result{};
    assert(leo_search_get_result(context, generation, &result) == LEO_LOCATION_OK);
    assert(result.evaluated_points == 12 && !result.complete && result.has_incumbent);
    leo_search_context_destroy(context);
    return trace;
}

void test_search_resume_ties_and_cancel() {
    const auto first = run_search(100);
    const auto second = run_search(200);
    assert(first == second);
    assert(first.size() == 12);
    assert(std::get<0>(first[0]) == -50.0 && std::get<1>(first[0]) == -50.0);

    leo_search_context *context = leo_search_context_create(400);
    leo_search_policy policy = leo_search_default_policy(250.0);
    assert(leo_search_begin(context, 300, &policy) == LEO_LOCATION_OK);
    assert(leo_search_cancel(context, 301) == LEO_LOCATION_STALE);
    assert(leo_search_cancel(context, 300) == LEO_LOCATION_OK);
    leo_search_point point{};
    uint32_t count = 0;
    assert(leo_search_next(context, 300, &point, 1, &count) == LEO_LOCATION_CANCELLED);
    leo_search_context_destroy(context);
}
}  // namespace

int main() {
    test_orbit_context();
    test_score_partition_and_penalty();
    test_search_resume_ties_and_cancel();
    std::cout << "native location unit tests passed\n";
    return 0;
}
