#include "recorded_main.hpp"

#include "corrected_geometry.hpp"
#include "live.hpp"
#include "recorded_bundle.hpp"
#include "../detector/corrected_profile_adapter.h"
#include "../device/recorded/recorded_source.h"
#include "../location/tle_id.hpp"
#include "../runtime/server_compat/server_compat.hpp"
#include "../runtime/sha256.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <unordered_set>
#include <utility>
#include <vector>

namespace leo::adaptive::application::recorded {
namespace {

constexpr std::size_t template_complex_count = 10000U;
constexpr std::uint32_t maximum_recorded_visits = 32U;
constexpr std::uint32_t historical_transition_flags =
    LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
    LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
    LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;

struct Parsed {
    std::string bundle, bundle_sha, analysis_digest, exact, control, tles, output;
    double latitude{}, longitude{}, radius_km{}, region_km{}, level_km{};
    std::uint32_t search_budget{}, search_slice{}, wall_seconds{};
    std::uint32_t detector_workers{1U}, analysis_workers{1U};
    bool origin{};
};

bool unsigned_number(const char* text, std::uint64_t maximum, std::uint64_t& value) {
    if (!text || !*text || *text == '-' || (*text == '0' && text[1])) return false;
    errno = 0;
    char* end = nullptr;
    const auto parsed = std::strtoull(text, &end, 10);
    if (errno || !end || *end || !parsed || parsed > maximum) return false;
    value = parsed;
    return true;
}

bool finite_number(const char* text, double& value) {
    if (!text || !*text || *text == '+') return false;
    errno = 0;
    char* end = nullptr;
    value = std::strtod(text, &end);
    return !errno && end && !*end && std::isfinite(value);
}

bool tagged_digest(const std::string& text) {
    return text.size() == 71U && text.compare(0, 7, "sha256:") == 0 &&
        text.find_first_not_of("0123456789abcdef", 7) == std::string::npos;
}

bool bare_digest(const std::string& text) {
    return text.size() == 64U &&
        text.find_first_not_of("0123456789abcdef") == std::string::npos;
}

bool parse(int argc, char** argv, Parsed& value) {
    for (int i = 1; i < argc;) {
        const std::string key = argv[i++];
        auto next = [&]() -> const char* { return i < argc ? argv[i++] : nullptr; };
        std::uint64_t number = 0;
        if (key == "--bundle-native") {
            const char* v = next(); if (!v || !value.bundle.empty()) return false; value.bundle = v;
        } else if (key == "--bundle-sha256") {
            const char* v = next(); if (!v || !value.bundle_sha.empty()) return false; value.bundle_sha = v;
        } else if (key == "--analysis-digest") {
            const char* v = next(); if (!v || !value.analysis_digest.empty()) return false; value.analysis_digest = v;
        } else if (key == "--exact-template") {
            const char* v = next(); if (!v || !value.exact.empty()) return false; value.exact = v;
        } else if (key == "--control-template") {
            const char* v = next(); if (!v || !value.control.empty()) return false; value.control = v;
        } else if (key == "--tle-catalogue") {
            const char* v = next(); if (!v || !value.tles.empty()) return false; value.tles = v;
        } else if (key == "--output") {
            const char* v = next(); if (!v || !value.output.empty()) return false; value.output = v;
        } else if (key == "--search-origin") {
            if (value.origin || i + 1 >= argc || !finite_number(argv[i++], value.latitude) ||
                !finite_number(argv[i++], value.longitude)) return false;
            value.origin = true;
        } else if (key == "--search-radius-km") {
            if (value.radius_km || !finite_number(next(), value.radius_km)) return false;
        } else if (key == "--search-region-km") {
            if (value.region_km || !finite_number(next(), value.region_km)) return false;
        } else if (key == "--search-level-km") {
            if (value.level_km || !finite_number(next(), value.level_km)) return false;
        } else if (key == "--search-point-budget") {
            if (value.search_budget || !unsigned_number(next(), 100000U, number)) return false;
            value.search_budget = static_cast<std::uint32_t>(number);
        } else if (key == "--search-slice-points") {
            if (value.search_slice || !unsigned_number(next(), 100000U, number)) return false;
            value.search_slice = static_cast<std::uint32_t>(number);
        } else if (key == "--wall-seconds") {
            if (value.wall_seconds || !unsigned_number(next(), 3600U, number)) return false;
            value.wall_seconds = static_cast<std::uint32_t>(number);
        } else if (key == "--detector-workers") {
            if (!unsigned_number(next(), 4U, number)) return false;
            value.detector_workers = static_cast<std::uint32_t>(number);
        } else if (key == "--analysis-workers") {
            if (!unsigned_number(next(), 4U, number)) return false;
            value.analysis_workers = static_cast<std::uint32_t>(number);
        } else return false;
    }
    const double cells = value.region_km / value.level_km;
    return !value.bundle.empty() && bare_digest(value.bundle_sha) &&
        tagged_digest(value.analysis_digest) && !value.exact.empty() &&
        !value.control.empty() && !value.tles.empty() && !value.output.empty() &&
        value.output.front() == '/' && value.origin && value.latitude >= -90 &&
        value.latitude <= 90 && value.longitude >= -180 && value.longitude <= 180 &&
        value.radius_km > 0 && value.radius_km <= 500 && value.region_km > 0 &&
        value.region_km <= 1000 && value.radius_km <= value.region_km / 2 &&
        value.level_km > 0 && cells >= 1 && cells <= 100 &&
        std::abs(cells - std::round(cells)) <= 1e-12 && value.search_budget &&
        value.search_slice && value.search_slice <= value.search_budget && value.wall_seconds &&
        value.detector_workers == 1U && value.analysis_workers >= 1U &&
        value.analysis_workers <= 4U;
}

template<class T> std::vector<T> read_exact(const std::string& path, std::size_t count) {
    std::vector<T> values(count);
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot open bounded binary input");
    input.read(reinterpret_cast<char*>(values.data()),
        static_cast<std::streamsize>(values.size() * sizeof(T)));
    if (!input || input.peek() != std::ifstream::traits_type::eof())
        throw std::runtime_error("bounded binary input has wrong size");
    return values;
}

std::vector<leo_tle_record> read_tles(const std::string& path) {
    std::ifstream input(path);
    std::size_t count = 0;
    if (!(input >> count) || !count || count > 20000U)
        throw std::runtime_error("bad TLE catalogue count");
    input.ignore(1024, '\n');
    std::vector<leo_tle_record> result(count);
    std::unordered_set<std::int32_t> ids;
    for (std::size_t i = 0; i < count; ++i) {
        std::string one, two;
        std::getline(input, one); std::getline(input, two);
        std::int32_t first = 0, second = 0;
        if (one.size() != 69U || two.size() != 69U || one[0] != '1' || two[0] != '2' ||
            !location::parse_tle_catalogue_id(std::string_view(one).substr(2, 5), first) ||
            !location::parse_tle_catalogue_id(std::string_view(two).substr(2, 5), second) ||
            first != second || !ids.insert(first).second)
            throw std::runtime_error("bad TLE catalogue record");
        result[i].satellite_id = first;
        std::memcpy(result[i].line1, one.data(), 69U);
        std::memcpy(result[i].line2, two.data(), 69U);
        result[i].line1[69] = result[i].line2[69] = '\0';
    }
    std::string extra;
    while (std::getline(input, extra)) if (!extra.empty())
        throw std::runtime_error("trailing TLE catalogue data");
    return result;
}

std::uint64_t monotonic_ns() {
    timespec value{};
    if (clock_gettime(CLOCK_MONOTONIC, &value))
        throw std::runtime_error("CLOCK_MONOTONIC unavailable");
    return static_cast<std::uint64_t>(value.tv_sec) * 1000000000ULL + value.tv_nsec;
}

int nibble(char c) { return c <= '9' ? c - '0' : c - 'a' + 10; }

std::array<std::uint8_t, 32> bytes_of_digest(const std::string& digest) {
    const std::string_view hex = digest.size() == 71U ?
        std::string_view(digest).substr(7) : std::string_view(digest);
    if (hex.size() != 64U || hex.find_first_not_of("0123456789abcdef") !=
            std::string_view::npos)
        throw std::runtime_error("invalid digest encoding");
    std::array<std::uint8_t, 32> result{};
    for (std::size_t i = 0; i < result.size(); ++i)
        result[i] = static_cast<std::uint8_t>((nibble(hex[2 * i]) << 4) |
            nibble(hex[2 * i + 1]));
    return result;
}

void append_u32(std::string& out, std::uint32_t value) {
    for (unsigned shift = 0; shift < 32U; shift += 8U)
        out.push_back(static_cast<char>((value >> shift) & 0xffU));
}

std::array<std::uint8_t, 32> detector_digest(const Parsed& parsed,
        const RecordedBundle& bundle, const std::vector<leo_native_glrt_complex>& exact,
        const std::vector<leo_native_glrt_complex>& control) {
    std::string material("leo-recorded-corrected-detector-binding/v1");
    material.push_back('\0'); material.append(parsed.analysis_digest); material.push_back('\0');
    material.append(reinterpret_cast<const char*>(bundle.calibration_manifest_digest.data()), 32U);
    append_u32(material, bundle.sample_rate_hz);
    material.append(reinterpret_cast<const char*>(exact.data()), exact.size() * sizeof(exact[0]));
    material.append(reinterpret_cast<const char*>(control.data()), control.size() * sizeof(control[0]));
    return bytes_of_digest(sha256(material));
}

struct AdapterDeleter {
    void operator()(leo_corrected_profile_adapter* value) const noexcept {
        if (value) (void)leo_corrected_profile_adapter_destroy(value);
    }
};
struct SourceDeleter {
    void operator()(leo_recorded_source* value) const noexcept {
        if (value) (void)leo_recorded_source_destroy(value);
    }
};
using AdapterOwner = std::unique_ptr<leo_corrected_profile_adapter, AdapterDeleter>;
using SourceOwner = std::unique_ptr<leo_recorded_source, SourceDeleter>;

struct CapturedEvent {
    leo_scanner_source_event source{};
};

struct Sink {
    live::Analysis* analysis{};
    leo_source_port* source{};
    std::vector<CapturedEvent> events;
    std::exception_ptr failure;
};

void event_sink(void* opaque, const leo_scanner_source_event* event) noexcept {
    auto& sink = *static_cast<Sink*>(opaque);
    if (sink.failure || !event) return;
    try {
        if (event->abi_version != LEO_SCANNER_SOURCE_ABI_VERSION ||
            event->counter_authority != LEO_SOURCE_COUNTER_PROVIDER_EXACT ||
            event->position_semantics != LEO_SOURCE_POSITION_COHERENT_CURRENT ||
            event->time_authority != LEO_SOURCE_TIME_NONE ||
            event->transition_flags != historical_transition_flags ||
            !event->physical_counter_qualified ||
            (event->block_flags & (LEO_SOURCE_BLOCK_OVERFLOW_BEFORE |
                                   LEO_SOURCE_BLOCK_DISCONTINUITY)))
            throw std::runtime_error("recorded source-event authority mismatch");
        sink.events.push_back({*event});
        sink.analysis->event(event->event);
    } catch (...) {
        sink.failure = std::current_exception();
        if (sink.source) (void)leo_source_port_cancel(sink.source);
    }
}

int cancel_source(void* opaque) {
    return leo_source_port_cancel(static_cast<leo_source_port*>(opaque));
}

std::string parent_path(const std::string& path) {
    const auto slash = path.rfind('/');
    return slash == 0 ? "/" : path.substr(0, slash);
}

std::string base_name(const std::string& path) {
    return path.substr(path.rfind('/') + 1U);
}

std::string canonical_directory(const std::string& path) {
    std::unique_ptr<char, decltype(&std::free)> resolved(realpath(path.c_str(), nullptr), &std::free);
    if (!resolved) throw std::runtime_error("output parent is not a canonical directory");
    struct stat metadata{};
    if (stat(resolved.get(), &metadata) || !S_ISDIR(metadata.st_mode))
        throw std::runtime_error("output parent is not a directory");
    return resolved.get();
}

bool beneath_qnap(const std::string& path) {
    return path == "/mnt/qnap01" ||
        (path.size() > 11U && path.compare(0, 11, "/mnt/qnap01") == 0 && path[11] == '/');
}

void require_new_safe_output(const std::string& output) {
    struct stat ignored{};
    if (!lstat(output.c_str(), &ignored) || errno != ENOENT)
        throw std::runtime_error("output destination already exists or cannot be inspected");
    const auto parent = canonical_directory(parent_path(output));
    if (beneath_qnap(parent)) throw std::runtime_error("QNAP output is forbidden");
}

struct AtomicDirectory {
    explicit AtomicDirectory(std::string destination)
        : final(std::move(destination)), staging(parent_path(final) + "/." +
              base_name(final) + ".tmp." + std::to_string(getpid())) {
        struct stat ignored{};
        if (!lstat(staging.c_str(), &ignored) || errno != ENOENT ||
            mkdir(staging.c_str(), 0700))
            throw std::runtime_error("cannot create output staging directory");
    }
    ~AtomicDirectory() {
        if (committed) return;
        for (const char* name : {"events.tsv", "tracks.tsv", "summary.json"})
            (void)unlink((staging + "/" + name).c_str());
        (void)rmdir(staging.c_str());
    }
    void commit() {
        if (rename(staging.c_str(), final.c_str()))
            throw std::runtime_error("cannot publish output directory");
        committed = true;
    }
    std::string final, staging;
    bool committed{};
};

void write_events(const std::string& path, const std::vector<CapturedEvent>& events) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create events output");
    out << "kind\tvisit\tvalid_start\tvalid_end\tselection_counter\ttransition_counter_before\t"
        "transition_counter_after\ttarget\tprofile\tattested_profile_crc32\tfrequency_hz\t"
        "feedback_outcome\tenergy_sum\tenergy_sample_count\tpower_dbfs\twindows_emitted\t"
        "row_index\tcandidate_index\treceiver_id\tprobe_index\tdetector_status\t"
        "fractional_epoch_server_parity_qualified\tdetector_enqueued_monotonic_ns\t"
        "detector_started_monotonic_ns\tdetector_finished_monotonic_ns\tdetector_queue_ns\t"
        "detector_runtime_ns\tdetector_row_count\tcounter_authority\tposition_semantics\t"
        "time_authority\ttransition_flags\tblock_flags\tphysical_counter_qualified\t"
        "coarse_epoch\tcoarse_bin\trefined_epoch\tframe_support\tglrt_complete\t"
        "conditioned_fallback\trefinement_skipped\tcoarse_cfo_hz\tfine_cfo_hz\t"
        "conditioned_cfo_hz\tepoch\tacquired_cfo_hz\ttracking_cfo_hz\texact_score\t"
        "control_score\tmargin\tacquire_score\tverify_score\tverify_control_score\t"
        "conditioned_score\tcoarse_score\tfractional_epoch_status\t"
        "fractional_epoch_offset_samples\tfractional_epoch_log_curvature\t"
        "fractional_epoch_exact_grid_0\tfractional_epoch_exact_grid_1\t"
        "fractional_epoch_exact_grid_2\tfractional_epoch_exact_grid_3\t"
        "fractional_epoch_exact_grid_4\tfractional_epoch_control_grid_0\t"
        "fractional_epoch_control_grid_1\tfractional_epoch_control_grid_2\t"
        "fractional_epoch_control_grid_3\tfractional_epoch_control_grid_4\t"
        "fractional_exact_score\tfractional_control_score\tfractional_margin\t"
        "fractional_residual_cfo_hz\tfractional_tracking_cfo_hz\n";
    out << std::setprecision(std::numeric_limits<double>::max_digits10);
    for (const auto& captured : events) {
        const auto& s = captured.source; const auto& e = s.event; const auto& c = e.candidate;
        out << e.kind << '\t' << e.visit << '\t' << e.valid_start << '\t' << e.valid_end << '\t'
            << e.selection_counter << '\t' << e.transition_counter_before << '\t'
            << e.transition_counter_after << '\t' << e.target << '\t' << e.profile << '\t'
            << e.attested_profile_crc32 << '\t' << e.frequency_hz << '\t' << e.feedback_outcome
            << '\t' << e.energy_sum << '\t' << e.energy_sample_count << '\t' << e.power_dbfs
            << '\t' << e.windows_emitted << '\t' << e.row_index << '\t' << e.candidate_index
            << '\t' << e.receiver_id << '\t' << e.probe_index << '\t' << e.detector_status
            << '\t' << e.fractional_epoch_server_parity_qualified << '\t'
            << e.detector_enqueued_monotonic_ns << '\t' << e.detector_started_monotonic_ns
            << '\t' << e.detector_finished_monotonic_ns << '\t' << e.detector_queue_ns << '\t'
            << e.detector_runtime_ns << '\t' << e.detector_row_count << '\t'
            << s.counter_authority << '\t' << s.position_semantics << '\t' << s.time_authority
            << '\t' << s.transition_flags << '\t' << s.block_flags << '\t'
            << s.physical_counter_qualified << '\t' << c.coarse_epoch << '\t' << c.coarse_bin
            << '\t' << c.refined_epoch << '\t' << c.frame_support << '\t' << c.glrt_complete
            << '\t' << c.conditioned_fallback << '\t' << c.refinement_skipped << '\t'
            << c.coarse_cfo_hz << '\t' << c.fine_cfo_hz << '\t' << c.conditioned_cfo_hz
            << '\t' << c.epoch << '\t' << c.acquired_cfo_hz << '\t' << c.tracking_cfo_hz
            << '\t' << c.exact_score << '\t' << c.control_score << '\t' << c.margin << '\t'
            << c.acquire_score << '\t' << c.verify_score << '\t' << c.verify_control_score
            << '\t' << c.conditioned_score << '\t' << c.coarse_score << '\t'
            << c.fractional_epoch_status << '\t' << c.fractional_epoch_offset_samples << '\t'
            << c.fractional_epoch_log_curvature;
        for (double value : c.fractional_epoch_exact_grid) out << '\t' << value;
        for (double value : c.fractional_epoch_control_grid) out << '\t' << value;
        out << '\t' << c.fractional_exact_score << '\t' << c.fractional_control_score << '\t'
            << c.fractional_margin << '\t' << c.fractional_residual_cfo_hz << '\t'
            << c.fractional_tracking_cfo_hz << '\n';
    }
    if (!out) throw std::runtime_error("cannot write events output");
}

void write_tracks(const std::string& path, const online::Snapshot* snapshot) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create tracks output");
    out << "kind\ttrack_index\ttracklet_id\tsegment_id\tsupport_digest\tpartition_seed\t"
        "channel\tedge\treceiver_id\tstart_utc_ns\tend_utc_ns\treference_utc_ns\t"
        "normalized_rate_hz_per_s\tnormalized_intercept_hz\tresidual_rms_hz\t"
        "residual_max_hz\tweighted_support\tpoint_index\tcandidate_id\tsource_group_id\t"
        "relative_alias_index\tnormalized_raw_cfo_hz\tnormalized_dealiased_cfo_hz\t"
        "observation_id\ttraining\ttime_s\tmeasured_hz\n";
    out << std::setprecision(std::numeric_limits<double>::max_digits10);
    if (!snapshot) return;
    if (snapshot->tracking_result.tracks.size() != snapshot->location_tracks.owned.size())
        throw std::runtime_error("snapshot track ownership mismatch");
    for (std::size_t i = 0; i < snapshot->tracking_result.tracks.size(); ++i) {
        const auto& track = snapshot->tracking_result.tracks[i];
        const auto& location = snapshot->location_tracks.owned[i];
        if (track.tracklet_id != location.tracklet_id ||
            track.points.size() != location.observation_ids.size() ||
            track.points.size() != location.training_mask.size() ||
            track.points.size() != location.times_s.size() ||
            track.points.size() != location.measured_hz.size())
            throw std::runtime_error("snapshot point ownership mismatch");
        out << "TRACK\t" << i << '\t' << track.tracklet_id << '\t' << track.segment_id << '\t'
            << location.support_digest << '\t' << location.partition_seed << '\t'
            << track.lane.channel << '\t' << track.lane.edge << '\t' << track.lane.receiver_id
            << '\t' << track.start_utc_ns << '\t' << track.end_utc_ns << '\t'
            << track.reference_utc_ns << '\t' << track.normalized_rate_hz_per_s << '\t'
            << track.normalized_intercept_hz << '\t' << track.residual_rms_hz << '\t'
            << track.residual_max_hz << '\t' << track.weighted_support
            << "\t0\t\t\t0\t0\t0\t\t0\t0\t0\n";
        for (std::size_t point = 0; point < track.points.size(); ++point) {
            const auto& p = track.points[point];
            out << "POINT\t" << i << '\t' << track.tracklet_id << "\t\t"
                << location.support_digest << '\t' << location.partition_seed
                << "\t0\t\t0\t0\t0\t0\t0\t0\t0\t0\t0\t" << point << '\t'
                << p.candidate_id << '\t' << p.source_group_id << '\t'
                << p.relative_alias_index << '\t' << p.normalized_raw_cfo_hz << '\t'
                << p.normalized_dealiased_cfo_hz << '\t' << location.observation_ids[point]
                << '\t' << static_cast<unsigned>(location.training_mask[point]) << '\t'
                << location.times_s[point] << '\t' << location.measured_hz[point] << '\n';
        }
    }
    if (!out) throw std::runtime_error("cannot write tracks output");
}

