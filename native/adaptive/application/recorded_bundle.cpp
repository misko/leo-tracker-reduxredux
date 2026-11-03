#include "recorded_bundle.hpp"
#include "../runtime/sha256.hpp"

#include <algorithm>
#include <cerrno>
#include <climits>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <locale.h>
#include <memory>
#include <string_view>
#include <sys/stat.h>
#include <type_traits>
#include <utility>

namespace leo::adaptive::application {
namespace {
constexpr std::size_t max_file_bytes = 16U * 1024U * 1024U;
constexpr std::size_t max_line_bytes = 2048U;
constexpr std::size_t max_visits = LEO_SCANNER_RECORDED_PLAN_MAX_VISITS;
constexpr std::uint32_t historical_transition_flags =
    LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
    LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
    LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;

bool canonical_unsigned(std::string_view text) {
    if (text.empty() || (text.size() > 1 && text.front() == '0')) return false;
    return std::all_of(text.begin(), text.end(), [](char c) {
        return c >= '0' && c <= '9';
    });
}

template <class T> bool unsigned_value(std::string_view text, T& output) {
    static_assert(std::is_unsigned<T>::value, "unsigned integer required");
    if (!canonical_unsigned(text)) return false;
    T value = 0;
    for (char digit : text) {
        const auto part = static_cast<T>(digit - '0');
        if (value > (std::numeric_limits<T>::max() - part) / 10) return false;
        value = static_cast<T>(value * 10 + part);
    }
    output = value;
    return true;
}

bool signed_value(std::string_view text, std::int64_t& output) {
    if (text.empty() || text.front() == '+') return false;
    const bool negative = text.front() == '-';
    const auto digits = negative ? text.substr(1) : text;
    if (!canonical_unsigned(digits) || (negative && digits == "0")) return false;
    std::uint64_t magnitude = 0;
    if (!unsigned_value(digits, magnitude)) return false;
    const auto limit = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    if ((!negative && magnitude > limit) || (negative && magnitude > limit + 1U))
        return false;
    output = negative ? (magnitude == limit + 1U ?
        std::numeric_limits<std::int64_t>::min() : -static_cast<std::int64_t>(magnitude)) :
        static_cast<std::int64_t>(magnitude);
    return true;
}

bool canonical_decimal(std::string_view text) {
    if (text.empty() || text.front() == '+') return false;
    std::size_t at = text.front() == '-' ? 1U : 0U;
    if (at == text.size()) return false;
    const std::size_t integer = at;
    if (text[at] == '0') {
        ++at;
        if (at < text.size() && text[at] >= '0' && text[at] <= '9') return false;
    } else {
        if (text[at] < '1' || text[at] > '9') return false;
        while (at < text.size() && text[at] >= '0' && text[at] <= '9') ++at;
    }
    if (at < text.size() && text[at] == '.') {
        const auto fraction = ++at;
        while (at < text.size() && text[at] >= '0' && text[at] <= '9') ++at;
        if (at == fraction || text[at - 1] == '0') return false;
    }
    if (at < text.size() && text[at] == 'e') {
        ++at;
        if (at < text.size() && text[at] == '-') ++at;
        const auto exponent = at;
        if (at == text.size() || text[at] < '0' || text[at] > '9') return false;
        if (text[at] == '0' && at + 1U < text.size()) return false;
        while (at < text.size() && text[at] >= '0' && text[at] <= '9') ++at;
        if (at == exponent) return false;
    }
    return integer < text.size() && at == text.size();
}

bool double_value(std::string_view text, locale_t locale, double& output) {
    if (!canonical_decimal(text)) return false;
    std::string owned(text);
    char* end = nullptr;
    errno = 0;
    const double value = strtod_l(owned.c_str(), &end, locale);
    if (errno == ERANGE || end != owned.c_str() + owned.size() ||
        !std::isfinite(value) || (value == 0 && std::signbit(value))) return false;
    output = value;
    return true;
}

int nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

bool digest_value(std::string_view text, std::array<std::uint8_t, 32>& output) {
    if (text.size() != 64U) return false;
    std::array<std::uint8_t, 32> value{};
    std::uint8_t combined = 0;
    for (std::size_t i = 0; i < value.size(); ++i) {
        const int high = nibble(text[2 * i]), low = nibble(text[2 * i + 1]);
        if (high < 0 || low < 0) return false;
        value[i] = static_cast<std::uint8_t>((high << 4) | low);
        combined |= value[i];
    }
    if (!combined) return false;
    output = value;
    return true;
}

bool analysis_digest_value(const std::string& text) {
    std::array<std::uint8_t, 32> ignored{};
    return text.size() == 71U && text.compare(0, 7, "sha256:") == 0 &&
        digest_value(std::string_view(text).substr(7), ignored);
}

bool token(std::string_view value, std::size_t maximum) {
    return !value.empty() && value.size() <= maximum &&
        std::all_of(value.begin(), value.end(), [](char c) {
            return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-';
        });
}

std::vector<std::string_view> fields(std::string_view line) {
    std::vector<std::string_view> result;
    std::size_t begin = 0;
    while (true) {
        const auto separator = line.find('\t', begin);
        result.push_back(line.substr(begin, separator == std::string_view::npos ?
            line.size() - begin : separator - begin));
        if (separator == std::string_view::npos) break;
        begin = separator + 1U;
    }
    return result;
}

bool safe_relative(std::string_view path) {
    if (path.empty() || path.size() > 512U || path.front() == '/' ||
        path.back() == '/' || path.find('\\') != std::string_view::npos)
        return false;
    std::size_t begin = 0;
    while (begin < path.size()) {
        const auto separator = path.find('/', begin);
        const auto part = path.substr(begin, separator == std::string_view::npos ?
            path.size() - begin : separator - begin);
        if (part.empty() || part == "." || part == ".." ||
            !std::all_of(part.begin(), part.end(), [](char c) {
                return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                    (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-';
            })) return false;
        if (separator == std::string_view::npos) break;
        begin = separator + 1U;
    }
    return true;
}

bool below_root(const std::string& root, const std::string& path) {
    if (root == "/") return path.size() > 1U && path.front() == '/';
    return path.size() > root.size() && path.compare(0, root.size(), root) == 0 &&
        path[root.size()] == '/';
}

std::string dirname(const std::string& path) {
    const auto slash = path.rfind('/');
    return slash == std::string::npos ? "." : slash == 0 ? "/" : path.substr(0, slash);
}

bool canonical_existing(const std::string& path, std::string& output) {
    std::unique_ptr<char, decltype(&std::free)> resolved(realpath(path.c_str(), nullptr),
        &std::free);
    if (!resolved) return false;
    output = resolved.get();
    return true;
}

RecordedBundleStatus read_bytes(const std::string& path, std::string& output,
                                std::string& canonical_path) {
    if (!canonical_existing(path, canonical_path)) return RecordedBundleStatus::open_failed;
    struct stat metadata{};
    if (stat(canonical_path.c_str(), &metadata) || !S_ISREG(metadata.st_mode))
        return RecordedBundleStatus::open_failed;
    if (metadata.st_size < 0 || static_cast<std::uint64_t>(metadata.st_size) > max_file_bytes)
        return RecordedBundleStatus::file_too_large;
    std::ifstream input(canonical_path, std::ios::binary);
    if (!input) return RecordedBundleStatus::open_failed;
    output.assign(static_cast<std::size_t>(metadata.st_size), '\0');
    if (!output.empty()) input.read(output.data(), static_cast<std::streamsize>(output.size()));
    if (!input || input.peek() != std::char_traits<char>::eof())
        return RecordedBundleStatus::io_error;
    return RecordedBundleStatus::ok;
}

bool checked_multiply(std::uint64_t left, std::uint64_t right,
                      std::uint64_t& output) {
    if (right && left > std::numeric_limits<std::uint64_t>::max() / right)
        return false;
    output = left * right;
    return true;
}

struct LocaleGuard {
    locale_t value{};
    explicit LocaleGuard(locale_t input) : value(input) {}
    ~LocaleGuard() { if (value) freelocale(value); }
    LocaleGuard(const LocaleGuard&) = delete;
    LocaleGuard& operator=(const LocaleGuard&) = delete;
};
}

RecordedBundleStatus read_recorded_bundle(const std::string& native_tsv_path,
        const std::string& expected_native_tsv_sha256,
        const std::string& analysis_digest, RecordedBundle& output) noexcept {
    try {
        std::array<std::uint8_t, 32> expected_digest{};
        if (native_tsv_path.empty() ||
            !digest_value(expected_native_tsv_sha256, expected_digest) ||
            !analysis_digest_value(analysis_digest))
            return RecordedBundleStatus::invalid_argument;
        std::string bytes, canonical_native;
        const auto read = read_bytes(native_tsv_path, bytes, canonical_native);
        if (read != RecordedBundleStatus::ok) return read;
        // The trust anchor is checked before interpreting even the FORMAT row.
        if (sha256(bytes) != expected_native_tsv_sha256)
            return RecordedBundleStatus::digest_mismatch;
        if (bytes.empty() || bytes.back() != '\n') return RecordedBundleStatus::malformed;
        for (unsigned char value : bytes)
            if (value != '\n' && value != '\t' && (value < 0x20U || value > 0x7eU))
                return RecordedBundleStatus::malformed;

        RecordedBundle result;
        result.native_tsv_path = canonical_native;
        result.bundle_root = dirname(canonical_native);
        result.native_tsv_digest = expected_digest;
        std::vector<std::string_view> lines;
        std::size_t begin = 0;
        while (begin < bytes.size()) {
            const auto newline = bytes.find('\n', begin);
            if (newline == std::string::npos || newline == begin ||
                newline - begin > max_line_bytes) return RecordedBundleStatus::malformed;
            lines.push_back(std::string_view(bytes).substr(begin, newline - begin));
            begin = newline + 1U;
        }
        if (lines.size() < 5U || lines.size() > 3U + LEO_SCANNER_MAX_TARGETS + max_visits)
            return RecordedBundleStatus::malformed;

        auto format = fields(lines[0]);
        if (format.size() != 2U || format[0] != "FORMAT" ||
            format[1] != "leo-recorded-ds9/v1") return RecordedBundleStatus::malformed;
        auto session = fields(lines[1]);
        if (session.size() != 10U || session[0] != "SESSION" ||
            !token(session[1], 128U) ||
            !unsigned_value(session[2], result.scanner_session) || !result.scanner_session ||
            !unsigned_value(session[3], result.generation) || !result.generation ||
            !unsigned_value(session[4], result.sample_rate_hz) ||
            !unsigned_value(session[5], result.receiver_count) ||
            !unsigned_value(session[6], result.analog_bandwidth_hz) ||
            !digest_value(session[7], result.recording_manifest_digest) ||
            !digest_value(session[8], result.calibration_manifest_digest) ||
            !digest_value(session[9], result.plan_digest) ||
            result.sample_rate_hz != 7500000U || result.receiver_count != 2U ||
            result.analog_bandwidth_hz != 7500000U)
            return RecordedBundleStatus::malformed;
        result.session_id = std::string(session[1]);

        auto timing = fields(lines[2]);
        std::uint32_t qualified = 0;
        if (timing.size() != 8U || timing[0] != "TIMING" ||
            !unsigned_value(timing[1], qualified) || qualified != 1U ||
            !unsigned_value(timing[2], result.timing.monotonic_before_ns) ||
            !unsigned_value(timing[3], result.timing.monotonic_after_ns) ||
            !unsigned_value(timing[4], result.timing.counter) ||
            !signed_value(timing[5], result.timing.utc_before_ns) ||
            !signed_value(timing[6], result.timing.utc_after_ns) ||
            !unsigned_value(timing[7], result.timing_bracket_width_ns) ||
            result.timing.utc_before_ns <= 0 ||
            result.timing.utc_after_ns < result.timing.utc_before_ns ||
            result.timing.monotonic_after_ns < result.timing.monotonic_before_ns ||
            static_cast<std::uint64_t>(result.timing.utc_after_ns -
                result.timing.utc_before_ns) != result.timing_bracket_width_ns)
            return RecordedBundleStatus::malformed;
        const auto monotonic_width = result.timing.monotonic_after_ns -
            result.timing.monotonic_before_ns;
        // UTC reads are nested inside the monotonic reads. Match Timebase's
        // one-sided clock-resolution allowance without an overflowing add.
        if (result.timing_bracket_width_ns > monotonic_width &&
            result.timing_bracket_width_ns - monotonic_width > UINT64_C(1000000))
            return RecordedBundleStatus::malformed;
        result.timing.exact_counter = true;

        LocaleGuard c_locale{newlocale(LC_NUMERIC_MASK, "C", nullptr)};
        if (!c_locale.value) return RecordedBundleStatus::no_memory;
        std::size_t row = 3U;
        while (row < lines.size() && lines[row].substr(0, 7) == "TARGET\t") {
            if (result.targets.size() == LEO_SCANNER_MAX_TARGETS)
                return RecordedBundleStatus::malformed;
            auto value = fields(lines[row++]);
            RecordedTarget target;
            std::string_view edge;
            if (value.size() != 13U || value[0] != "TARGET" ||
                !unsigned_value(value[1], target.target_index) ||
                target.target_index != result.targets.size() ||
                !unsigned_value(value[2], target.target_key) ||
                target.target_key >= LEO_SCANNER_MAX_TARGETS ||
                !unsigned_value(value[3], target.channel) ||
                target.channel < 1U || target.channel > 4U ||
                ((edge = value[4]) != "lower" && edge != "upper") ||
                !unsigned_value(value[5], target.requested_tuned_if_hz) ||
                !unsigned_value(value[6], target.actual_tuned_if_hz) ||
                !unsigned_value(value[7], target.actual_rf_hz) ||
                !double_value(value[8], c_locale.value, target.pilot_if_hz[0]) ||
                !double_value(value[9], c_locale.value, target.pilot_if_hz[1]) ||
                !double_value(value[10], c_locale.value, target.template_min_hz) ||
                !double_value(value[11], c_locale.value, target.template_max_hz) ||
                !unsigned_value(value[12], target.profile_crc32) ||
                target.requested_tuned_if_hz != target.actual_tuned_if_hz ||
                !target.actual_tuned_if_hz ||
                target.actual_tuned_if_hz > UINT64_C(9007199254740992) ||
                !target.actual_rf_hz || target.actual_rf_hz > UINT64_C(9007199254740992) ||
                target.template_min_hz >= target.template_max_hz ||
                target.profile_crc32 != 0U)
                return RecordedBundleStatus::malformed;
            target.upper_edge = edge == "upper";
            if (std::any_of(result.targets.begin(), result.targets.end(),
                    [&](const RecordedTarget& old) { return old.target_key == target.target_key; }))
                return RecordedBundleStatus::malformed;
            result.targets.push_back(target);
        }
        if (result.targets.empty()) return RecordedBundleStatus::malformed;

        const std::uint64_t samples = static_cast<std::uint64_t>(result.sample_rate_hz) *
            120U / 1000U;
        std::uint64_t expected_raw_bytes = 0;
        if (!checked_multiply(samples, result.receiver_count * 2U * sizeof(std::int16_t),
                              expected_raw_bytes))
            return RecordedBundleStatus::malformed;
        while (row < lines.size()) {
            if (result.plan_rows.size() == max_visits)
                return RecordedBundleStatus::malformed;
            auto value = fields(lines[row++]);
            leo_scanner_recorded_visit visit{};
            RecordedRawFile raw;
            if (value.size() != 19U || value[0] != "VISIT")
                return RecordedBundleStatus::malformed;
            if (!safe_relative(value[18])) return RecordedBundleStatus::unsafe_path;
            if (
                !unsigned_value(value[1], visit.visit) ||
                !unsigned_value(value[2], visit.target_index) ||
                !unsigned_value(value[3], visit.target_key) ||
                !unsigned_value(value[4], visit.dwell_ms) ||
                !unsigned_value(value[5], visit.selection_applied) ||
                !unsigned_value(value[6], visit.expected_transition_flags) ||
                !unsigned_value(value[7], visit.expected_profile_crc32) ||
                !unsigned_value(value[8], visit.requested_frequency_hz) ||
                !unsigned_value(value[9], visit.expected_actual_frequency_hz) ||
                !unsigned_value(value[10], visit.selection_counter) ||
                !unsigned_value(value[11], visit.transition_previous_valid_end) ||
                !unsigned_value(value[12], visit.transition_valid_start) ||
                !unsigned_value(value[13], visit.valid_start) ||
                !unsigned_value(value[14], visit.valid_end) ||
                !digest_value(value[15], raw.recording_event_digest) ||
                !digest_value(value[16], raw.raw_digest) ||
                !unsigned_value(value[17], raw.raw_bytes) ||
                visit.target_index >= result.targets.size() ||
                visit.dwell_ms != 120U || visit.selection_applied != 1U ||
                visit.expected_transition_flags != historical_transition_flags ||
                visit.expected_profile_crc32 != 0U ||
                visit.transition_previous_valid_end > visit.selection_counter ||
                visit.selection_counter > visit.transition_valid_start ||
                visit.transition_valid_start != visit.valid_start ||
                visit.valid_end <= visit.valid_start ||
                visit.valid_end - visit.valid_start != samples ||
                raw.raw_bytes != expected_raw_bytes)
                return RecordedBundleStatus::malformed;
            const auto& target = result.targets[visit.target_index];
            if (visit.target_key != target.target_key ||
                visit.requested_frequency_hz != target.requested_tuned_if_hz ||
                visit.expected_actual_frequency_hz != target.actual_tuned_if_hz ||
                (!result.plan_rows.empty() &&
                    (visit.visit <= result.plan_rows.back().visit ||
                     visit.valid_start <= result.plan_rows.back().valid_start ||
                     visit.selection_counter < result.plan_rows.back().valid_end)))
                return RecordedBundleStatus::malformed;
            raw.visit = visit.visit;
            raw.relative_path = std::string(value[18]);
            const std::string joined = result.bundle_root + "/" + raw.relative_path;
            if (!canonical_existing(joined, raw.canonical_path) ||
                !below_root(result.bundle_root, raw.canonical_path))
                return RecordedBundleStatus::unsafe_path;
            struct stat metadata{};
            if (stat(raw.canonical_path.c_str(), &metadata) ||
                !S_ISREG(metadata.st_mode) || metadata.st_size < 0 ||
                static_cast<std::uint64_t>(metadata.st_size) != raw.raw_bytes)
                return RecordedBundleStatus::malformed;
            result.plan_rows.push_back(visit);
            result.raw_files.push_back(std::move(raw));
        }
        if (result.plan_rows.empty() || result.timing.counter > result.plan_rows.front().valid_start)
            return RecordedBundleStatus::malformed;

        result.corrected_geometry.manifest_digest = result.calibration_manifest_digest;
        result.corrected_geometry.sample_rate_hz = result.sample_rate_hz;
        result.corrected_geometry.bandwidth_hz = result.analog_bandwidth_hz;
        result.corrected_geometry.policy_half_width_hz = 800000.0;
        result.corrected_geometry.target_count = static_cast<std::uint32_t>(result.targets.size());
        result.ingest_authority.generation = result.generation;
        result.ingest_authority.sample_rate_hz = result.sample_rate_hz;
        result.ingest_authority.input_digest = "sha256:" + std::string(session[7]);
        result.ingest_authority.analysis_digest = analysis_digest;
        result.ingest_authority.profile_authority = ingest::ProfileAuthority::historical_metadata;
        result.ingest_authority.targets.reserve(result.targets.size());
        for (const auto& target : result.targets) {
            auto& geometry = result.corrected_geometry.targets[target.target_index];
            geometry.target_key = target.target_key;
            geometry.tuned_if_hz = target.actual_tuned_if_hz;
            geometry.pilot_if_hz = target.pilot_if_hz;
            geometry.template_min_hz = target.template_min_hz;
            geometry.template_max_hz = target.template_max_hz;
            result.ingest_authority.targets.push_back(ingest::Target{target.target_key,
                target.profile_crc32, target.channel, target.actual_tuned_if_hz,
                static_cast<double>(target.actual_rf_hz), target.upper_edge});
        }
        output = std::move(result);
        return RecordedBundleStatus::ok;
    } catch (const std::bad_alloc&) { return RecordedBundleStatus::no_memory; }
      catch (...) { return RecordedBundleStatus::io_error; }
}

timing::Config recorded_timing_config(const RecordedBundle& bundle) {
    return {bundle.sample_rate_hz, UINT64_C(1000000000), UINT64_C(1801000000000),
        0, UINT64_C(1000000), 8};
}

}
