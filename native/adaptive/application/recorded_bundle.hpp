#pragma once

#include "corrected_geometry.hpp"
#include "../ingest/ingest.hpp"
#include "../scanner/scanner_recorded_plan.h"
#include "../timing/timebase.hpp"

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace leo::adaptive::application {

enum class RecordedBundleStatus {
    ok,
    invalid_argument,
    open_failed,
    file_too_large,
    digest_mismatch,
    malformed,
    unsafe_path,
    no_memory,
    io_error,
};

struct RecordedTarget {
    std::uint32_t target_index{}, target_key{}, channel{};
    bool upper_edge{};
    std::uint64_t requested_tuned_if_hz{}, actual_tuned_if_hz{}, actual_rf_hz{};
    std::array<double, 2> pilot_if_hz{};
    double template_min_hz{}, template_max_hz{};
    std::uint32_t profile_crc32{};
};

struct RecordedRawFile {
    std::uint64_t visit{};
    std::array<std::uint8_t, 32> recording_event_digest{}, raw_digest{};
    std::uint64_t raw_bytes{};
    std::string relative_path, canonical_path;
};

/* All storage is value-owned. A leo_scanner_recorded_plan may borrow
 * plan_rows.data() only while this Bundle remains alive and unchanged. */
struct RecordedBundle {
    std::string native_tsv_path, bundle_root, session_id;
    std::uint64_t scanner_session{}, generation{};
    std::uint32_t sample_rate_hz{}, receiver_count{}, analog_bandwidth_hz{};
    std::array<std::uint8_t, 32> native_tsv_digest{}, recording_manifest_digest{},
        calibration_manifest_digest{}, plan_digest{};
    timing::Bracket timing;
    std::uint64_t timing_bracket_width_ns{};
    std::vector<RecordedTarget> targets;
    std::vector<leo_scanner_recorded_visit> plan_rows;
    std::vector<RecordedRawFile> raw_files;
    CorrectedGeometryProfile corrected_geometry;
    ingest::Authority ingest_authority;
};

/* Verifies the externally supplied native.tsv SHA-256 before parsing any row.
 * analysis_digest is a caller-owned sha256:<64 lower hex> binding over the
 * detector/support composition; it is copied into ingest_authority. Raw files
 * are not read here, but every path is canonicalized beneath the bundle root
 * and its regular-file size is checked before this call succeeds. */
RecordedBundleStatus read_recorded_bundle(const std::string& native_tsv_path,
    const std::string& expected_native_tsv_sha256,
    const std::string& analysis_digest, RecordedBundle& output) noexcept;

/* Timing authority paired with read_recorded_bundle's saved-bracket checks.
 * In particular, the reader's bounded 1 ms clock-resolution allowance must
 * remain present when the bracket enters Timebase. */
timing::Config recorded_timing_config(const RecordedBundle&);

}
