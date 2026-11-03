#pragma once

#include "../../tracking.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace leo::adaptive::tracking::research::fast_tracks {

struct Config {
    double canonical_rf_hz{11'200'000'000.0};
    double alias_spacing_hz{1.0 / 4.4e-6};
    double minimum_slope_hz_per_s{-15'000.0};
    double maximum_slope_hz_per_s{15'000.0};
    double residual_gate_hz{2'500.0};
    double maximum_gap_s{4.0};
    double minimum_span_s{4.0};
    std::size_t minimum_support{8};
    double minimum_point_weight{0.1};
    std::size_t slope_seed_count{121};
    std::size_t beam_width{256};
    std::size_t branches_per_state{2};
    std::size_t maximum_tracks_per_lane{8};
    std::size_t maximum_input_points{40'000};
    std::size_t maximum_candidates_per_source_group{16};
    std::size_t maximum_nodes_per_peel{2'000'000};
};

struct Point {
    std::string candidate_id;
    std::string source_group_id;
    int relative_alias_index{};
    double normalized_raw_cfo_hz{};
    double normalized_dealiased_cfo_hz{};
};

struct Track {
    Lane lane;
    std::int64_t start_utc_ns{};
    std::int64_t end_utc_ns{};
    std::int64_t reference_utc_ns{};
    double normalized_rate_hz_per_s{};
    double normalized_intercept_hz{};
    double residual_rms_hz{};
    double residual_max_hz{};
    double weighted_support{};
    std::vector<Point> points;
};

struct Stats {
    std::size_t lanes{};
    std::size_t source_groups{};
    std::size_t peel_passes{};
    std::size_t nodes_created{};
    std::size_t maximum_live_beam{};
    std::size_t exact_duplicates_consolidated{};
};

struct Result {
    std::vector<Track> tracks;
    std::size_t input_candidate_count{};
    std::size_t used_candidate_count{};
    Stats stats;
};

// Research-only bounded continuity beam. It consumes public Candidate fields
// and has no satellite, TLE, location, or oracle-label input.
Result reconstruct(const std::vector<Candidate>&, const Config& = Config{});

}  // namespace leo::adaptive::tracking::research::fast_tracks
