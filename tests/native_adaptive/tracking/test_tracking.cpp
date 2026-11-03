#include "tracking.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using leo::adaptive::tracking::Candidate;
using leo::adaptive::tracking::Config;
using leo::adaptive::tracking::Result;

void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

std::string identity(int value) {
    std::ostringstream out;
    out << "sha256:" << std::hex << std::setfill('0') << std::setw(64) << value;
    return out.str();
}

std::vector<Candidate> fixture() {
    constexpr std::int64_t base = 1'800'000'000'000'000'000LL;
    constexpr double spacing = 1.0 / 4.4e-6;
    std::vector<Candidate> rows;
    for (int index = 0; index < 9; ++index) {
        const std::int64_t center = base + static_cast<std::int64_t>(index) * 600'000'000LL;
        const double time = 0.6 * index;
        const int alias = index % 3 - 1;
        const double raw = 31'000.0 + 1'250.0 * time + alias * spacing;
        rows.push_back(Candidate{
            identity(index+1), identity(index+101), 0, 1,
            "lower", 11'200'000'000.0, center - 20'000'000, center, center + 20'000'000,
            raw, 1.25, 0.25, 1.0,
        });
    }
    // A competing candidate from an existing source group has less evidence and must lose.
    Candidate duplicate = rows[4];
    duplicate.candidate_id = identity(51);
    duplicate.measured_cfo_hz += 500.0;
    duplicate.exact_score = 0.26;
    duplicate.margin = 0.01;
    rows.push_back(duplicate);
    // A finite positive-margin point below the minimum weight cannot support the line.
    Candidate noise = rows[0];
    noise.candidate_id = identity(52);
    noise.source_group_id = identity(152);
    noise.support_start_utc_ns += 5'000'000'000LL;
    noise.support_center_utc_ns += 5'000'000'000LL;
    noise.support_end_utc_ns += 5'000'000'000LL;
    noise.measured_cfo_hz = 100'000.0;
    noise.exact_score = 0.251;
    noise.margin = 0.001;
    rows.push_back(noise);
    return rows;
}

bool same_double(double left, double right) {
    std::uint64_t left_bits = 0, right_bits = 0;
    std::memcpy(&left_bits, &left, sizeof(left));
    std::memcpy(&right_bits, &right, sizeof(right));
    return left_bits == right_bits;
}

bool same_result(const Result& left, const Result& right) {
    if (left.input_candidate_count != right.input_candidate_count ||
        left.used_candidate_count != right.used_candidate_count ||
        left.config_digest != right.config_digest ||
        left.tracks.size() != right.tracks.size()) return false;
    for (std::size_t track_index = 0; track_index < left.tracks.size(); ++track_index) {
        const auto& a = left.tracks[track_index];
        const auto& b = right.tracks[track_index];
        if (a.segment_id != b.segment_id || a.tracklet_id != b.tracklet_id ||
            a.lane.channel != b.lane.channel || a.lane.edge != b.lane.edge ||
            a.lane.receiver_id != b.lane.receiver_id ||
            !same_double(a.lane.actual_rf_hz, b.lane.actual_rf_hz) ||
            a.start_utc_ns != b.start_utc_ns || a.end_utc_ns != b.end_utc_ns ||
            a.reference_utc_ns != b.reference_utc_ns ||
            !same_double(a.normalized_rate_hz_per_s, b.normalized_rate_hz_per_s) ||
            !same_double(a.normalized_intercept_hz, b.normalized_intercept_hz) ||
            !same_double(a.residual_rms_hz, b.residual_rms_hz) ||
            !same_double(a.residual_max_hz, b.residual_max_hz) ||
            !same_double(a.weighted_support, b.weighted_support) ||
            a.points.size() != b.points.size()) return false;
        for (std::size_t point_index = 0; point_index < a.points.size(); ++point_index) {
            const auto& x = a.points[point_index];
            const auto& y = b.points[point_index];
            if (x.candidate_id != y.candidate_id ||
                x.source_group_id != y.source_group_id ||
                x.relative_alias_index != y.relative_alias_index ||
                !same_double(x.normalized_raw_cfo_hz, y.normalized_raw_cfo_hz) ||
                !same_double(x.normalized_dealiased_cfo_hz,
                    y.normalized_dealiased_cfo_hz)) return false;
        }
    }
    return true;
}

