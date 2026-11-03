#include "exact_track_score_cache.hpp"
#include "tle_id.hpp"
#include "tracking.hpp"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <tuple>
#include <unordered_map>
#include <vector>

namespace {
using Owned = leo::adaptive::pipeline::OwnedLocationTrack;
using Batch = leo::adaptive::pipeline::LocationTrackBatch;
using Cache = leo::adaptive::location::research::ExactTrackScoreCache;
using Scope = leo::adaptive::location::research::ExactScoreScope;

std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> result;
    std::size_t begin = 0;
    for (;;) {
        const auto end = line.find('\t', begin);
        result.push_back(line.substr(begin, end - begin));
        if (end == std::string::npos) return result;
        begin = end + 1;
    }
}

template <class T> T integer(const std::string& text) {
    errno = 0;
    char* end = nullptr;
    const long long value = std::strtoll(text.c_str(), &end, 10);
    if (errno || end != text.c_str() + text.size() ||
        value < static_cast<long long>(std::numeric_limits<T>::min()) ||
        value > static_cast<long long>(std::numeric_limits<T>::max()))
        throw std::runtime_error("invalid integer fixture field");
    return static_cast<T>(value);
}

double number(const std::string& text) {
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (end != text.c_str() + text.size()) throw std::runtime_error("invalid number field");
    return value;
}

struct Fixture {
    leo::adaptive::pipeline::GraphAuthority graph;
    std::vector<leo::adaptive::tracking::Candidate> candidates;
};

Fixture load_fixture(const std::string& candidates_path, const std::string& graph_path) {
    Fixture fixture;
    std::ifstream graph_input(graph_path);
    std::string line;
    if (!std::getline(graph_input, line)) throw std::runtime_error("missing graph metadata");
    const auto meta = fields(line);
    if (meta.size() != 4 || meta[0] != "META") throw std::runtime_error("bad graph metadata");
    fixture.graph.session_id = meta[1];
    fixture.graph.input_manifest_digest = meta[2];
    fixture.graph.session_start_utc_ns = integer<std::int64_t>(meta[3]);
    if (!std::getline(graph_input, line)) throw std::runtime_error("missing graph header");
    while (std::getline(graph_input, line)) {
        const auto row = fields(line);
        if (row.size() != 8) throw std::runtime_error("bad graph row");
        fixture.graph.candidates.emplace(row[0], leo::adaptive::pipeline::SupportAuthority{
            integer<std::int64_t>(row[1]), integer<std::int64_t>(row[2]),
            integer<std::int64_t>(row[3]), row[4], row[5], row[6], row[7]});
    }

    std::ifstream candidate_input(candidates_path);
    if (!std::getline(candidate_input, line)) throw std::runtime_error("missing candidates");
    while (std::getline(candidate_input, line)) {
        const auto row = fields(line);
        if (row.size() != 13) throw std::runtime_error("bad candidate row");
        fixture.candidates.push_back(leo::adaptive::tracking::Candidate{
            row[0], row[1], integer<int>(row[2]), integer<int>(row[3]), row[4], number(row[5]),
            integer<std::int64_t>(row[6]), integer<std::int64_t>(row[7]),
            integer<std::int64_t>(row[8]), number(row[9]), number(row[10]),
            number(row[11]), number(row[12])});
    }
    std::sort(fixture.candidates.begin(), fixture.candidates.end(), [](const auto& a, const auto& b) {
        return std::tie(a.support_end_utc_ns, a.candidate_id) <
            std::tie(b.support_end_utc_ns, b.candidate_id);
    });
    return fixture;
}

