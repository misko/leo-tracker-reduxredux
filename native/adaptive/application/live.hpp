#pragma once

#include "session.hpp"
#include "execution.hpp"
#include "../scanner/scanner.h"
#include "../device/local/local_radio_prepare.h"

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace leo::adaptive::application::live {

struct Target {
    std::uint32_t profile{}, channel{};
    std::uint64_t frequency_hz{};
    double actual_rf_hz{};
    bool upper_edge{};
};

struct AnalysisConfig {
    ingest::Authority authority;
    timing::Config timing;
    online::Config online;
    online::SessionAuthority session;
    std::vector<leo_tle_record> catalogue;
    online::SearchConfig search;
    std::uint64_t maximum_detector_latency_ns{};
    std::uint64_t publication_interval_ns{};
    std::uint32_t search_slice_points{};
    // Explicit orbit interpolation profile. The live MVP passes 1 s / 32;
    // a longer-history profile can be assessed without changing composition.
    double orbit_knot_step_s{};
    std::uint32_t orbit_knot_count{};
    // Replay/cooperative hosts may explicitly supply the analysis owner.
    // Production defaults to its independent background thread.
    bool caller_driven{};
    // Owned tracking dispatch width. One preserves serial execution and
    // allocates no additional pool.
    std::uint32_t analysis_workers{1};
    // Optional neutral support-authority profile. All fields must be empty or
    // all fields must form one valid borrowed binding. The Session copies the
    // profile metadata; the callback/context live through Analysis destruction.
    SupportDerivationPort support_derivation{};
};

struct Summary {
    std::uint64_t scanner_candidates{}, accepted_candidates{}, rejected_candidates{};
    std::uint64_t detector_latency_violations{}, detector_failures{};
    std::uint64_t scanner_queue_drops{}, application_queue_overflows{};
    std::uint64_t invalid_candidate_events{}, timing_failures{};
    std::uint64_t publications{}, publication_empty{}, publication_failures{};
    std::uint64_t publication_deferrals{};
    std::uint64_t orbit_builds{}, searches_started{}, searches_complete{};
    std::uint64_t searches_unconverged{}, search_failures{}, snapshot_expirations{};
    std::uint64_t searches_stale{}, publications_with_tracks{};
    bool search_pending{};
    std::uint64_t watermark_deferrals{};
    std::uint64_t publication_compute_count{}, publication_compute_total_ns{};
    std::uint64_t publication_compute_max_ns{};
    std::uint64_t publication_cadence_requests{}, publication_cadence_serviced{};
    std::uint64_t publication_cadence_misses{};
    bool publication_cadence_pending{};
    std::uint64_t snapshot_source_age_count{};
    std::uint64_t snapshot_source_age_lower_current_ns{}, snapshot_source_age_lower_max_ns{};
    std::uint64_t snapshot_source_age_upper_current_ns{}, snapshot_source_age_upper_max_ns{};
    std::uint64_t result_source_age_count{};
    std::uint64_t result_source_age_lower_current_ns{}, result_source_age_lower_max_ns{};
    std::uint64_t result_source_age_upper_current_ns{}, result_source_age_upper_max_ns{};
    std::uint64_t snapshot_result_duration_count{}, snapshot_result_duration_current_ns{};
    std::uint64_t snapshot_result_duration_max_ns{};
    std::uint64_t orbit_generation{}, snapshot_generation{};
    std::int64_t causal_watermark_utc_ns{};
    // Measured source progress is the lower UTC endpoint of the latest clock
    // bracket. Causal frontier subtracts declared detector lateness. Neither is
    // host-arrival time.
    std::int64_t latest_measured_source_progress_utc_before_ns{};
    std::int64_t latest_measured_source_progress_utc_after_ns{};
    std::int64_t latest_causal_frontier_utc_ns{};
    std::int64_t last_snapshot_watermark_utc_ns{};
    std::int64_t last_result_snapshot_watermark_utc_ns{};
    std::uint64_t publication_lag_current_ns{}, publication_lag_max_ns{};
    bool timing_qualified{true};
    bool support_profile_bound{};
    SupportProfileBinding support_profile;
    online::SearchResult last_search;
    // Copied by the single analysis owner before Summary publication.
    online::ExactScoreCacheStats exact_score_cache;
    application::Stats session;
};

class Analysis {
public:
    explicit Analysis(AnalysisConfig);
    ~Analysis();
    Analysis(const Analysis&) = delete;
    Analysis& operator=(const Analysis&) = delete;

    timing::Status observe(const timing::Bracket&);
    void event(const leo_scanner_event&);
    void set_cancel(void* context, int (*cancel)(void*));
    // Waits for an in-flight callback and prevents future cancellation calls.
    void detach_cancel();
    // Last completed analysis iteration; safe to read from the control thread.
    Summary progress() const;
    // Caller-driven mode only. One analysis iteration with the configured
    // search point allowance. poll() and finish() must not overlap.
    Summary poll();
    // Call only after scanner return and radio close/deactivate/restore/release.
    // Performs one final analysis iteration; a budgeted search may remain
    // unconverged or pending, which the returned summary reports explicitly.
    Summary finish_after_rf_stopped();
    // Available only after finish_after_rf_stopped returns successfully.
    // Returns the latest immutable publication (possibly null), which may be
    // newer than a pinned search result. Does not publish or run analysis.
    std::shared_ptr<const online::Snapshot> final_published_snapshot() const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

// Application-private injection boundary. Production passes the two local-IIO
// providers; tests pass deterministic providers through the identical cleanup
// and ownership path. No provider is touched by the no-argument capability run.
int run_cli_with_providers(int argc,char** argv,
    const leo_local_provider_ops*,const leo_local_radio_prepare_ops*);

// Explicit profiled companion boundary. The existing portable entry remains
// schema v4 and never links a concrete support implementation. This overload
// emits the separate generic profiled v1 contracts and borrows the port for the
// entire blocking call.
int run_cli_with_providers_and_support(int argc,char** argv,
    const leo_local_provider_ops*,const leo_local_radio_prepare_ops*,
    const SupportDerivationPort&);

} // namespace leo::adaptive::application::live
