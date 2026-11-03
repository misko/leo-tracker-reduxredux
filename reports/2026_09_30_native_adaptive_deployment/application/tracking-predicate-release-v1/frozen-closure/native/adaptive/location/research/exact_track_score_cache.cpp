#include "exact_track_score_cache.hpp"

#include <algorithm>
#include <cstring>

namespace leo::adaptive::location::research {
namespace {

bool exact_double(double left, double right) {
    return std::memcmp(&left, &right, sizeof(left)) == 0;
}

bool exact_doubles(const std::vector<double>& left, const std::vector<double>& right) {
    return left.size() == right.size() &&
        (left.empty() || std::memcmp(left.data(), right.data(), left.size() * sizeof(double)) == 0);
}

std::size_t string_bytes(const std::string& value) {
    return value.size();
}

std::size_t track_bytes(const pipeline::OwnedLocationTrack& track) {
    std::size_t total = string_bytes(track.tracklet_id) + string_bytes(track.support_digest) +
        string_bytes(track.partition_seed) + track.times_s.size() * sizeof(double) +
        track.measured_hz.size() * sizeof(double) +
        track.training_mask.size() * sizeof(std::uint8_t);
    for (const auto& identity : track.observation_ids) total += string_bytes(identity);
    return total;
}

}  // namespace

bool exact_scope_equal(const ExactScoreScope& left, const ExactScoreScope& right) {
    if (left.stream_generation != right.stream_generation ||
        left.orbit_generation != right.orbit_generation ||
        left.config.tau_first_s != right.config.tau_first_s ||
        left.config.tau_last_s != right.config.tau_last_s ||
        left.config.tau_step_s != right.config.tau_step_s ||
        !exact_double(left.config.carrier_hz, right.config.carrier_hz) ||
        !exact_double(left.config.speed_of_light_km_s, right.config.speed_of_light_km_s) ||
        !exact_double(left.config.unmatched_penalty_hz, right.config.unmatched_penalty_hz)) {
        return false;
    }
    for (unsigned component = 0; component < 3; ++component) {
        if (!exact_double(left.site.ecef_km[component], right.site.ecef_km[component]) ||
            !exact_double(left.site.up[component], right.site.up[component])) return false;
    }
    return true;
}

bool exact_track_equal(
    const pipeline::OwnedLocationTrack& left_owned,
    const leo_location_track& left_record,
    const pipeline::OwnedLocationTrack& right_owned,
    const leo_location_track& right_record) {
    return left_record.track_key == right_record.track_key &&
        left_record.observation_count == right_record.observation_count &&
        left_record.weight_s == right_record.weight_s &&
        left_owned.tracklet_id == right_owned.tracklet_id &&
        left_owned.support_digest == right_owned.support_digest &&
        left_owned.partition_seed == right_owned.partition_seed &&
        left_owned.observation_ids == right_owned.observation_ids &&
        exact_doubles(left_owned.times_s, right_owned.times_s) &&
        exact_doubles(left_owned.measured_hz, right_owned.measured_hz) &&
        left_owned.training_mask == right_owned.training_mask;
}

void ExactTrackScoreCache::begin(const ExactScoreScope& scope) {
    if (!has_scope_ || !exact_scope_equal(scope_, scope)) {
        entries_.clear();
        scope_ = scope;
        has_scope_ = true;
    }
}

bool ExactTrackScoreCache::lookup(
    const pipeline::OwnedLocationTrack& owned,
    const leo_location_track& record,
    leo_track_score* score,
    leo_score_stats* stats) const {
    if (!has_scope_ || score == nullptr || stats == nullptr) return false;
    const auto found = std::find_if(entries_.begin(), entries_.end(), [&](const Entry& entry) {
        return entry.owned.tracklet_id == owned.tracklet_id &&
            exact_track_equal(entry.owned, leo_location_track{
                entry.track_key,
                static_cast<std::uint32_t>(entry.owned.times_s.size()),
                entry.weight_s,
                entry.owned.times_s.data(),
                entry.owned.measured_hz.data(),
                entry.owned.training_mask.data()}, owned, record);
    });
    if (found == entries_.end()) return false;
    *score = found->score;
    *stats = found->stats;
    return true;
}

void ExactTrackScoreCache::store(
    const pipeline::OwnedLocationTrack& owned,
    const leo_location_track& record,
    const leo_track_score& score,
    const leo_score_stats& stats) {
    if (!has_scope_) return;
    auto found = std::find_if(entries_.begin(), entries_.end(), [&](const Entry& entry) {
        return entry.owned.tracklet_id == owned.tracklet_id;
    });
    Entry value{owned, record.track_key, record.weight_s, score, stats};
    if (found == entries_.end()) entries_.push_back(std::move(value));
    else *found = std::move(value);
}

std::size_t ExactTrackScoreCache::entries() const noexcept {
    return entries_.size();
}

std::size_t ExactTrackScoreCache::logical_bytes() const noexcept {
    std::size_t total = entries_.size() * sizeof(Entry);
    for (const auto& entry : entries_) total += track_bytes(entry.owned);
    return total;
}

}  // namespace leo::adaptive::location::research