std::vector<std::int64_t> causal_cutoffs(const Fixture& fixture) {
    const auto first = fixture.candidates.front().support_end_utc_ns;
    const auto last = fixture.candidates.back().support_end_utc_ns;
    std::vector<std::int64_t> result;
    auto cutoff = first;
    while (cutoff < last) {
        cutoff = std::min(cutoff + static_cast<std::int64_t>(5'000'000'000LL), last);
        result.push_back(cutoff);
    }
    return result;
}

Batch make_prefix(const Fixture& fixture, std::size_t ordinal, std::size_t* candidate_count) {
    const auto cutoffs = causal_cutoffs(fixture);
    if (ordinal == 0 || ordinal > cutoffs.size()) throw std::runtime_error("bad prefix ordinal");
    std::vector<leo::adaptive::tracking::Candidate> prefix;
    for (const auto& candidate : fixture.candidates)
        if (candidate.support_end_utc_ns <= cutoffs[ordinal - 1]) prefix.push_back(candidate);
    *candidate_count = prefix.size();
    return leo::adaptive::pipeline::make_location_tracks(
        leo::adaptive::tracking::reconstruct(prefix), fixture.graph);
}

std::vector<leo_tle_record> load_tles(const std::string& path) {
    std::ifstream input(path);
    std::size_t count = 0;
    if (!(input >> count) || count == 0 || count > 20'000)
        throw std::runtime_error("cannot read TLE count");
    input.ignore(1024, '\n');
    std::vector<leo_tle_record> result(count);
    for (std::size_t index = 0; index < count; ++index) {
        std::string one, two;
        std::getline(input, one); std::getline(input, two);
        if (one.size() != 69 || two.size() != 69 ||
            !leo::adaptive::location::parse_tle_catalogue_id(
                std::string_view(one).substr(2, 5), result[index].satellite_id))
            throw std::runtime_error("bad TLE");
        std::memcpy(result[index].line1, one.data(), 69);
        std::memcpy(result[index].line2, two.data(), 69);
        result[index].line1[69] = result[index].line2[69] = '\0';
    }
    return result;
}

leo_location_site fixed_site() {
    constexpr double pi = 3.14159265358979323846;
    constexpr double semi_major_axis_km = 6378.137;
    constexpr double flattening = 1.0 / 298.257223563;
    constexpr double eccentricity_squared = flattening * (2.0 - flattening);
    const double latitude = 38.5 * pi / 180.0;
    const double longitude = -121.5 * pi / 180.0;
    const double prime_vertical = semi_major_axis_km /
        std::sqrt(1.0 - eccentricity_squared * std::sin(latitude) * std::sin(latitude));
    leo_location_site result{};
    result.ecef_km[0] = prime_vertical * std::cos(latitude) * std::cos(longitude);
    result.ecef_km[1] = prime_vertical * std::cos(latitude) * std::sin(longitude);
    result.ecef_km[2] = prime_vertical * (1.0 - eccentricity_squared) * std::sin(latitude);
    result.up[0] = std::cos(latitude) * std::cos(longitude);
    result.up[1] = std::cos(latitude) * std::sin(longitude);
    result.up[2] = std::sin(latitude);
    return result;
}

struct ContextDelete { void operator()(leo_score_context* value) const { leo_score_context_destroy(value); } };
struct OrbitDelete { void operator()(leo_orbit_context* value) const { leo_orbit_context_destroy(value); } };
using Context = std::unique_ptr<leo_score_context, ContextDelete>;
using Orbit = std::unique_ptr<leo_orbit_context, OrbitDelete>;

bool same_double(double left, double right) {
    return std::memcmp(&left, &right, sizeof(left)) == 0;
}

bool same_score(const leo_track_score& left, const leo_track_score& right) {
    return left.matched == right.matched && left.candidate_id == right.candidate_id &&
        left.tau_s == right.tau_s && same_double(left.heldout_rms_hz, right.heldout_rms_hz) &&
        same_double(left.training_rms_hz, right.training_rms_hz) &&
        same_double(left.frequency_offset_hz, right.frequency_offset_hz);
}

bool same_point(const leo_point_score& left, const leo_point_score& right) {
    return same_double(left.weighted_mse_hz2, right.weighted_mse_hz2) &&
        same_double(left.residual_rmse_hz, right.residual_rmse_hz) &&
        left.matched_track_count == right.matched_track_count &&
        left.unmatched_track_count == right.unmatched_track_count;
}

void add_stats(leo_score_stats* destination, const leo_score_stats& source) {
    if (UINT64_MAX - destination->rejected_satellite_tracks < source.rejected_satellite_tracks ||
        UINT64_MAX - destination->evaluated_satellite_tracks < source.evaluated_satellite_tracks)
        throw std::runtime_error("score statistics overflow");
    destination->rejected_satellite_tracks += source.rejected_satellite_tracks;
    destination->evaluated_satellite_tracks += source.evaluated_satellite_tracks;
}

struct Scored {
    std::vector<leo_track_score> tracks;
    leo_score_stats stats{};
    leo_point_score point{};
};

Scored score_bulk(leo_score_context* context, const leo_orbit_snapshot& orbit,
                  const Batch& batch, const leo_location_site& site,
                  const leo_score_config& config) {
    Scored result;
    result.tracks.resize(batch.records.size());
    leo_track_scores_clear(result.tracks.data(), static_cast<std::uint32_t>(result.tracks.size()));
    if (leo_score_partition(context, &orbit, batch.records.data(),
            static_cast<std::uint32_t>(batch.records.size()), &site, &config, 0,
            orbit.satellite_count, result.tracks.data(), &result.stats) != LEO_LOCATION_OK ||
        leo_point_score_finish(batch.records.data(), static_cast<std::uint32_t>(batch.records.size()),
            result.tracks.data(), &config, &result.point) != LEO_LOCATION_OK)
        throw std::runtime_error("bulk score failed");
    return result;
}

std::pair<leo_track_score, leo_score_stats> score_one(
    leo_score_context* context, const leo_orbit_snapshot& orbit,
    const leo_location_track& track, const leo_location_site& site,
    const leo_score_config& config) {
    leo_track_score score{};
    leo_score_stats stats{};
    leo_track_scores_clear(&score, 1);
    if (leo_score_partition(context, &orbit, &track, 1, &site, &config, 0,
            orbit.satellite_count, &score, &stats) != LEO_LOCATION_OK)
        throw std::runtime_error("single-track score failed");
    return {score, stats};
}

void require_exact(const Scored& left, const Scored& right, const char* label) {
    if (left.tracks.size() != right.tracks.size()) throw std::runtime_error(label);
    for (std::size_t index = 0; index < left.tracks.size(); ++index)
        if (!same_score(left.tracks[index], right.tracks[index])) throw std::runtime_error(label);
    if (left.stats.rejected_satellite_tracks != right.stats.rejected_satellite_tracks ||
        left.stats.evaluated_satellite_tracks != right.stats.evaluated_satellite_tracks ||
        !same_point(left.point, right.point)) throw std::runtime_error(label);
}

Scored score_individual(leo_score_context* context, const leo_orbit_snapshot& orbit,
                        const Batch& batch, const leo_location_site& site,
                        const leo_score_config& config, Cache* cache) {
    Scored result;
    result.tracks.resize(batch.records.size());
    for (std::size_t index = 0; index < batch.records.size(); ++index) {
        const auto scored = score_one(context, orbit, batch.records[index], site, config);
        result.tracks[index] = scored.first;
        add_stats(&result.stats, scored.second);
        if (cache) cache->store(batch.owned[index], batch.records[index], scored.first, scored.second);
    }
    if (leo_point_score_finish(batch.records.data(), static_cast<std::uint32_t>(batch.records.size()),
            result.tracks.data(), &config, &result.point) != LEO_LOCATION_OK)
        throw std::runtime_error("individual finish failed");
    return result;
}

struct Reused {
    Scored scored;
    std::size_t hits{};
    std::size_t misses{};
};

Reused score_reused(leo_score_context* context, const leo_orbit_snapshot& orbit,
                    const Batch& batch, const leo_location_site& site,
                    const leo_score_config& config, Cache* cache) {
    Reused result;
    result.scored.tracks.resize(batch.records.size());
    for (std::size_t index = 0; index < batch.records.size(); ++index) {
        leo_score_stats stats{};
        if (cache->lookup(batch.owned[index], batch.records[index],
                &result.scored.tracks[index], &stats)) {
            ++result.hits;
        } else {
            const auto scored = score_one(context, orbit, batch.records[index], site, config);
            result.scored.tracks[index] = scored.first;
            stats = scored.second;
            cache->store(batch.owned[index], batch.records[index], scored.first, scored.second);
            ++result.misses;
        }
        add_stats(&result.scored.stats, stats);
    }
    if (leo_point_score_finish(batch.records.data(), static_cast<std::uint32_t>(batch.records.size()),
            result.scored.tracks.data(), &config, &result.scored.point) != LEO_LOCATION_OK)
        throw std::runtime_error("reuse finish failed");
    return result;
}

double elapsed(const std::chrono::steady_clock::time_point& start) {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
}
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 4)
            throw std::runtime_error("usage: test_ds9_exact_score_reuse CANDIDATES GRAPH TLES");
        const Fixture fixture = load_fixture(argv[1], argv[2]);
        std::size_t count58 = 0, count59 = 0;
        Batch prefix58 = make_prefix(fixture, 58, &count58);
        Batch prefix59 = make_prefix(fixture, 59, &count59);
        if (count58 != 11'389 || count59 != 11'566 ||
            prefix58.records.size() != 64 || prefix59.records.size() != 64)
            throw std::runtime_error("unexpected causal prefix shape");

        const auto catalogue = load_tles(argv[3]);
        Orbit orbit_context(leo_orbit_context_create(
            static_cast<std::uint32_t>(catalogue.size()), 96));
        Context score_context(leo_score_context_create(100'000, 11));
        if (!orbit_context || !score_context) throw std::runtime_error("context allocation failed");
        leo_orbit_snapshot orbit{};
        if (leo_orbit_build_tle(orbit_context.get(), 1, fixture.graph.session_start_utc_ns,
                -10.0, 10.0, 96, catalogue.data(),
                static_cast<std::uint32_t>(catalogue.size()), &orbit) != LEO_LOCATION_OK)
            throw std::runtime_error("orbit build failed");
        const auto site = fixed_site();
        const auto config = leo_score_default_config();
        const Scope scope{1, orbit.generation, site, config};

        const auto cold58_start = std::chrono::steady_clock::now();
        const Scored cold58 = score_bulk(score_context.get(), orbit, prefix58, site, config);
        const double cold58_seconds = elapsed(cold58_start);
        Cache seeded;
        seeded.begin(scope);
        const auto seed_start = std::chrono::steady_clock::now();
        const Scored individual58 = score_individual(
            score_context.get(), orbit, prefix58, site, config, &seeded);
        const double seed_seconds = elapsed(seed_start);
        require_exact(cold58, individual58, "prefix58 individual score differs");
        const std::size_t seed_bytes = seeded.logical_bytes();

        const auto cold59_start = std::chrono::steady_clock::now();
        const Scored cold59 = score_bulk(score_context.get(), orbit, prefix59, site, config);
        const double cold59_seconds = elapsed(cold59_start);
        Cache reuse_cache = seeded;
        reuse_cache.begin(scope);
        const auto reuse_start = std::chrono::steady_clock::now();
        const Reused reused59 = score_reused(
            score_context.get(), orbit, prefix59, site, config, &reuse_cache);
        const double reuse_seconds = elapsed(reuse_start);
        require_exact(cold59, reused59.scored, "prefix59 reused score differs");
        if (reused59.hits != 55 || reused59.misses != 9)
            throw std::runtime_error("unexpected exact cache hit inventory");

        std::cout << std::setprecision(17)
            << "{\"schema\":\"leo-exact-track-score-reuse-research/v1\","
            << "\"prefix_from_ordinal\":58,\"prefix_to_ordinal\":59,"
            << "\"prefix_from_candidates\":" << count58 << ','
            << "\"prefix_to_candidates\":" << count59 << ','
            << "\"prefix_from_tracks\":" << prefix58.records.size() << ','
            << "\"prefix_to_tracks\":" << prefix59.records.size() << ','
            << "\"catalogue_records\":" << catalogue.size() << ','
            << "\"orbit_generation\":" << orbit.generation << ','
            << "\"orbit_knots\":96,\"orbit_knot_step_s\":10,"
            << "\"cache_hits\":" << reused59.hits << ','
            << "\"cache_misses\":" << reused59.misses << ','
            << "\"seed_cache_logical_bytes\":" << seed_bytes << ','
            << "\"final_cache_logical_bytes\":" << reuse_cache.logical_bytes() << ','
            << "\"cold_prefix58_seconds\":" << cold58_seconds << ','
            << "\"seed_individual_seconds\":" << seed_seconds << ','
            << "\"cold_prefix59_seconds\":" << cold59_seconds << ','
            << "\"reuse_prefix59_seconds\":" << reuse_seconds << ','
            << "\"weighted_mse_hz2\":" << cold59.point.weighted_mse_hz2 << ','
            << "\"matched_tracks\":" << cold59.point.matched_track_count << ','
            << "\"unmatched_tracks\":" << cold59.point.unmatched_track_count << ','
            << "\"evaluated_satellite_tracks\":"
            << cold59.stats.evaluated_satellite_tracks << ','
            << "\"rejected_satellite_tracks\":"
            << cold59.stats.rejected_satellite_tracks << ','
            << "\"track_winners_bit_exact\":true,\"point_score_bit_exact\":true,"
            << "\"statistics_exact\":true,\"publication_generation_in_cache_key\":false}"
            << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "exact score reuse research: " << error.what() << '\n';
        return 1;
    }
}
