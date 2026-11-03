#pragma once

#include <cstdint>
#include <cstddef>
#include <memory>
#include <string>
#include <vector>

namespace leo::adaptive::tracking {

struct Candidate {
    std::string candidate_id;
    std::string source_group_id;
    int receiver_id{};
    int channel{};
    std::string edge;
    double actual_rf_hz{};
    std::int64_t support_start_utc_ns{};
    std::int64_t support_center_utc_ns{};
    std::int64_t support_end_utc_ns{};
    double measured_cfo_hz{};
    double exact_score{};
    double control_score{};
    double margin{};
};

struct Config {
    double canonical_rf_hz{11'200'000'000.0};
    double alias_spacing_hz{1.0 / 4.4e-6};
    double minimum_slope_hz_per_s{-15'000.0};
    double maximum_slope_hz_per_s{15'000.0};
    double residual_gate_hz{2'500.0};
    double maximum_gap_s{4.0};
    double minimum_span_s{3.0};
    std::size_t minimum_support{6};
    double minimum_point_weight{0.1};
    std::size_t slope_bins{3'601};
    std::size_t intercept_bins{512};
    std::size_t peak_candidates{64};
    std::size_t maximum_tracks_per_lane{8};
    std::size_t maximum_input_points{40'000};
    std::size_t maximum_candidates_per_source_group{16};
    std::size_t maximum_trajectory_hypotheses{16};
    double cross_lane_minimum_overlap_s{8.0};
    double cross_lane_rate_gate_hz_per_s{250.0};
};

struct Lane {
    int channel{};
    std::string edge;
    int receiver_id{};
    double actual_rf_hz{};
};

struct TrackPoint {
    std::string candidate_id;
    std::string source_group_id;
    int relative_alias_index{};
    double normalized_raw_cfo_hz{};
    double normalized_dealiased_cfo_hz{};
};

struct Track {
    std::string segment_id;
    std::string tracklet_id;
    Lane lane;
    std::int64_t start_utc_ns{};
    std::int64_t end_utc_ns{};
    std::int64_t reference_utc_ns{};
    double normalized_rate_hz_per_s{};
    double normalized_intercept_hz{};
    double residual_rms_hz{};
    double residual_max_hz{};
    double weighted_support{};
    std::vector<TrackPoint> points;
};

struct Result {
    std::vector<Track> tracks;
    std::size_t input_candidate_count{};
    std::size_t used_candidate_count{};
    std::string config_digest;
};

Result reconstruct(const std::vector<Candidate>& candidates, const Config& config = Config{});

/* Borrowed synchronous execution port. A null run selects the serial path.
 * Otherwise run must invoke task(task_context, index) exactly once for every
 * index in [0,count), and finish all callbacks before returning or throwing.
 * Callbacks may run concurrently; the caller owns workers and their CPU/memory
 * budget. No execution state is retained by reconstruction. */
struct LaneExecution {
    void* context{};
    void (*run)(void* context, std::size_t count, void* task_context,
                void (*task)(void*, std::size_t)){};
};

Result reconstruct(const std::vector<Candidate>& candidates, const Config& config,
                   const LaneExecution& execution);

struct ReconstructorStats {
    std::size_t maximum_cache_bytes{};
    /* Conservative retained allocation accounting, including vector capacities
     * and candidate string capacities. This is not whole-process RSS. */
    std::size_t resident_cache_bytes{};
    std::size_t cached_lanes{};
    std::size_t last_reused_lanes{};
    std::size_t last_extended_lanes{};
    std::size_t last_bin_cells_computed{};
    bool last_cold_fallback{};
    std::uint64_t cold_starts{};
    std::uint64_t prefix_invalidations{};
    std::uint64_t config_invalidations{};
    std::uint64_t capacity_fallbacks{};
};

/* Single-owner persistent exact-prefix accelerator. The stateless reconstruct
 * function remains the cold oracle. Cache reuse never changes histogram
 * accumulation order and falls back cold on any unverifiable prefix. */
class Reconstructor {
public:
    explicit Reconstructor(std::size_t maximum_cache_bytes =
        96U * 1024U * 1024U);
    ~Reconstructor();
    Reconstructor(Reconstructor&&) noexcept;
    Reconstructor& operator=(Reconstructor&&) noexcept;
    Reconstructor(const Reconstructor&) = delete;
    Reconstructor& operator=(const Reconstructor&) = delete;

    Result reconstruct(const std::vector<Candidate>& candidates,
        const Config& config = Config{});
    Result reconstruct(const std::vector<Candidate>& candidates,
        const Config& config, const LaneExecution& execution);
    void clear();
    ReconstructorStats stats() const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace leo::adaptive::tracking
