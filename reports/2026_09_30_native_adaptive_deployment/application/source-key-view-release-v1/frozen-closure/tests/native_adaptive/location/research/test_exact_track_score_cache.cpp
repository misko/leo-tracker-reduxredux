#include "exact_track_score_cache.hpp"

#include <cassert>
#include <cmath>

using leo::adaptive::location::research::ExactScoreScope;
using leo::adaptive::location::research::ExactTrackScoreCache;

namespace {
leo::adaptive::pipeline::OwnedLocationTrack track() {
    return {"sha256:track", "sha256:support", "sha256:partition",
        {"observation-a", "observation-b"}, {1.0, 2.0}, {3.0, 4.0}, {1, 0}};
}

leo_location_track record(const leo::adaptive::pipeline::OwnedLocationTrack& owned) {
    return {7, 2, 2, owned.times_s.data(), owned.measured_hz.data(),
        owned.training_mask.data()};
}

ExactScoreScope scope() {
    ExactScoreScope value{};
    value.stream_generation = 1;
    value.orbit_generation = 2;
    value.site.ecef_km[0] = 1.0;
    value.site.ecef_km[1] = 2.0;
    value.site.ecef_km[2] = 3.0;
    value.site.up[0] = 0.0;
    value.site.up[1] = 0.0;
    value.site.up[2] = 1.0;
    value.config = leo_score_default_config();
    return value;
}

bool hit(ExactTrackScoreCache& cache, const leo::adaptive::pipeline::OwnedLocationTrack& owned) {
    leo_track_score score{};
    leo_score_stats stats{};
    return cache.lookup(owned, record(owned), &score, &stats);
}
}  // namespace

int main() {
    ExactTrackScoreCache cache;
    auto authority = track();
    auto key = scope();
    const leo_track_score score{1, 42, -2, 3.0, 4.0, 5.0};
    const leo_score_stats stats{10, 11};
    cache.begin(key);
    cache.store(authority, record(authority), score, stats);
    assert(hit(cache, authority));
    assert(cache.entries() == 1 && cache.logical_bytes() > sizeof(score) + sizeof(stats));

    auto changed = authority;
    changed.support_digest += "-changed";
    assert(!hit(cache, changed));
    changed = authority;
    changed.training_mask[0] = 0;
    assert(!hit(cache, changed));
    changed = authority;
    changed.measured_hz[0] = std::nextafter(changed.measured_hz[0], INFINITY);
    assert(!hit(cache, changed));
    auto changed_record = record(authority);
    ++changed_record.weight_s;
    leo_track_score ignored_score{};
    leo_score_stats ignored_stats{};
    assert(!cache.lookup(authority, changed_record, &ignored_score, &ignored_stats));

    auto changed_scope = key;
    changed_scope.site.ecef_km[0] = std::nextafter(changed_scope.site.ecef_km[0], INFINITY);
    cache.begin(changed_scope);
    assert(cache.entries() == 0 && !hit(cache, authority));
    cache.begin(key); cache.store(authority, record(authority), score, stats);
    changed_scope = key; changed_scope.config.carrier_hz =
        std::nextafter(changed_scope.config.carrier_hz, INFINITY);
    cache.begin(changed_scope); assert(cache.entries() == 0);
    cache.begin(key); cache.store(authority, record(authority), score, stats);
    changed_scope = key; ++changed_scope.orbit_generation;
    cache.begin(changed_scope); assert(cache.entries() == 0);
    cache.begin(key); cache.store(authority, record(authority), score, stats);
    changed_scope = key; ++changed_scope.stream_generation;
    cache.begin(changed_scope); assert(cache.entries() == 0);
    return 0;
}
