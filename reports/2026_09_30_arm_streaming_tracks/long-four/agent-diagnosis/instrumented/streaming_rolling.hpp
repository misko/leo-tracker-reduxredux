#pragma once

#include "../../tracking.hpp"

#include <cstddef>
#include <vector>

namespace leo::adaptive::tracking::research::streaming_rolling {

struct Config {
    double canonical_rf_hz{11'200'000'000.0};
    double alias_spacing_hz{1.0/4.4e-6};
    double window_s{8.0};
    std::size_t maximum_fit_points{32};
    double residual_gate_hz{2'500.0};
    double maximum_uncertainty_hz{2'500.0};
    double minimum_rate_hz_per_s{-15'000.0};
    double maximum_rate_hz_per_s{15'000.0};
    double maximum_gap_s{4.0};
    double minimum_span_s{4.0};
    std::size_t minimum_support{8};
    std::size_t maximum_active_per_lane{24};
    std::size_t alternatives_per_hypothesis{2};
    std::size_t maximum_candidates_per_group{16};
    std::size_t maximum_input_points{40'000};
};

struct Stats {
    std::size_t lanes{};
    std::size_t source_groups{};
    std::size_t groups_processed{};
    std::size_t fits{};
    std::size_t associations_tested{};
    std::size_t births{};
    std::size_t peak_active{};
};

struct Result {
    std::vector<tracking::Track> tracks;
    std::size_t input_candidate_count{};
    std::size_t used_candidate_count{};
    Stats stats;
};

Result reconstruct(const std::vector<tracking::Candidate>&, const Config& = Config{});

} // namespace leo::adaptive::tracking::research::streaming_rolling
