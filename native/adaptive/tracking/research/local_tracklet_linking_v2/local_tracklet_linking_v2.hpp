#pragma once

#include "../../tracking.hpp"
#include <cstddef>
#include <vector>

namespace leo::adaptive::tracking::research::local_tracklet_linking_v2 {

struct Config {
    double canonical_rf_hz{11'200'000'000.0};
    double alias_spacing_hz{1.0/4.4e-6};
    double window_s{8.0};
    double window_step_s{4.0};
    double residual_gate_hz{2'500.0};
    double link_frequency_gate_hz{5'000.0};
    double link_rate_gate_hz_per_s{3'000.0};
    double maximum_gap_s{4.0};
    double minimum_rate_hz_per_s{-15'000.0};
    double maximum_rate_hz_per_s{15'000.0};
    double minimum_span_s{4.0};
    std::size_t minimum_support{8};
    std::size_t maximum_candidates_per_group{16};
    std::size_t maximum_local_seeds_per_window{128};
    std::size_t maximum_fragments_per_window{16};
    std::size_t maximum_tracks_per_lane{16};
    std::size_t maximum_input_points{40'000};
};

struct Stats { std::size_t lanes{},windows{},local_seeds{},fragments{},link_tests{}; };
struct Result { std::vector<tracking::Track> tracks; std::size_t input_candidate_count{},used_candidate_count{}; Stats stats; };
Result reconstruct(const std::vector<tracking::Candidate>&,const Config& = Config{});

} // namespace leo::adaptive::tracking::research::local_tracklet_linking_v2
