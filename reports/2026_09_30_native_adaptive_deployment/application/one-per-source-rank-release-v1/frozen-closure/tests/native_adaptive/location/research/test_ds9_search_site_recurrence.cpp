#include "exact_track_score_cache.hpp"
#include "tle_id.hpp"
#include "tracking.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <thread>
#include <tuple>
#include <vector>

namespace {
using Batch = leo::adaptive::pipeline::LocationTrackBatch;
using Owned = leo::adaptive::pipeline::OwnedLocationTrack;

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

leo_location_site make_site(double origin_latitude_deg, double origin_longitude_deg,
                            double east_km, double north_km) {
    constexpr double pi = 3.14159265358979323846;
    constexpr double mean_earth_radius_km = 6371.0088;
    constexpr double semi_major_axis_km = 6378.137;
    constexpr double flattening = 1.0 / 298.257223563;
    constexpr double eccentricity_squared = flattening * (2.0 - flattening);
    const double angular = std::hypot(east_km, north_km) / mean_earth_radius_km;
    const double bearing = std::atan2(east_km, north_km);
    const double latitude0 = origin_latitude_deg * pi / 180.0;
    const double longitude0 = origin_longitude_deg * pi / 180.0;
    const double latitude = std::asin(std::sin(latitude0) * std::cos(angular) +
        std::cos(latitude0) * std::sin(angular) * std::cos(bearing));
    const double longitude = longitude0 + std::atan2(
        std::sin(bearing) * std::sin(angular) * std::cos(latitude0),
        std::cos(angular) - std::sin(latitude0) * std::sin(latitude));
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

std::uint64_t bits(double value) {
    std::uint64_t result = 0;
    static_assert(sizeof(result) == sizeof(value));
    std::memcpy(&result, &value, sizeof(result));
    return result;
}

struct SiteKey {
    std::array<std::uint64_t, 6> words{};
    bool operator<(const SiteKey& other) const { return words < other.words; }
    bool operator==(const SiteKey& other) const { return words == other.words; }
};

SiteKey key(const leo_location_site& site) {
    return SiteKey{{bits(site.ecef_km[0]), bits(site.ecef_km[1]), bits(site.ecef_km[2]),
                    bits(site.up[0]), bits(site.up[1]), bits(site.up[2])}};
}

struct ContextDelete { void operator()(leo_score_context* p) const { leo_score_context_destroy(p); } };
struct OrbitDelete { void operator()(leo_orbit_context* p) const { leo_orbit_context_destroy(p); } };
struct SearchDelete { void operator()(leo_search_context* p) const { leo_search_context_destroy(p); } };
using Context = std::unique_ptr<leo_score_context, ContextDelete>;
using Orbit = std::unique_ptr<leo_orbit_context, OrbitDelete>;
using Search = std::unique_ptr<leo_search_context, SearchDelete>;

struct ScoreEngine {
    std::array<Context, 2> contexts;
    std::array<std::vector<leo_track_score>, 2> partials;
    explicit ScoreEngine(std::uint32_t maximum_observations, std::size_t tracks)
        : contexts{Context(leo_score_context_create(maximum_observations, 11)),
                   Context(leo_score_context_create(maximum_observations, 11))} {
        if (!contexts[0] || !contexts[1]) throw std::runtime_error("score allocation failed");
        for (auto& partial : partials) partial.resize(tracks);
    }
};

double score_site(ScoreEngine* engine, const leo_orbit_snapshot& orbit, const Batch& batch,
                  const leo_location_site& site, const leo_score_config& config) {
    std::array<leo_location_status, 2> statuses{LEO_LOCATION_STATE, LEO_LOCATION_STATE};
    std::array<leo_score_stats, 2> stats{};
    std::array<std::thread, 2> threads;
    for (std::size_t worker = 0; worker < 2; ++worker) {
        threads[worker] = std::thread([&, worker] {
            auto& partial = engine->partials[worker];
            leo_track_scores_clear(partial.data(), static_cast<std::uint32_t>(partial.size()));
            const auto begin = static_cast<std::uint32_t>(
                static_cast<std::uint64_t>(orbit.satellite_count) * worker / 2);
            const auto end = static_cast<std::uint32_t>(
                static_cast<std::uint64_t>(orbit.satellite_count) * (worker + 1) / 2);
            statuses[worker] = leo_score_partition(engine->contexts[worker].get(), &orbit,
                batch.records.data(), static_cast<std::uint32_t>(batch.records.size()),
                &site, &config, begin, end, partial.data(), &stats[worker]);
        });
    }
    for (auto& thread : threads) thread.join();
    if (statuses[0] != LEO_LOCATION_OK || statuses[1] != LEO_LOCATION_OK ||
        leo_track_scores_reduce(engine->partials[0].data(), engine->partials[1].data(),
            static_cast<std::uint32_t>(batch.records.size())) != LEO_LOCATION_OK)
        throw std::runtime_error("partition score failed");
    leo_point_score point{};
    if (leo_point_score_finish(batch.records.data(), static_cast<std::uint32_t>(batch.records.size()),
            engine->partials[0].data(), &config, &point) != LEO_LOCATION_OK)
        throw std::runtime_error("point score failed");
    return point.weighted_mse_hz2;
}

std::size_t track_logical_bytes(const Owned& track) {
    std::size_t result = sizeof(Owned) + track.tracklet_id.size() + track.support_digest.size() +
        track.partition_seed.size() + track.times_s.size() * sizeof(double) +
        track.measured_hz.size() * sizeof(double) + track.training_mask.size();
    for (const auto& value : track.observation_ids) result += value.size();
    return result;
}

std::size_t exact_track_overlap(const Batch& left, const Batch& right) {
    std::size_t count = 0;
    for (std::size_t r = 0; r < right.records.size(); ++r) {
        for (std::size_t l = 0; l < left.records.size(); ++l) {
            if (leo::adaptive::location::research::exact_track_equal(
                    left.owned[l], left.records[l], right.owned[r], right.records[r])) {
                ++count;
                break;
            }
        }
    }
    return count;
}

struct Evaluation {
    double east{};
    double north{};
    double mse{};
    leo_location_site site{};
    SiteKey site_key{};
};

struct SearchRun {
    std::vector<Evaluation> evaluations;
    leo_search_result result{};
    double seconds{};
};

SearchRun run_search(std::uint64_t generation, const leo_orbit_snapshot& orbit,
                     const Batch& batch, std::ofstream* raw) {
    constexpr double latitude = 38.5816;
    constexpr double longitude = -121.4944;
    Search search(leo_search_context_create(400));
    if (!search) throw std::runtime_error("search allocation failed");
    const auto policy = leo_search_default_policy(250.0);
    const auto config = leo_score_default_config();
    std::uint32_t maximum_observations = 0;
    for (const auto& record : batch.records)
        maximum_observations = std::max(maximum_observations, record.observation_count);
    ScoreEngine engine(maximum_observations, batch.records.size());
    if (leo_search_begin(search.get(), generation, &policy) != LEO_LOCATION_OK)
        throw std::runtime_error("search begin failed");
    SearchRun run;
    const auto started = std::chrono::steady_clock::now();
    for (;;) {
        leo_search_point points[128]{};
        std::uint32_t count = 0;
        const auto status = leo_search_next(search.get(), generation, points, 128, &count);
        if (status == LEO_LOCATION_DONE) break;
        if (status != LEO_LOCATION_OK) throw std::runtime_error("search next failed");
        std::vector<leo_search_evaluation> submitted(count);
        for (std::uint32_t index = 0; index < count; ++index) {
            const auto site = make_site(latitude, longitude, points[index].east_km, points[index].north_km);
            const double mse = score_site(&engine, orbit, batch, site, config);
            submitted[index] = {points[index].east_km, points[index].north_km, mse};
            run.evaluations.push_back({points[index].east_km, points[index].north_km,
                                       mse, site, key(site)});
            *raw << generation << '\t' << run.evaluations.size() - 1 << '\t'
                 << std::hex << bits(points[index].east_km) << '\t' << bits(points[index].north_km);
            for (const auto word : run.evaluations.back().site_key.words) *raw << '\t' << word;
            *raw << '\t' << bits(mse) << std::dec << '\t' << orbit.generation << '\t'
                 << bits(config.carrier_hz) << '\t' << bits(config.speed_of_light_km_s) << '\t'
                 << bits(config.unmatched_penalty_hz) << '\t' << config.tau_first_s << '\t'
                 << config.tau_last_s << '\t' << config.tau_step_s << '\n';
        }
        if (leo_search_submit(search.get(), generation, submitted.data(), count) != LEO_LOCATION_OK)
            throw std::runtime_error("search submit failed");
    }
    run.seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    if (leo_search_get_result(search.get(), generation, &run.result) != LEO_LOCATION_OK ||
        run.result.evaluated_points != 400 || run.evaluations.size() != 400 ||
        !run.result.has_incumbent)
        throw std::runtime_error("search result failed");
    return run;
}

std::size_t site_intersection(const SearchRun& left, const SearchRun& right) {
    std::vector<SiteKey> a, b;
    for (const auto& item : left.evaluations) a.push_back(item.site_key);
    for (const auto& item : right.evaluations) b.push_back(item.site_key);
    std::sort(a.begin(), a.end()); std::sort(b.begin(), b.end());
    std::vector<SiteKey> common;
    std::set_intersection(a.begin(), a.end(), b.begin(), b.end(), std::back_inserter(common));
    return common.size();
}
}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 5)
            throw std::runtime_error("usage: test CANDIDATES GRAPH TLES RAW_TSV");
        const Fixture fixture = load_fixture(argv[1], argv[2]);
        std::array<std::size_t, 3> candidate_counts{};
        std::array<Batch, 3> batches{
            make_prefix(fixture, 58, &candidate_counts[0]),
            make_prefix(fixture, 59, &candidate_counts[1]),
            make_prefix(fixture, 60, &candidate_counts[2])};
        if (candidate_counts != std::array<std::size_t, 3>{11'389, 11'566, 11'747})
            throw std::runtime_error("unexpected prefix counts");
        for (const auto& batch : batches)
            if (batch.records.size() != 64) throw std::runtime_error("unexpected track count");
        const auto catalogue = load_tles(argv[3]);
        Orbit orbit_context(leo_orbit_context_create(static_cast<std::uint32_t>(catalogue.size()), 96));
        if (!orbit_context) throw std::runtime_error("orbit allocation failed");
        leo_orbit_snapshot orbit{};
        if (leo_orbit_build_tle(orbit_context.get(), 7, fixture.graph.session_start_utc_ns,
                -10.0, 10.0, 96, catalogue.data(), static_cast<std::uint32_t>(catalogue.size()),
                &orbit) != LEO_LOCATION_OK)
            throw std::runtime_error("orbit build failed");
        std::ofstream raw(argv[4]);
        if (!raw) throw std::runtime_error("cannot create raw inventory");
        raw << "snapshot_generation\tevaluation\teast_bits\tnorth_bits\tecef_x_bits\t"
               "ecef_y_bits\tecef_z_bits\tup_x_bits\tup_y_bits\tup_z_bits\tmse_bits\t"
               "orbit_generation\tcarrier_bits\tspeed_bits\tpenalty_bits\ttau_first\t"
               "tau_last\ttau_step\n";
        std::array<SearchRun, 3> runs{
            run_search(58, orbit, batches[0], &raw),
            run_search(59, orbit, batches[1], &raw),
            run_search(60, orbit, batches[2], &raw)};
        raw.close();
        const std::size_t overlap58_59 = exact_track_overlap(batches[0], batches[1]);
        const std::size_t overlap59_60 = exact_track_overlap(batches[1], batches[2]);
        const std::size_t sites58_59 = site_intersection(runs[0], runs[1]);
        const std::size_t sites59_60 = site_intersection(runs[1], runs[2]);
        const std::size_t sites58_60 = site_intersection(runs[0], runs[2]);
        std::size_t authority_bytes = 0;
        for (const auto& item : batches[1].owned) authority_bytes += track_logical_bytes(item);
        const std::size_t score_entry_bytes = sizeof(leo_track_score) + sizeof(leo_score_stats) + 1;
        const std::size_t normalized_snapshot_cache_bytes = authority_bytes +
            runs[1].evaluations.size() * batches[1].records.size() * score_entry_bytes;
        std::cout << std::setprecision(17)
            << "{\"schema\":\"leo-ds9-exact-site-recurrence-research/v1\","
            << "\"policy\":{\"origin_latitude_deg\":38.5816,"
               "\"origin_longitude_deg\":-121.4944,\"radius_km\":250,"
               "\"region_size_km\":1000,\"levels_km\":[100,50,25,12.5],"
               "\"budget_points\":400,\"scoring_workers\":2},"
            << "\"catalogue_records\":" << catalogue.size()
            << ",\"orbit_generation\":" << orbit.generation
            << ",\"prefix_ordinals\":[58,59,60],\"candidate_counts\":["
            << candidate_counts[0] << ',' << candidate_counts[1] << ',' << candidate_counts[2]
            << "],\"track_counts\":[64,64,64],\"evaluated_points\":[400,400,400],"
            << "\"elapsed_seconds\":[" << runs[0].seconds << ',' << runs[1].seconds << ','
            << runs[2].seconds << "],\"incumbents\":[";
        for (std::size_t i = 0; i < runs.size(); ++i) {
            if (i) std::cout << ',';
            std::cout << "{\"east_km\":" << runs[i].result.incumbent.east_km
                << ",\"north_km\":" << runs[i].result.incumbent.north_km
                << ",\"rmse_hz\":" << std::sqrt(runs[i].result.incumbent.weighted_mse_hz2)
                << ",\"deferred_cells\":" << runs[i].result.deferred_cells << '}';
        }
        std::cout << "],\"adjacent\":[{\"from\":58,\"to\":59,\"site_intersection\":"
            << sites58_59 << ",\"exact_track_overlap\":" << overlap58_59
            << ",\"potential_exact_track_score_hits\":" << sites58_59 * overlap58_59
            << "},{\"from\":59,\"to\":60,\"site_intersection\":" << sites59_60
            << ",\"exact_track_overlap\":" << overlap59_60
            << ",\"potential_exact_track_score_hits\":" << sites59_60 * overlap59_60
            << "}],\"site_intersection_58_60\":" << sites58_60
            << ",\"middle_track_authority_logical_bytes\":" << authority_bytes
            << ",\"normalized_middle_snapshot_cache_logical_bytes\":"
            << normalized_snapshot_cache_bytes
            << ",\"score_entry_bytes\":" << score_entry_bytes
            << ",\"pinned_policy_relation\":\"each 400-point search completes on its immutable prefix before the newest adjacent publication starts\","
               "\"raw_inventory\":\"" << argv[4] << "\",\"production_changed\":false}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "site recurrence research: " << error.what() << '\n';
        return 1;
    }
}