void test_alias_track_and_permutation_invariance() {
    auto rows = fixture();
    const auto first = leo::adaptive::tracking::reconstruct(rows);
    require(first.input_candidate_count == 11, "input count differs");
    require(first.used_candidate_count == 9, "used count differs");
    require(first.tracks.size() == 1, "track count differs");
    const auto& track = first.tracks.front();
    require(track.points.size() == 9, "track support differs");
    require(std::abs(track.normalized_rate_hz_per_s - 1250.0) < 1e-7, "slope differs");
    require(std::abs(track.normalized_intercept_hz - 31000.0) < 1e-6, "intercept differs");
    require(track.residual_max_hz < 1e-6, "residual differs");
    require(track.segment_id ==
            "sha256:f474cd4982fddd1e7397bbfe1fdca99fa745f2f63a619fdb34b20920cc07853a",
            "segment identity differs");
    for (std::size_t index = 0; index < track.points.size(); ++index) {
        require(track.points[index].candidate_id == identity(static_cast<int>(index)+1),
                "point membership differs");
        require(track.points[index].relative_alias_index == static_cast<int>(index % 3) - 1,
                "relative alias differs");
    }

    std::reverse(rows.begin(), rows.end());
    const auto second = leo::adaptive::tracking::reconstruct(rows);
    require(second.tracks.size() == 1, "permuted track count differs");
    require(second.tracks.front().segment_id == track.segment_id,
            "result depends on input permutation");
}

void test_same_source_equal_numeric_rank_uses_lexical_candidate_id() {
    auto base = fixture();
    base.resize(9);
    std::vector<Candidate> rows;
    rows.reserve(base.size() * 2);
    for (std::size_t index = 0; index < base.size(); ++index) {
        Candidate lexical_loser = base[index];
        lexical_loser.candidate_id = identity(500 + static_cast<int>(index));
        rows.push_back(lexical_loser);
        rows.push_back(base[index]);
    }

    const auto first = leo::adaptive::tracking::reconstruct(rows);
    require(first.tracks.size() == 1, "equal-rank fixture lost its track");
    require(first.tracks.front().points.size() == base.size(),
        "equal-rank fixture changed support");
    for (std::size_t index = 0; index < base.size(); ++index)
        require(first.tracks.front().points[index].candidate_id ==
            base[index].candidate_id,
            "equal numeric rank did not use lexical candidate identity");

    std::reverse(rows.begin(), rows.end());
    const auto reversed = leo::adaptive::tracking::reconstruct(rows);
    require(same_result(first, reversed),
        "equal-rank lexical choice depends on input order");
}

