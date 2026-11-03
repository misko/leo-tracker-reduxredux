#pragma once

#include "location.h"
#include "pipeline.hpp"

#include <cstddef>
#include <cstdint>
#include <vector>

namespace leo::adaptive::location::research {

/* Research-only authority for reusing a complete per-track score. Publication
 * generation is deliberately absent: an identical track may survive a newer
 * publication. Stream or orbit replacement, an exact site change, or any
 * score-policy change establishes a different scope. */
struct ExactScoreScope {
    std::uint64_t stream_generation{};
    std::uint64_t orbit_generation{};
    leo_location_site site{};
    leo_score_config config{};
};

class ExactTrackScoreCache {
public:
    void begin(const ExactScoreScope& scope);
    bool lookup(
        const pipeline::OwnedLocationTrack& owned,
        const leo_location_track& record,
        leo_track_score* score,
        leo_score_stats* stats) const;
    void store(
        const pipeline::OwnedLocationTrack& owned,
        const leo_location_track& record,
        const leo_track_score& score,
        const leo_score_stats& stats);

    std::size_t entries() const noexcept;
    std::size_t logical_bytes() const noexcept;

private:
    struct Entry {
        pipeline::OwnedLocationTrack owned;
        std::uint64_t track_key{};
        std::uint32_t weight_s{};
        leo_track_score score{};
        leo_score_stats stats{};
    };

    bool has_scope_{};
    ExactScoreScope scope_{};
    std::vector<Entry> entries_;
};

bool exact_scope_equal(const ExactScoreScope& left, const ExactScoreScope& right);
bool exact_track_equal(
    const pipeline::OwnedLocationTrack& left_owned,
    const leo_location_track& left_record,
    const pipeline::OwnedLocationTrack& right_owned,
    const leo_location_track& right_record);

}  // namespace leo::adaptive::location::research
