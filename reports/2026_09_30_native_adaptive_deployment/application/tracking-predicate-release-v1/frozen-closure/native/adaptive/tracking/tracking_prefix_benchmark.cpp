#include "tracking.hpp"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace {

using leo::adaptive::tracking::Candidate;
using leo::adaptive::tracking::Result;

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
        parsed > static_cast<long long>(std::numeric_limits<Integer>::max()))
        throw std::runtime_error(std::string("invalid ") + name);
    return static_cast<Integer>(parsed);
}

std::size_t parse_size(const char* text, const char* name) {
    errno = 0;
    char* end = nullptr;
    const unsigned long long parsed = std::strtoull(text, &end, 10);
    if (errno || !*text || *end || parsed > std::numeric_limits<std::size_t>::max())
        throw std::runtime_error(std::string("invalid ") + name);
    return static_cast<std::size_t>(parsed);
}

double parse_double(const std::string& text, const char* name) {
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (end != text.c_str() + text.size())
        throw std::runtime_error(std::string("invalid ") + name);
    return value;
}

Candidate parse_candidate(const std::vector<std::string>& fields) {
    if (fields.size() != 13U)
        throw std::runtime_error("candidate row must have 13 fields");
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

std::vector<Candidate> load(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open candidate input");
    std::string line;
    if (!std::getline(input, line) || line !=
        "candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\t"
        "support_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\t"
        "measured_cfo_hz\texact_score\tcontrol_score\tmargin")
        throw std::runtime_error("unsupported candidate header");
    std::vector<Candidate> rows;
    while (std::getline(input, line))
        if (!line.empty()) rows.push_back(parse_candidate(split_tabs(line)));
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
    for (std::size_t i = 0; i < left.tracks.size(); ++i) {
        const auto& a = left.tracks[i];
        const auto& b = right.tracks[i];
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
        for (std::size_t j = 0; j < a.points.size(); ++j) {
            const auto& x = a.points[j];
            const auto& y = b.points[j];
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

double elapsed(std::chrono::steady_clock::time_point start) {
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2 || argc > 5) {
        std::cerr << "usage: " << argv[0]
                  << " CANDIDATES.tsv [INTERVAL_SECONDS] [CACHE_BYTES] [--tail-two]\n";
        return 2;
    }
    try {
        const std::size_t interval_seconds = argc >= 3 ?
            parse_size(argv[2], "interval") : 5U;
        const std::size_t cache_bytes = argc >= 4 ?
            parse_size(argv[3], "cache bytes") : 96U * 1024U * 1024U;
        const bool tail_two = argc == 5 && std::strcmp(argv[4], "--tail-two") == 0;
        if (argc == 5 && !tail_two)
            throw std::runtime_error("fourth option must be --tail-two");
        if (!interval_seconds || interval_seconds >
            static_cast<std::size_t>(INT64_MAX / INT64_C(1000000000)))
            throw std::runtime_error("interval is out of range");
        auto rows = load(argv[1]);
        if (rows.empty()) throw std::runtime_error("candidate input is empty");
        std::sort(rows.begin(), rows.end(),
            [](const Candidate& left, const Candidate& right) {
                return std::tie(left.support_end_utc_ns,left.candidate_id) <
                    std::tie(right.support_end_utc_ns,right.candidate_id);
            });
        const std::int64_t first = rows.front().support_end_utc_ns;
        const std::int64_t last = rows.back().support_end_utc_ns;
        if (first<=0) throw std::runtime_error("invalid support end");
        const std::int64_t step = static_cast<std::int64_t>(interval_seconds) *
            INT64_C(1000000000);
        leo::adaptive::tracking::Reconstructor stateful(cache_bytes);
        std::size_t prefixes = 0, equal_prefixes = 0, cold_calls = 0;
        std::size_t maximum_resident = 0;
        double cold_seconds = 0.0, stateful_seconds = 0.0;
        double maximum_cold_seconds = 0.0, maximum_stateful_seconds = 0.0;
        double tail_seed_cold_seconds = 0.0, tail_seed_seconds = 0.0;
        double tail_final_cold_seconds = 0.0, tail_final_warm_seconds = 0.0;
        std::size_t final_candidates = 0, final_tracks = 0;
        std::int64_t cutoff = first;
        std::vector<std::int64_t> cutoffs;
        while (cutoff < last) {
            cutoff = last - cutoff > step ? cutoff + step : last;
            cutoffs.push_back(cutoff);
        }
        if (tail_two && cutoffs.size() < 2U)
            throw std::runtime_error("tail-two mode requires at least two prefixes");
        const std::size_t begin_prefix = tail_two ? cutoffs.size() - 2U : 0U;
        for (std::size_t cutoff_index = begin_prefix;
             cutoff_index < cutoffs.size(); ++cutoff_index) {
            cutoff = cutoffs[cutoff_index];
            std::vector<Candidate> prefix;
            prefix.reserve(rows.size());
            for (const Candidate& row : rows)
                if (row.support_end_utc_ns <= cutoff) prefix.push_back(row);
            const auto cold_start = std::chrono::steady_clock::now();
            const Result cold = leo::adaptive::tracking::reconstruct(prefix);
            const double cold_elapsed = elapsed(cold_start);
            const auto stateful_start = std::chrono::steady_clock::now();
            const Result cached = stateful.reconstruct(prefix);
            const double stateful_elapsed = elapsed(stateful_start);
            ++prefixes;
            if (same_result(cold, cached)) ++equal_prefixes;
            else throw std::runtime_error("stateful result differs at prefix " +
                std::to_string(prefixes));
            const auto stats = stateful.stats();
            if (stats.last_cold_fallback) ++cold_calls;
            maximum_resident = std::max(maximum_resident,
                stats.resident_cache_bytes);
            cold_seconds += cold_elapsed;
            stateful_seconds += stateful_elapsed;
            maximum_cold_seconds = std::max(maximum_cold_seconds, cold_elapsed);
            maximum_stateful_seconds = std::max(maximum_stateful_seconds,
                stateful_elapsed);
            if (tail_two && cutoff_index == begin_prefix) {
                tail_seed_cold_seconds = cold_elapsed;
                tail_seed_seconds = stateful_elapsed;
            } else if (tail_two) {
                tail_final_cold_seconds = cold_elapsed;
                tail_final_warm_seconds = stateful_elapsed;
            }
            final_candidates = prefix.size();
            final_tracks = cached.tracks.size();
        }
        const auto stats = stateful.stats();
        std::cout << std::setprecision(17)
                  << "{\n"
                  << "  \"schema\": \"leo-tracking-prefix-benchmark-v2\",\n"
                  << "  \"cutoff_authority\": \"support-end-utc\",\n"
                  << "  \"candidate_order\": \"support-end-utc,candidate-id\",\n"
                  << "  \"available_prefixes\": " << cutoffs.size() << ",\n"
                  << "  \"first_prefix_index\": " << begin_prefix << ",\n"
                  << "  \"tail_two\": " << (tail_two ? "true":"false") << ",\n"
                  << "  \"tail_seed_cold_seconds\": " << tail_seed_cold_seconds << ",\n"
                  << "  \"tail_seed_stateful_seconds\": " << tail_seed_seconds << ",\n"
                  << "  \"tail_final_cold_seconds\": " << tail_final_cold_seconds << ",\n"
                  << "  \"tail_final_warm_seconds\": " << tail_final_warm_seconds << ",\n"
                  << "  \"input_candidates\": " << rows.size() << ",\n"
                  << "  \"duration_seconds\": "
                  << static_cast<double>(last - first) / 1e9 << ",\n"
                  << "  \"interval_seconds\": " << interval_seconds << ",\n"
                  << "  \"prefixes\": " << prefixes << ",\n"
                  << "  \"bit_exact_prefixes\": " << equal_prefixes << ",\n"
                  << "  \"stateful_cold_calls\": " << cold_calls << ",\n"
                  << "  \"cold_total_seconds\": " << cold_seconds << ",\n"
                  << "  \"stateful_total_seconds\": " << stateful_seconds << ",\n"
                  << "  \"cold_maximum_seconds\": " << maximum_cold_seconds << ",\n"
                  << "  \"stateful_maximum_seconds\": " << maximum_stateful_seconds << ",\n"
                  << "  \"maximum_resident_cache_bytes\": " << maximum_resident << ",\n"
                  << "  \"cache_budget_bytes\": " << cache_bytes << ",\n"
                  << "  \"prefix_invalidations\": " << stats.prefix_invalidations << ",\n"
                  << "  \"config_invalidations\": " << stats.config_invalidations << ",\n"
                  << "  \"capacity_fallbacks\": " << stats.capacity_fallbacks << ",\n"
                  << "  \"final_candidates\": " << final_candidates << ",\n"
                  << "  \"final_tracks\": " << final_tracks << "\n"
                  << "}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "tracking-prefix-benchmark: " << error.what() << '\n';
        return 1;
    }
}
