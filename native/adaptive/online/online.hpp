#pragma once

#include "location.h"
#include "pipeline.hpp"
#include "projection.hpp"
#include "tracking.hpp"

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace leo::adaptive::online {

enum class Status {
    ok,
    invalid,
    future_observation,
    stale_generation,
    duplicate,
    capacity,
    no_observations,
    no_tracks,
    no_orbit,
    running_unconverged,
    complete,
    cancelled,
    stale,
    error,
};

enum class PublicationSearchPolicy {
    invalidate_on_publish,
    pin_started_snapshot,
};

/* Borrowed synchronous score dispatcher. One worker with a null run callback
 * retains the serial path. For two through four workers, run must invoke task
 * exactly once for every index in [0,workers) and finish all callbacks before
 * returning or throwing. The caller owns the dispatcher and keeps its context
 * alive through every synchronous resume_search call. */
struct ScoringExecution {
    std::uint32_t workers{1};
    void* context{};
    void (*run)(void* context, std::size_t count, void* task_context,
                void (*task)(void*, std::size_t)){};
};

struct Config {
    std::size_t maximum_history_observations{40'000};
    std::int64_t history_window_ns{600'000'000'000LL};
    std::size_t maximum_tracks{128};
    std::uint32_t maximum_satellites{4'096};
    std::uint32_t maximum_knots{256};
    std::size_t maximum_orbit_bytes{128U * 1024U * 1024U};
    std::uint32_t maximum_search_points{10'000};
    std::uint32_t maximum_observations_per_track{100'000};
    tracking::Config tracking{};
    PublicationSearchPolicy publication_search_policy{
        PublicationSearchPolicy::invalidate_on_publish};
    /* Borrowed dispatcher; its context must outlive this coordinator and every
     * synchronous publish call. Null retains serial tracking. */
    tracking::LaneExecution tracking_execution{};
    ScoringExecution scoring_execution{};
    /* Zero disables exact per-track score reuse. A nonzero value bounds the
     * retained cache payload (vector/string capacities; allocator metadata is
     * excluded). Cache pressure falls back to the ordinary cold scorer. */
    std::size_t maximum_exact_score_cache_bytes{};
};

struct ExactScoreCacheStats {
    bool enabled{};
    std::size_t retained_payload_bytes{};
    std::size_t retained_sites{};
    std::uint64_t track_hits{};
    std::uint64_t track_misses{};
    std::uint64_t site_insertions{};
    std::uint64_t site_evictions{};
    std::uint64_t cold_fallback_points{};
};

struct SessionAuthority {
    std::string session_id;
    std::string input_manifest_digest;
    std::int64_t session_start_utc_ns{};
};

struct IngestReceipt {
    Status status{Status::invalid};
    std::size_t retained_observations{};
    std::size_t pruned_observations{};
};

struct OrbitBuild {
    std::uint64_t generation{};
    std::int64_t start_utc_ns{};
    double knot_start_s{};
    double knot_step_s{};
    std::uint32_t knot_count{};
    std::vector<leo_tle_record> records;
};

struct SearchConfig {
    double origin_latitude_deg{};
    double origin_longitude_deg{};
    leo_search_policy policy{};
    leo_score_config score{};
};

enum class SearchState {
    idle,
    running_unconverged,
    complete,
    cancelled,
    stale,
    error,
};

struct SearchResult {
    SearchState state{SearchState::idle};
    Status status{Status::ok};
    std::uint64_t search_generation{};
    std::uint64_t snapshot_generation{};
    std::uint64_t orbit_generation{};
    std::uint32_t evaluated_points{};
    std::uint32_t deferred_cells{};
    std::uint32_t required_points{};
    bool has_incumbent{};
    leo_search_evaluation incumbent{};
    double incumbent_residual_rmse_hz{};
    std::uint32_t incumbent_matched_tracks{};
    std::uint32_t incumbent_unmatched_tracks{};
    std::uint64_t incumbent_evaluated_satellite_tracks{};
    std::uint64_t incumbent_rejected_satellite_tracks{};
};

struct Snapshot {
    std::uint64_t generation{};
    std::uint64_t stream_generation{};
    std::int64_t watermark_utc_ns{};
    std::size_t retained_observation_count{};
    tracking::Result tracking_result;
    pipeline::LocationTrackBatch location_tracks;

    Snapshot() = default;
    Snapshot(const Snapshot&) = delete;
    Snapshot& operator=(const Snapshot&) = delete;
};

struct ReferenceComparison {
    bool exact{};
    std::size_t expected_tracks{};
    std::size_t actual_tracks{};
    std::size_t mismatched_tracks{};
    std::size_t mismatched_points{};
};

/* Produces the response-free support authority used by the online pipeline.
 * moment0 and moment1 are fixed by the normalized fractional-support contract;
 * no winner, mask, or location response is read or inferred. */
pipeline::SupportAuthority derive_support_authority(const Observation& observation);

/* Pure diagnostic comparison. It never mutates a coordinator or contributes
 * evidence to reconstruction, partitioning, scoring, or search. */
ReferenceComparison compare_reference(
    const Snapshot& actual,
    const tracking::Result& expected);

class Coordinator {
public:
    Coordinator(Config config, SessionAuthority authority);
    ~Coordinator();
    Coordinator(const Coordinator&) = delete;
    Coordinator& operator=(const Coordinator&) = delete;
    Coordinator(Coordinator&&) noexcept;
    Coordinator& operator=(Coordinator&&) noexcept;

    Status replace_stream_generation(std::uint64_t generation);
    IngestReceipt ingest(
        const Observation& observation,
        std::int64_t causal_watermark_utc_ns);
    IngestReceipt ingest(
        const Observation& observation,
        const pipeline::SupportAuthority& support,
        std::int64_t causal_watermark_utc_ns);
    Status advance_watermark(std::int64_t causal_watermark_utc_ns);

    /* Publication is an explicit cadence boundary. Appends after publication
     * do not invalidate a search over that immutable prefix. By default, a
     * later successful publication does. pin_started_snapshot keeps an active
     * search on its immutable prefix while current_snapshot() advances. The
     * watermark may not exceed the latest causal ingress watermark, and
     * observations ending after it are never included. */
    Status publish(
        std::int64_t watermark_utc_ns,
        std::shared_ptr<const Snapshot>* snapshot);
    std::shared_ptr<const Snapshot> current_snapshot() const;

    Status replace_orbit(const OrbitBuild& build);
    Status begin_search(
        std::uint64_t snapshot_generation,
        const SearchConfig& config,
        SearchResult* result);
    /* In pin_started_snapshot mode a native deterministic batch may be scored
     * over several calls without exceeding maximum_points in any call. The
     * batch is submitted in its original order only when complete. Default
     * mode preserves the whole-native-batch requirement. */
    SearchResult resume_search(std::uint32_t maximum_points);
    SearchResult cancel_search();

    std::size_t retained_observations() const;
    // Evidence removed by the count limit while still inside the time window.
    // Resets on stream-generation replacement; ordinary expiry is excluded.
    std::uint64_t history_capacity_evictions() const;
    std::int64_t causal_watermark_utc_ns() const;
    ExactScoreCacheStats exact_score_cache_stats() const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace leo::adaptive::online
