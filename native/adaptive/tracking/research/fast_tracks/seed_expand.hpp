#pragma once

#include "../../tracking.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace leo::adaptive::tracking::research::seed_expand {

struct Seed {
    Lane lane;
    std::int64_t start_utc_ns{};
    std::int64_t end_utc_ns{};
    std::int64_t reference_utc_ns{};
    double normalized_rate_hz_per_s{};
    double normalized_intercept_hz{};
};

struct Config {
    ::leo::adaptive::tracking::Config tracking;
    std::size_t maximum_seeds{256};
    std::size_t maximum_hypotheses_per_lane{16};
};

struct Result {
    std::vector<Track> tracks;
    std::size_t input_candidate_count{};
    std::size_t used_candidate_count{};
    std::size_t seed_count{};
    std::size_t expanded_segment_count{};
    std::size_t exact_segments_consolidated{};
    std::size_t near_geometry_consolidated{};
    std::size_t shared_candidate_overlaps{};
};

// Research-only source-driven expansion. Seeds come from another native coarse
// tracker result; candidates are always rescored from the complete input lane.
Result expand(const std::vector<Candidate>&,const std::vector<Seed>&,
              const Config& = Config{});

}  // namespace leo::adaptive::tracking::research::seed_expand
