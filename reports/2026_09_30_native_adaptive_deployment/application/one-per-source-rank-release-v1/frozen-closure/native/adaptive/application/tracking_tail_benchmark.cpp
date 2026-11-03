#include "execution.hpp"
#include "../runtime/sha256.hpp"

#include <algorithm>
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
#include <stdexcept>
#include <string>
#include <sys/resource.h>
#include <time.h>
#include <tuple>
#include <utility>
#include <vector>

namespace {

using leo::adaptive::application::TrackingExecution;
using leo::adaptive::tracking::Candidate;
using leo::adaptive::tracking::Config;
using leo::adaptive::tracking::Result;
using leo::adaptive::tracking::ReconstructorStats;

constexpr const char* kFixtureSha256 =
    "9e39b38e67094d85f33262d00f65dab999097db088877604c3535d71b966071f";
constexpr std::size_t kFixtureCandidates = 11'747U;
constexpr std::size_t kExpectedPrefixes = 60U;
constexpr std::size_t kSeedPrefix = 58U;
constexpr std::size_t kWarmPrefix = 59U;

std::vector<std::string> split_tabs(const std::string& line) {
    std::vector<std::string> fields;
    std::size_t start = 0;
    while (true) {
        const std::size_t end = line.find('\t', start);
        fields.push_back(line.substr(start, end - start));
        if (end == std::string::npos) return fields;
        start = end + 1U;
    }
}

template <typename Integer>
Integer parse_integer(const std::string& text, const char* name) {
    errno = 0;
    char* end = nullptr;
    const long long parsed = std::strtoll(text.c_str(), &end, 10);
    if (errno || end != text.c_str() + text.size() ||
        parsed < static_cast<long long>(std::numeric_limits<Integer>::min()) ||
        parsed > static_cast<long long>(std::numeric_limits<Integer>::max())) {
        throw std::runtime_error(std::string("invalid ") + name);
    }
    return static_cast<Integer>(parsed);
}

std::size_t parse_size(const char* text, const char* name) {
    errno = 0;
    char* end = nullptr;
    const unsigned long long parsed = std::strtoull(text, &end, 10);
    if (errno || !text || !*text || *text == '-' || !end || *end || !parsed ||
        parsed > std::numeric_limits<std::size_t>::max()) {
        throw std::runtime_error(std::string("invalid ") + name);
    }
    return static_cast<std::size_t>(parsed);
}

double parse_double(const std::string& text, const char* name) {
    errno = 0;
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (errno || end != text.c_str() + text.size() || !std::isfinite(value)) {
        throw std::runtime_error(std::string("invalid ") + name);
    }
    return value;
}

Candidate parse_candidate(const std::vector<std::string>& fields) {
    if (fields.size() != 13U) {
        throw std::runtime_error("candidate row must have 13 fields");
    }
    return Candidate{
        fields[0], fields[1], parse_integer<int>(fields[2], "receiver"),
        parse_integer<int>(fields[3], "channel"), fields[4],
        parse_double(fields[5], "RF"),
        parse_integer<std::int64_t>(fields[6], "support start"),
        parse_integer<std::int64_t>(fields[7], "support center"),
        parse_integer<std::int64_t>(fields[8], "support end"),
        parse_double(fields[9], "CFO"), parse_double(fields[10], "exact"),
        parse_double(fields[11], "control"), parse_double(fields[12], "margin")};
}

std::string file_digest(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot open candidate input for hashing");
    const std::string bytes{std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>()};
    if (input.bad()) throw std::runtime_error("cannot read candidate input for hashing");
    return leo::adaptive::sha256(bytes);
}

std::vector<Candidate> load(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open candidate input");
    std::string line;
    if (!std::getline(input, line) || line !=
        "candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\t"
        "support_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\t"
        "measured_cfo_hz\texact_score\tcontrol_score\tmargin") {
        throw std::runtime_error("unsupported candidate header");
    }
    std::vector<Candidate> rows;
    rows.reserve(kFixtureCandidates);
    while (std::getline(input, line)) {
        if (!line.empty()) rows.push_back(parse_candidate(split_tabs(line)));
    }
    if (!input.eof()) throw std::runtime_error("cannot read candidate input");
    return rows;
}

bool same_double(double left, double right) {
    std::uint64_t a = 0, b = 0;
    std::memcpy(&a, &left, sizeof(left));
    std::memcpy(&b, &right, sizeof(right));
    return a == b;
}

bool same_result(const Result& left, const Result& right) {
    if (left.input_candidate_count != right.input_candidate_count ||
        left.used_candidate_count != right.used_candidate_count ||
        left.config_digest != right.config_digest ||
        left.tracks.size() != right.tracks.size()) return false;
    for (std::size_t index = 0; index < left.tracks.size(); ++index) {
        const auto& a = left.tracks[index];
        const auto& b = right.tracks[index];
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
        for (std::size_t point = 0; point < a.points.size(); ++point) {
            const auto& x = a.points[point];
            const auto& y = b.points[point];
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

void append_u64(std::string& output, std::uint64_t value) {
    for (unsigned shift = 0; shift < 64U; shift += 8U) {
        output.push_back(static_cast<char>((value >> shift) & 0xffU));
    }
}

void append_string(std::string& output, const std::string& value) {
    append_u64(output, value.size());
    output.append(value);
}

void append_double(std::string& output, double value) {
    std::uint64_t bits = 0;
    std::memcpy(&bits, &value, sizeof(bits));
    append_u64(output, bits);
}

std::string result_digest(const Result& result) {
    std::string material = "leo-tracking-result-bits/v1";
    append_u64(material, result.input_candidate_count);
    append_u64(material, result.used_candidate_count);
    append_string(material, result.config_digest);
    append_u64(material, result.tracks.size());
    for (const auto& track : result.tracks) {
        append_string(material, track.segment_id);
        append_string(material, track.tracklet_id);
        append_u64(material, static_cast<std::uint64_t>(track.lane.receiver_id));
        append_u64(material, static_cast<std::uint64_t>(track.lane.channel));
        append_string(material, track.lane.edge);
        append_double(material, track.lane.actual_rf_hz);
        append_u64(material, static_cast<std::uint64_t>(track.start_utc_ns));
        append_u64(material, static_cast<std::uint64_t>(track.end_utc_ns));
        append_u64(material, static_cast<std::uint64_t>(track.reference_utc_ns));
        append_double(material, track.normalized_rate_hz_per_s);
        append_double(material, track.normalized_intercept_hz);
        append_double(material, track.residual_rms_hz);
        append_double(material, track.residual_max_hz);
        append_double(material, track.weighted_support);
        append_u64(material, track.points.size());
        for (const auto& point : track.points) {
            append_string(material, point.candidate_id);
            append_string(material, point.source_group_id);
            append_u64(material, static_cast<std::uint64_t>(point.relative_alias_index));
            append_double(material, point.normalized_raw_cfo_hz);
            append_double(material, point.normalized_dealiased_cfo_hz);
        }
    }
    return leo::adaptive::sha256(material);
}

double wall_seconds(std::chrono::steady_clock::time_point start) {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
}

double process_cpu_seconds() {
    timespec value{};
    if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &value)) {
        throw std::runtime_error("cannot read process CPU clock");
    }
    return static_cast<double>(value.tv_sec) + static_cast<double>(value.tv_nsec) / 1e9;
}

struct TimedResult {
    Result result;
    double wall{};
};

template <typename Function>
TimedResult timed(Function&& function) {
    const auto start = std::chrono::steady_clock::now();
    Result result = function();
    return {std::move(result), wall_seconds(start)};
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3 || argc > 4) {
        std::cerr << "usage: " << argv[0]
                  << " CANDIDATES.tsv WORKERS [CACHE_BYTES]\n";
        return 2;
    }
    try {
        const std::size_t workers = parse_size(argv[2], "workers");
        const std::size_t cache_bytes = argc == 4 ?
            parse_size(argv[3], "cache bytes") : 96U * 1024U * 1024U;
        if (workers != 1U && workers != 2U) {
            throw std::runtime_error("workers must be one or two");
        }
        const std::string input_sha256 = file_digest(argv[1]);
        if (input_sha256 != kFixtureSha256) {
            throw std::runtime_error("candidate fixture digest differs");
        }
        auto rows = load(argv[1]);
        if (rows.size() != kFixtureCandidates) {
            throw std::runtime_error("candidate fixture cardinality differs");
        }
        std::sort(rows.begin(), rows.end(),
            [](const Candidate& left, const Candidate& right) {
                return std::tie(left.support_end_utc_ns, left.candidate_id) <
                    std::tie(right.support_end_utc_ns, right.candidate_id);
            });
        const std::int64_t first = rows.front().support_end_utc_ns;
        const std::int64_t last = rows.back().support_end_utc_ns;
        constexpr std::int64_t step = INT64_C(5'000'000'000);
        if (first <= 0 || last <= first) throw std::runtime_error("invalid support span");
        std::vector<std::int64_t> cutoffs;
        std::int64_t cutoff = first;
        while (cutoff < last) {
            cutoff = last - cutoff > step ? cutoff + step : last;
            cutoffs.push_back(cutoff);
        }
        if (cutoffs.size() != kExpectedPrefixes) {
            throw std::runtime_error("fixture does not have 60 causal prefixes");
        }
        const auto seed_end = std::upper_bound(rows.begin(), rows.end(), cutoffs[kSeedPrefix],
            [](std::int64_t value, const Candidate& candidate) {
                return value < candidate.support_end_utc_ns;
            });
        std::vector<Candidate> seed(rows.begin(), seed_end);
        std::vector<Candidate> final = std::move(rows);
        if (seed.empty() || seed.size() >= final.size()) {
            throw std::runtime_error("tail prefixes do not form a strict extension");
        }

        const auto benchmark_start = std::chrono::steady_clock::now();
        const double cpu_start = process_cpu_seconds();
        TrackingExecution execution(static_cast<std::uint32_t>(workers));
        const auto port = execution.port();
        const Config config{};
        leo::adaptive::tracking::Reconstructor stateful(cache_bytes);

        std::string seed_digest;
        double seed_cold_wall = 0.0, seed_stateful_wall = 0.0;
        ReconstructorStats seed_stats{};
        {
            auto cold = timed([&] {
                return leo::adaptive::tracking::reconstruct(seed, config, port);
            });
            auto cached = timed([&] { return stateful.reconstruct(seed, config, port); });
            if (!same_result(cold.result, cached.result)) {
                throw std::runtime_error("seed stateful result differs from cold oracle");
            }
            seed_digest = result_digest(cold.result);
            seed_cold_wall = cold.wall;
            seed_stateful_wall = cached.wall;
            seed_stats = stateful.stats();
        }

        std::string final_digest;
        std::size_t final_tracks = 0;
        double final_cold_wall = 0.0, final_warm_wall = 0.0;
        ReconstructorStats warm_stats{};
        {
            auto cold = timed([&] {
                return leo::adaptive::tracking::reconstruct(final, config, port);
            });
            auto cached = timed([&] { return stateful.reconstruct(final, config, port); });
            if (!same_result(cold.result, cached.result)) {
                throw std::runtime_error("warm stateful result differs from cold oracle");
            }
            final_digest = result_digest(cold.result);
            final_tracks = cold.result.tracks.size();
            final_cold_wall = cold.wall;
            final_warm_wall = cached.wall;
            warm_stats = stateful.stats();
        }
        if (!seed_stats.last_cold_fallback || warm_stats.last_cold_fallback ||
            warm_stats.prefix_invalidations || warm_stats.config_invalidations ||
            warm_stats.capacity_fallbacks ||
            warm_stats.last_reused_lanes + warm_stats.last_extended_lanes !=
                warm_stats.cached_lanes ||
            warm_stats.resident_cache_bytes > cache_bytes || final_tracks != 64U) {
            throw std::runtime_error("unexpected exact-prefix cache accounting");
        }
        const double process_cpu = process_cpu_seconds() - cpu_start;
        const double benchmark_wall = wall_seconds(benchmark_start);
        rusage usage{};
        if (getrusage(RUSAGE_SELF, &usage)) throw std::runtime_error("cannot read RSS");

        std::cout << std::setprecision(17)
                  << "{\n"
                  << "  \"schema\": \"leo-application-tracking-tail-prefix/v1\",\n"
                  << "  \"input_sha256\": \"" << input_sha256 << "\",\n"
                  << "  \"input_candidates\": " << final.size() << ",\n"
                  << "  \"cutoff_authority\": \"support-end-utc\",\n"
                  << "  \"candidate_order\": \"support-end-utc,candidate-id\",\n"
                  << "  \"interval_seconds\": 5,\n"
                  << "  \"available_prefixes\": " << cutoffs.size() << ",\n"
                  << "  \"seed_prefix_index_zero_based\": " << kSeedPrefix << ",\n"
                  << "  \"warm_prefix_index_zero_based\": " << kWarmPrefix << ",\n"
                  << "  \"seed_cutoff_utc_ns\": " << cutoffs[kSeedPrefix] << ",\n"
                  << "  \"warm_cutoff_utc_ns\": " << cutoffs[kWarmPrefix] << ",\n"
                  << "  \"seed_candidates\": " << seed.size() << ",\n"
                  << "  \"final_candidates\": " << final.size() << ",\n"
                  << "  \"execution_adapter\": \"application::TrackingExecution\",\n"
                  << "  \"analysis_workers\": " << workers << ",\n"
                  << "  \"bit_exact_prefixes\": 2,\n"
                  << "  \"seed_result_sha256\": \"" << seed_digest << "\",\n"
                  << "  \"final_result_sha256\": \"" << final_digest << "\",\n"
                  << "  \"final_tracks\": " << final_tracks << ",\n"
                  << "  \"seed_cold_wall_seconds\": " << seed_cold_wall << ",\n"
                  << "  \"seed_stateful_wall_seconds\": " << seed_stateful_wall << ",\n"
                  << "  \"final_cold_wall_seconds\": " << final_cold_wall << ",\n"
                  << "  \"final_warm_wall_seconds\": " << final_warm_wall << ",\n"
                  << "  \"benchmark_wall_seconds\": " << benchmark_wall << ",\n"
                  << "  \"process_cpu_seconds\": " << process_cpu << ",\n"
                  << "  \"maximum_rss_kib\": " << usage.ru_maxrss << ",\n"
                  << "  \"cache_budget_bytes\": " << cache_bytes << ",\n"
                  << "  \"seed_resident_cache_bytes\": "
                  << seed_stats.resident_cache_bytes << ",\n"
                  << "  \"warm_resident_cache_bytes\": "
                  << warm_stats.resident_cache_bytes << ",\n"
                  << "  \"warm_cached_lanes\": " << warm_stats.cached_lanes << ",\n"
                  << "  \"warm_reused_lanes\": " << warm_stats.last_reused_lanes << ",\n"
                  << "  \"warm_extended_lanes\": " << warm_stats.last_extended_lanes << ",\n"
                  << "  \"warm_bin_cells_computed\": "
                  << warm_stats.last_bin_cells_computed << ",\n"
                  << "  \"cold_starts\": " << warm_stats.cold_starts << ",\n"
                  << "  \"prefix_invalidations\": "
                  << warm_stats.prefix_invalidations << ",\n"
                  << "  \"config_invalidations\": "
                  << warm_stats.config_invalidations << ",\n"
                  << "  \"capacity_fallbacks\": "
                  << warm_stats.capacity_fallbacks << "\n"
                  << "}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "application-tracking-tail-benchmark: " << error.what() << '\n';
        return 1;
    }
}