void test_validation() {
    auto rows = fixture();
    rows[1].candidate_id = rows[0].candidate_id;
    bool rejected = false;
    try {
        (void)leo::adaptive::tracking::reconstruct(rows);
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    require(rejected, "duplicate candidate identity was accepted");

    Config invalid;
    invalid.slope_bins = 1;
    rejected = false;
    try {
        (void)leo::adaptive::tracking::reconstruct(fixture(), invalid);
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    require(rejected, "invalid work bounds were accepted");
}

void test_bin_cache_bounded_fallbacks() {
    Config oversized_bins;
    oversized_bins.slope_bins = 25;
    oversized_bins.intercept_bins = 65'537;
    oversized_bins.maximum_tracks_per_lane = 1;
    const auto fallback = leo::adaptive::tracking::reconstruct(fixture(), oversized_bins);
    require(fallback.tracks.size() == 1, "oversized-bin fallback lost the track");
    require(fallback.tracks.front().segment_id ==
            "sha256:f474cd4982fddd1e7397bbfe1fdca99fa745f2f63a619fdb34b20920cc07853a",
            "oversized-bin fallback changed membership");

    Config insufficient_support;
    insufficient_support.slope_bins = 1'000'000;
    insufficient_support.minimum_support = 20;
    const auto empty = leo::adaptive::tracking::reconstruct(fixture(), insufficient_support);
    require(empty.tracks.empty(), "insufficient support unexpectedly produced a track");
}

void test_persistent_exact_prefix_and_invalidations() {
    auto rows = fixture();
    std::sort(rows.begin(), rows.end(), [](const Candidate& left, const Candidate& right) {
        return std::tie(left.support_center_utc_ns, left.measured_cfo_hz,
                   left.candidate_id) <
            std::tie(right.support_center_utc_ns, right.measured_cfo_hz,
                   right.candidate_id);
    });
    leo::adaptive::tracking::Reconstructor stateful;
    std::vector<Candidate> prefix(rows.begin(), rows.begin() + 6);
    require(same_result(stateful.reconstruct(prefix),
        leo::adaptive::tracking::reconstruct(prefix)),
        "cold persistent result differs");
    auto stats = stateful.stats();
    require(stats.last_cold_fallback && stats.cold_starts == 1,
        "first persistent call was not cold");
    require(stats.resident_cache_bytes <= stats.maximum_cache_bytes,
        "persistent cache exceeds budget");

    prefix.push_back(rows[6]);
    require(same_result(stateful.reconstruct(prefix),
        leo::adaptive::tracking::reconstruct(prefix)),
        "extended persistent result differs");
    stats = stateful.stats();
    require(!stats.last_cold_fallback && stats.last_extended_lanes == 1,
        "exact prefix did not extend the lane");
    require(same_result(stateful.reconstruct(prefix),
        leo::adaptive::tracking::reconstruct(prefix)),
        "reused persistent result differs");
    require(stateful.stats().last_reused_lanes == 1,
        "unchanged prefix did not reuse the lane");

    auto reordered = prefix;
    std::swap(reordered[0], reordered[1]);
    require(same_result(stateful.reconstruct(reordered),
        leo::adaptive::tracking::reconstruct(reordered)),
        "reordered cold result differs");
    require(stateful.stats().last_cold_fallback &&
        stateful.stats().prefix_invalidations == 1,
        "candidate reorder did not invalidate");

    auto expired = reordered;
    expired.erase(expired.begin());
    require(same_result(stateful.reconstruct(expired),
        leo::adaptive::tracking::reconstruct(expired)),
        "expired cold result differs");
    require(stateful.stats().prefix_invalidations == 2,
        "candidate expiry did not invalidate");

    Config changed;
    changed.peak_candidates = 63;
    require(same_result(stateful.reconstruct(expired, changed),
        leo::adaptive::tracking::reconstruct(expired, changed)),
        "config-change cold result differs");
    require(stateful.stats().config_invalidations == 1,
        "config change did not invalidate");

    auto changed_rf = expired;
    for (auto& candidate : changed_rf) candidate.actual_rf_hz += 1.0;
    require(same_result(stateful.reconstruct(changed_rf, changed),
        leo::adaptive::tracking::reconstruct(changed_rf, changed)),
        "RF-change cold result differs");
    require(stateful.stats().prefix_invalidations == 3,
        "RF change did not invalidate");
}

void test_persistent_global_capacity_fallback() {
    const Candidate base = fixture().front();
    std::vector<Candidate> rows;
    for (int index = 0; index < 256; ++index) {
        Candidate candidate = base;
        candidate.candidate_id = identity(10'000 + index);
        candidate.source_group_id = identity(20'000 + index);
        candidate.support_start_utc_ns += static_cast<std::int64_t>(index) *
            100'000'000LL;
        candidate.support_center_utc_ns += static_cast<std::int64_t>(index) *
            100'000'000LL;
        candidate.support_end_utc_ns += static_cast<std::int64_t>(index) *
            100'000'000LL;
        candidate.measured_cfo_hz += 125.0 * index;
        rows.push_back(std::move(candidate));
    }
    leo::adaptive::tracking::Reconstructor stateful(1024U);
    require(same_result(stateful.reconstruct(rows),
        leo::adaptive::tracking::reconstruct(rows)),
        "capacity cold result differs");
    const auto stats = stateful.stats();
    require(stats.last_cold_fallback && stats.capacity_fallbacks == 1,
        "small global budget did not fall back");
    require(stats.resident_cache_bytes == 0 && stats.cached_lanes == 0,
        "capacity fallback retained cache allocation");
    require(stats.last_bin_cells_computed == 0,
        "tiny budget performed bin-cache work before fallback");
}

}  // namespace

int main() {
    try {
        test_alias_track_and_permutation_invariance();
        test_same_source_equal_numeric_rank_uses_lexical_candidate_id();
        test_validation();
        test_bin_cache_bounded_fallbacks();
        test_persistent_exact_prefix_and_invalidations();
        test_persistent_global_capacity_fallback();
        std::cout << "tracking unit tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