void write_summary(const std::string& path, const RecordedBundle& bundle,
        const leo_scanner_source_stats& source, const live::Summary& analysis,
        const online::Snapshot* snapshot, std::size_t events,
        const server_compat::CacheStats& support) {
    const auto& s = source.scanner;
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot create summary output");
    out << std::boolalpha << std::setprecision(std::numeric_limits<double>::max_digits10)
        << "{\"schema\":\"leo-recorded-ds9-application/v1\","
        << "\"execution_mode\":\"recorded_unpaced\",\"freshness_qualified\":false,"
        << "\"cadence_qualified\":false,\"historical_profile_crc_available\":false,"
        << "\"session_id\":\"" << bundle.session_id << "\",\"generation\":"
        << bundle.generation << ",\"plan_visits\":" << bundle.plan_rows.size()
        << ",\"serialized_events\":" << events
        << ",\"scanner\":{\"visits_started\":" << s.visits_started
        << ",\"visits_intact\":" << s.visits_intact
        << ",\"visits_incomplete\":" << s.visits_incomplete
        << ",\"windows_emitted\":" << s.windows_emitted
        << ",\"detector_accepted\":" << s.detector_accepted
        << ",\"detector_completed\":" << s.detector_completed
        << ",\"detector_failures\":" << s.detector_failures
        << ",\"detector_queue_drops\":" << s.detector_queue_drops
        << ",\"detector_rows\":" << s.detector_rows
        << ",\"detector_candidates\":" << s.detector_candidates
        << ",\"missing_samples\":" << s.missing_samples
        << ",\"queue_high_water\":" << s.detector_queue_high_water
        << ",\"stop_reason\":" << s.stop_reason << ",\"stop_status\":" << s.stop_status
        << "},\"source\":{\"overflow_blocks\":" << source.overflow_blocks
        << ",\"discontinuity_blocks\":" << source.discontinuity_blocks
        << ",\"unknown_discontinuities\":" << source.unknown_discontinuities
        << ",\"exact_missing_samples\":" << source.exact_missing_samples
        << ",\"counter_authority\":" << source.counter_authority
        << ",\"position_semantics\":" << source.position_semantics
        << ",\"time_authority\":" << source.time_authority
        << ",\"physical_counter_qualified\":" << source.physical_counter_qualified
        << "},\"analysis\":{\"scanner_candidates\":" << analysis.scanner_candidates
        << ",\"accepted_candidates\":" << analysis.accepted_candidates
        << ",\"rejected_candidates\":" << analysis.rejected_candidates
        << ",\"detector_latency_violations\":" << analysis.detector_latency_violations
        << ",\"detector_failures\":" << analysis.detector_failures
        << ",\"invalid_candidate_events\":" << analysis.invalid_candidate_events
        << ",\"timing_failures\":" << analysis.timing_failures
        << ",\"publications\":" << analysis.publications
        << ",\"publication_failures\":" << analysis.publication_failures
        << ",\"searches_started\":" << analysis.searches_started
        << ",\"searches_complete\":" << analysis.searches_complete
        << ",\"search_failures\":" << analysis.search_failures
        << ",\"timing_qualified_internal\":" << analysis.timing_qualified
        << ",\"session_projected\":" << analysis.session.projected
        << ",\"session_nonpassing\":" << analysis.session.nonpassing
        << ",\"session_consumed\":" << analysis.session.consumed
        << ",\"session_rejected\":" << analysis.session.rejected
        << ",\"session_queue_dropped\":" << analysis.session.queue_dropped
        << ",\"support_derived\":" << analysis.session.support_derived
        << ",\"support_invalid\":" << analysis.session.support_invalid
        << ",\"support_unavailable\":" << analysis.session.support_unavailable
        << "},\"support_profile\":{\"name\":\"" << analysis.support_profile.profile_name
        << "\",\"manifest\":\"" << analysis.support_profile.profile_manifest_digest
        << "\",\"cache_hits\":" << support.hits << ",\"cache_misses\":" << support.misses
        << "},\"snapshot\":{\"available\":" << (snapshot != nullptr)
        << ",\"generation\":" << (snapshot ? snapshot->generation : 0U)
        << ",\"watermark_utc_ns\":" << (snapshot ? snapshot->watermark_utc_ns : 0)
        << ",\"retained_observations\":" << (snapshot ? snapshot->retained_observation_count : 0U)
        << ",\"tracks\":" << (snapshot ? snapshot->tracking_result.tracks.size() : 0U)
        << ",\"location_tracks\":" << (snapshot ? snapshot->location_tracks.records.size() : 0U)
        << "},\"search\":{\"state\":" << static_cast<unsigned>(analysis.last_search.state)
        << ",\"status\":" << static_cast<unsigned>(analysis.last_search.status)
        << ",\"evaluated_points\":" << analysis.last_search.evaluated_points
        << ",\"has_incumbent\":" << analysis.last_search.has_incumbent
        << ",\"weighted_mse_hz2\":" << analysis.last_search.incumbent.weighted_mse_hz2
        << ",\"matched_tracks\":" << analysis.last_search.incumbent_matched_tracks
        << ",\"unmatched_tracks\":" << analysis.last_search.incumbent_unmatched_tracks
        << "}}\n";
    if (!out) throw std::runtime_error("cannot write summary output");
}

