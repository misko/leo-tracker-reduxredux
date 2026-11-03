#pragma once

#include "../../tracking.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace leo::adaptive::tracking::research::curvature_tracks {

struct Config {
    double canonical_rf_hz{11'200'000'000.0};
    double alias_spacing_hz{1.0 / 4.4e-6};
    double minimum_rate_hz_per_s{-15'000.0};
    double maximum_rate_hz_per_s{15'000.0};
    double maximum_acceleration_hz_per_s2{250.0};
    double residual_gate_hz{2'500.0};
    double measurement_uncertainty_hz{400.0};
    double maximum_gap_s{4.0};
    double maximum_source_group_span_s{0.020};
    double minimum_span_s{4.0};
    std::size_t minimum_support{8};
    double minimum_point_weight{0.1};
    double state_window_s{12.0};
    std::size_t state_window{32};
    std::size_t maximum_seeds_per_lane{512};
    std::size_t ambiguity_branches{2};
    std::size_t ambiguity_beam{4};
    std::size_t maximum_hypotheses_per_lane{16};
    std::size_t maximum_input_points{40'000};
    std::size_t maximum_candidates_per_source_group{16};
};

struct Track {
    // This linear fit exists only so existing TRACK readers can inspect the
    // result. Association uses the local frequency/rate/acceleration states.
    tracking::Track compatibility_linear_summary;
    double maximum_abs_local_acceleration_hz_per_s2{};
    double trajectory_score{};
};

struct Stats {
    std::size_t lanes{};
    std::size_t source_groups{};
    std::size_t seeds_considered{};
    std::size_t seeds_retained{};
    std::size_t states_evaluated{};
    std::size_t exact_hypotheses_consolidated{};
    std::size_t near_hypotheses_consolidated{};
    std::size_t external_seed_tracks{};
    std::size_t retained_original_alternatives{};
};

struct Result {
    std::vector<Track> tracks;
    std::size_t input_candidate_count{};
    std::size_t used_candidate_count{};
    Stats stats;
};

struct SeedPoint {
    std::string candidate_id;
    double normalized_dealiased_cfo_hz{};
};

struct SeedTrack {
    tracking::Lane lane;
    std::vector<SeedPoint> points;
};

Result reconstruct(const std::vector<tracking::Candidate>&,
                   const Config& = Config{});

// Research-only hybrid entry point. Seed membership must refer to candidates
// in the input and is used only to initialize local state. Association is
// rerun against every original source group. Optional retained originals make
// the output an explicit hypothesis bank, not an exclusive assignment.
Result reconstruct_seeded(const std::vector<tracking::Candidate>&,
                          const std::vector<SeedTrack>&,
                          bool retain_original_alternatives,
                          const Config& = Config{});

}  // namespace leo::adaptive::tracking::research::curvature_tracks
