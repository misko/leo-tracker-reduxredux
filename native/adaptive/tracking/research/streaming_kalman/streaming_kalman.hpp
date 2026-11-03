#pragma once

#include "../../tracking.hpp"

#include <cstddef>
#include <vector>

namespace leo::adaptive::tracking::research::streaming_kalman {

struct Config {
    double canonical_rf_hz{11'200'000'000.0};
    double alias_spacing_hz{1.0 / 4.4e-6};
    double measurement_sigma_hz{400.0};
    double acceleration_sigma_hz_per_s2{60.0};
    double innovation_gate_hz{5'000.0};
    double minimum_rate_hz_per_s{-15'000.0};
    double maximum_rate_hz_per_s{15'000.0};
    double maximum_gap_s{4.0};
    double minimum_span_s{4.0};
    std::size_t minimum_support{8};
    double minimum_point_weight{0.1};
    std::size_t association_branches{2};
    std::size_t maximum_hypotheses_per_lane{96};
    std::size_t maximum_output_tracks_per_lane{16};
    std::size_t maximum_input_points{40'000};
    std::size_t maximum_candidates_per_source_group{16};
};

struct Stats {
    std::size_t lanes{};
    std::size_t source_groups{};
    std::size_t rolling_births{};
    std::size_t predictions{};
    std::size_t accepted_updates{};
    std::size_t missed_detection_branches{};
    std::size_t peak_hypotheses{};
};

struct Result {
    std::vector<tracking::Track> tracks;
    std::size_t input_candidate_count{};
    std::size_t used_candidate_count{};
    Stats stats;
};

// Research-only chronological 2-state frequency/rate Kalman hypothesis bank.
// Output tracks are overlapping hypotheses, not an exclusive assignment.
Result reconstruct(const std::vector<tracking::Candidate>&,
                   const Config& = Config{});

}  // namespace leo::adaptive::tracking::research::streaming_kalman