void require_success(const RecordedBundle& bundle, const leo_scanner_source_stats& source,
        const live::Summary& analysis) {
    const auto visits = bundle.plan_rows.size(); const auto& scanner = source.scanner;
    if (scanner.stop_status || scanner.visits_started != visits ||
        scanner.visits_intact != visits || scanner.visits_incomplete ||
        scanner.detector_accepted != visits || scanner.detector_completed != visits ||
        scanner.detector_failures || scanner.detector_queue_drops || scanner.missing_samples ||
        source.overflow_blocks || source.discontinuity_blocks || source.unknown_discontinuities ||
        source.exact_missing_samples || analysis.scanner_queue_drops || analysis.detector_failures ||
        analysis.detector_latency_violations || analysis.invalid_candidate_events ||
        analysis.timing_failures || analysis.session.rejected || analysis.session.queue_dropped ||
        analysis.session.support_invalid || analysis.session.support_unavailable ||
        analysis.session.support_unhealthy || analysis.publication_failures ||
        analysis.search_failures || !analysis.support_profile_bound ||
        analysis.session.support_derived != analysis.accepted_candidates)
        throw std::runtime_error("recorded composition did not finish losslessly");
}

} // namespace

int run_cli(int argc, char** argv) {
    try {
        Parsed parsed;
        if (!parse(argc, argv, parsed)) throw std::runtime_error(
            "usage: leo-recorded-ds9 --bundle-native PATH --bundle-sha256 HEX "
            "--analysis-digest sha256:HEX --exact-template PATH --control-template PATH "
            "--tle-catalogue PATH --search-origin LAT LON --search-radius-km KM "
            "--search-region-km KM --search-level-km KM --search-point-budget N "
            "--search-slice-points N --wall-seconds N --detector-workers 1 "
            "--analysis-workers 1..4 --output NEW_ABSOLUTE_DIRECTORY");
        require_new_safe_output(parsed.output);

        RecordedBundle bundle;
        const auto bundle_status = read_recorded_bundle(parsed.bundle, parsed.bundle_sha,
            parsed.analysis_digest, bundle);
        if (bundle_status != RecordedBundleStatus::ok)
            throw std::runtime_error("recorded bundle rejected: " +
                std::to_string(static_cast<unsigned>(bundle_status)));
        if (bundle.plan_rows.size() > maximum_recorded_visits)
            throw std::runtime_error("recorded application v1 is bounded to 32 visits");

        const auto exact = read_exact<leo_native_glrt_complex>(parsed.exact,
            template_complex_count);
        const auto control = read_exact<leo_native_glrt_complex>(parsed.control,
            template_complex_count);
        auto catalogue = read_tles(parsed.tles);
        const auto detector_configuration = detector_digest(parsed, bundle, exact, control);

        leo_corrected_profile_adapter* adapter_raw = nullptr;
        if (leo_corrected_profile_adapter_create(&adapter_raw, bundle.sample_rate_hz,
                exact.data(), control.data(), exact.size()))
            throw std::runtime_error("cannot create corrected detector adapter");
        AdapterOwner adapter(adapter_raw);
        leo_scanner_profile_detector_binding detector{};
        if (leo_corrected_profile_adapter_binding(adapter.get(), detector_configuration.data(),
                &detector))
            throw std::runtime_error("cannot bind corrected detector adapter");

        std::vector<leo_recorded_source_visit_file> source_files(bundle.plan_rows.size());
        for (std::size_t i = 0; i < source_files.size(); ++i) {
            source_files[i].visit = bundle.plan_rows[i];
            source_files[i].raw_ci16_path = bundle.raw_files[i].canonical_path.c_str();
            std::copy(bundle.raw_files[i].raw_digest.begin(), bundle.raw_files[i].raw_digest.end(),
                source_files[i].raw_sha256);
            source_files[i].raw_bytes = bundle.raw_files[i].raw_bytes;
        }
        leo_recorded_source_config source_config{LEO_RECORDED_SOURCE_ABI_VERSION,
            bundle.sample_rate_hz, bundle.receiver_count, 150000U,
            static_cast<std::uint32_t>(source_files.size()), source_files.data()};
        leo_recorded_source* source_raw = nullptr;
        if (leo_recorded_source_create(&source_config, &source_raw))
            throw std::runtime_error("cannot create recorded source");
        SourceOwner source(source_raw);
        leo_source_port* source_port = leo_recorded_source_port(source.get());
        if (!source_port) throw std::runtime_error("recorded source has no port");

        server_compat::SupportDeriver support(server_compat::authority_binding());
        online::Config online;
        online.publication_search_policy = online::PublicationSearchPolicy::pin_started_snapshot;
        online.history_window_ns = 600'000'000'000LL;
        online.maximum_satellites = static_cast<std::uint32_t>(catalogue.size());
        online.maximum_knots = 96U;
        online.maximum_search_points = parsed.search_budget;
        online.maximum_orbit_bytes = catalogue.size() * 96U * sizeof(leo_orbit_state) * 2U;
        online::SearchConfig search{};
        search.origin_latitude_deg = parsed.latitude; search.origin_longitude_deg = parsed.longitude;
        search.score = leo_score_default_config(); search.policy.radius_km = parsed.radius_km;
        search.policy.region_size_km = parsed.region_km; search.policy.level_count = 1U;
        search.policy.levels_km[0] = parsed.level_km; search.policy.budget_points = parsed.search_budget;
        const auto bracket_center = bundle.timing.utc_before_ns +
            (bundle.timing.utc_after_ns - bundle.timing.utc_before_ns) / 2;
        live::AnalysisConfig analysis_config{bundle.ingest_authority,
            recorded_timing_config(bundle), online,
            {bundle.session_id, bundle.ingest_authority.input_digest, bracket_center},
            std::move(catalogue), search, 300'000'000'000ULL, 5'000'000'000ULL,
            parsed.search_slice, 20.0, 96U, true, parsed.analysis_workers,
            server_compat::derivation_port(support)};
        live::Analysis analysis(std::move(analysis_config));
        if (analysis.observe(bundle.timing) != timing::Status::ok)
            throw std::runtime_error("saved timing bracket rejected");
        analysis.set_cancel(source_port, cancel_source);

        leo_scanner_recorded_config scanner{};
        scanner.abi_version = LEO_SCANNER_RECORDED_PLAN_ABI_VERSION;
        scanner.session = bundle.scanner_session; scanner.generation = bundle.generation;
        scanner.sample_rate_hz = bundle.sample_rate_hz; scanner.receiver_count = bundle.receiver_count;
        const auto now = monotonic_ns();
        const auto allowance = static_cast<std::uint64_t>(parsed.wall_seconds) * 1000000000ULL;
        if (now > UINT64_MAX - allowance) throw std::runtime_error("deadline overflow");
        scanner.wall_deadline_monotonic_ns = now + allowance;
        scanner.detector_queue_capacity = 1U;
        scanner.target_count = static_cast<std::uint32_t>(bundle.targets.size());
        for (const auto& target : bundle.targets)
            scanner.targets[target.target_index] = {target.target_key,
                target.requested_tuned_if_hz, target.profile_crc32, 1U};
        leo_scanner_recorded_plan plan{LEO_SCANNER_RECORDED_PLAN_ABI_VERSION,
            static_cast<std::uint32_t>(bundle.plan_rows.size()), bundle.plan_rows.data(), {}};
        std::copy(bundle.plan_digest.begin(), bundle.plan_digest.end(), plan.plan_digest);
        leo_scanner_source_requirements requirements{LEO_SCANNER_SOURCE_ABI_VERSION,
            LEO_SOURCE_COUNTER_PROVIDER_EXACT, LEO_SOURCE_POSITION_COHERENT_CURRENT,
            LEO_SOURCE_CAP_CANCEL | LEO_SOURCE_CAP_SELECT | LEO_SOURCE_CAP_SIMULTANEOUS_RX |
                LEO_SOURCE_CAP_COHERENT_RX | LEO_SOURCE_CAP_FREQUENCY_ATTESTATION |
                LEO_SOURCE_CAP_TARGET_ATTESTATION | LEO_SOURCE_CAP_EXACT_GAP |
                LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY,
            historical_transition_flags, 1U, 1U};
        leo_scanner_geometry_port geometry{&bundle.corrected_geometry,
            derive_corrected_geometry, {}};
        std::copy(bundle.corrected_geometry.manifest_digest.begin(),
            bundle.corrected_geometry.manifest_digest.end(), geometry.profile_manifest_digest);
        leo_scanner_profile_execution_options execution{LEO_SCANNER_PROFILE_ABI_VERSION,
            parsed.detector_workers, &detector, geometry};
        Sink sink{&analysis, source_port, {}, {}};
        sink.events.reserve(bundle.plan_rows.size() * 20U);
        leo_scanner_source_stats source_stats{};
        const int scanner_status = leo_scanner_run_source_profiled_recorded_ex(&scanner, &plan,
            source_port, &requirements, &execution, event_sink, &sink, &source_stats);
        analysis.detach_cancel();
        if (sink.failure) std::rethrow_exception(sink.failure);
        if (scanner_status) throw std::runtime_error("recorded scanner failed: " +
            std::to_string(scanner_status));
        const auto summary = analysis.finish_after_rf_stopped();
        const auto snapshot = analysis.final_published_snapshot();
        require_success(bundle, source_stats, summary);

        AtomicDirectory output(parsed.output);
        write_events(output.staging + "/events.tsv", sink.events);
        write_tracks(output.staging + "/tracks.tsv", snapshot.get());
        write_summary(output.staging + "/summary.json", bundle, source_stats, summary,
            snapshot.get(), sink.events.size(), support.cache_stats());
        output.commit();
        std::cout << "{\"schema\":\"leo-recorded-ds9-application-cli/v1\","
            "\"execution_mode\":\"recorded_unpaced\",\"freshness_qualified\":false,"
            "\"visits\":" << bundle.plan_rows.size() << ",\"candidates\":"
            << summary.accepted_candidates << ",\"tracks\":"
            << (snapshot ? snapshot->tracking_result.tracks.size() : 0U) << ",\"output\":\""
            << parsed.output << "\"}\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}

} // namespace leo::adaptive::application::recorded

#ifndef LEO_RECORDED_APPLICATION_NO_MAIN
int main(int argc, char** argv) {
    return leo::adaptive::application::recorded::run_cli(argc, argv);
}
#endif
