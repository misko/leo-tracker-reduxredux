#pragma once
#include "../scanner/scanner.h"
#include "../runtime/projection.hpp"
#include "../timing/timebase.hpp"
#include <vector>

namespace leo::adaptive::ingest {
enum class ProfileAuthority { live_attested, historical_metadata };
struct Target {
    std::uint32_t profile{}, profile_crc32{}, channel{};
    std::uint64_t tuning_frequency_hz{};
    double actual_rf_hz{};
    bool upper_edge{};
};
struct Authority {
    std::uint64_t generation{};
    std::uint32_t sample_rate_hz{};
    std::string input_digest, analysis_digest;
    std::vector<Target> targets;
    // Some historical recordings lack a persisted profile CRC. Replay may
    // explicitly declare that absence; a live source must never use this mode.
    ProfileAuthority profile_authority{ProfileAuthority::live_attested};
};
// Explicit timing authority for a bounded historical source. The values are
// copied from persisted source metadata; they are not a replacement for live
// clock observations or a claim about runtime freshness. The caller remains
// responsible for validating the source envelope and forwarding only events
// whose within-visit counter continuity is qualified.
struct HistoricalTimingProfile {
    std::uint64_t generation{};
    std::uint32_t sample_rate_hz{};
    std::uint64_t anchor_counter{};
    std::int64_t anchor_utc_ns{};
    std::uint64_t utc_bracket_width_ns{};
    std::uint64_t minimum_window_counter{};
    std::uint64_t maximum_support_end_counter{};
    std::string profile_name, profile_manifest_digest;
};
bool valid_historical_timing_profile(
    const Authority&, const HistoricalTimingProfile&) noexcept;
enum class Status { emitted, ignored, nonpassing, invalid_event, timing_unavailable };
struct PreparedProjection {
    ProjectionSource source;
    FractionalCandidate candidate;
};
// Caller binds events to their scanner invocation. The scanner v2 contract has
// no generation field: never mix callbacks from different invocations here.
// This function has no mutable state. Serialize access to the timing owner or
// pass a value-owned timing snapshot. RF comes from the explicit target map,
// never from an assumed tuner/sky frequency conversion.
Status project_event(const Authority&, const timing::Timebase&,
                     const leo_scanner_event&, Observation&);

// Bind a scanner candidate to immutable RF authority and a value-owned timing
// anchor, and validate all projection inputs without deriving support. The
// prepared value remains valid after the Timebase advances or prunes anchors.
Status prepare_event(const Authority&, const timing::Timebase&,
                     const leo_scanner_event&, PreparedProjection&);

// Historical replay uses the persisted anchor midpoint and UTC span exactly.
// No drift growth, clock-resolution padding, or synthetic Bracket is applied.
Status project_event(const Authority&, const HistoricalTimingProfile&,
                     const leo_scanner_event&, Observation&);
Status prepare_event(const Authority&, const HistoricalTimingProfile&,
                     const leo_scanner_event&, PreparedProjection&);

// Explicit session-bound support authority. The neutral port is invoked on the
// caller's thread only for a passing candidate. On emission, derivation carries
// the exact moment lexemes corresponding to the numeric Observation support.
Status project_event(const Authority&, const timing::Timebase&,
                     const leo_scanner_event&, const SupportDerivationPort&,
                     Observation&, SupportDerivation&);
}
