#ifndef LEO_ADAPTIVE_LOCATION_H
#define LEO_ADAPTIVE_LOCATION_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LEO_LOCATION_ABI_VERSION 1u
#define LEO_LOCATION_MAX_LEVELS 8u

typedef enum leo_location_status {
    LEO_LOCATION_OK = 0,
    LEO_LOCATION_DONE = 1,
    LEO_LOCATION_CANCELLED = 2,
    LEO_LOCATION_INVALID = -1,
    LEO_LOCATION_CAPACITY = -2,
    LEO_LOCATION_ORBIT_ERROR = -3,
    LEO_LOCATION_STALE = -4,
    LEO_LOCATION_STATE = -5
} leo_location_status;

typedef struct leo_tle_record {
    int32_t satellite_id;
    char line1[70];
    char line2[70];
} leo_tle_record;

typedef struct leo_orbit_state {
    double position_km[3];
    double velocity_km_s[3];
} leo_orbit_state;

/* Context-owned immutable view. It remains valid until the next successful
 * build on the same context or context destruction. States are satellite-major. */
typedef struct leo_orbit_snapshot {
    uint64_t generation;
    int64_t start_utc_ns;
    double knot_start_s;
    double knot_step_s;
    uint32_t satellite_count;
    uint32_t knot_count;
    const int32_t *satellite_ids;
    const leo_orbit_state *states;
} leo_orbit_snapshot;

typedef struct leo_orbit_context leo_orbit_context;

leo_orbit_context *leo_orbit_context_create(uint32_t max_satellites, uint32_t max_knots);
void leo_orbit_context_destroy(leo_orbit_context *context);
leo_location_status leo_orbit_build_tle(
    leo_orbit_context *context,
    uint64_t generation,
    int64_t start_utc_ns,
    double knot_start_s,
    double knot_step_s,
    uint32_t knot_count,
    const leo_tle_record *records,
    uint32_t satellite_count,
    leo_orbit_snapshot *snapshot);
leo_location_status leo_orbit_interpolate(
    const leo_orbit_snapshot *snapshot,
    uint32_t satellite_index,
    double relative_time_s,
    leo_orbit_state *state);

typedef struct leo_location_site {
    double ecef_km[3];
    double up[3];
} leo_location_site;

typedef struct leo_location_track {
    uint64_t track_key;
    uint32_t observation_count;
    uint32_t weight_s;
    const double *times_s;
    const double *measured_hz;
    const uint8_t *training_mask;
} leo_location_track;

typedef struct leo_score_config {
    double carrier_hz;
    double speed_of_light_km_s;
    double unmatched_penalty_hz;
    int32_t tau_first_s;
    int32_t tau_last_s;
    int32_t tau_step_s;
} leo_score_config;

typedef struct leo_track_score {
    uint8_t matched;
    int32_t candidate_id;
    int32_t tau_s;
    double heldout_rms_hz;
    double training_rms_hz;
    double frequency_offset_hz;
} leo_track_score;

typedef struct leo_point_score {
    double weighted_mse_hz2;
    double residual_rmse_hz;
    uint32_t matched_track_count;
    uint32_t unmatched_track_count;
} leo_point_score;

typedef struct leo_score_stats {
    uint64_t rejected_satellite_tracks;
    uint64_t evaluated_satellite_tracks;
} leo_score_stats;

typedef struct leo_score_context leo_score_context;

leo_score_context *leo_score_context_create(uint32_t max_observations, uint32_t max_taus);
void leo_score_context_destroy(leo_score_context *context);
leo_score_config leo_score_default_config(void);
leo_location_status leo_score_validate_inputs(
    const leo_orbit_snapshot *snapshot,
    const leo_location_track *tracks,
    uint32_t track_count,
    const leo_location_site *site,
    const leo_score_config *config);
void leo_track_scores_clear(leo_track_score *scores, uint32_t track_count);
leo_location_status leo_score_partition(
    leo_score_context *context,
    const leo_orbit_snapshot *snapshot,
    const leo_location_track *tracks,
    uint32_t track_count,
    const leo_location_site *site,
    const leo_score_config *config,
    uint32_t satellite_begin,
    uint32_t satellite_end,
    leo_track_score *scores,
    leo_score_stats *stats);
leo_location_status leo_track_scores_reduce(
    leo_track_score *destination,
    const leo_track_score *source,
    uint32_t track_count);
leo_location_status leo_point_score_finish(
    const leo_location_track *tracks,
    uint32_t track_count,
    const leo_track_score *scores,
    const leo_score_config *config,
    leo_point_score *point_score);

typedef struct leo_search_policy {
    double radius_km;
    double region_size_km;
    uint32_t level_count;
    double levels_km[LEO_LOCATION_MAX_LEVELS];
    uint32_t budget_points;
} leo_search_policy;

typedef struct leo_search_point {
    double east_km;
    double north_km;
    double spacing_km;
    uint32_t depth;
} leo_search_point;

typedef struct leo_search_evaluation {
    double east_km;
    double north_km;
    double weighted_mse_hz2;
} leo_search_evaluation;

typedef struct leo_search_result {
    uint64_t generation;
    uint32_t evaluated_points;
    uint32_t deferred_cells;
    uint8_t complete;
    uint8_t cancelled;
    uint8_t has_incumbent;
    leo_search_evaluation incumbent;
} leo_search_result;

typedef struct leo_search_context leo_search_context;

leo_search_policy leo_search_default_policy(double radius_km);
leo_search_context *leo_search_context_create(uint32_t max_budget_points);
void leo_search_context_destroy(leo_search_context *context);
leo_location_status leo_search_begin(
    leo_search_context *context,
    uint64_t generation,
    const leo_search_policy *policy);
/* next() returns a deterministic batch for the caller to score. The context
 * may be retained between calls; submit() must receive the same generation and
 * the requested coordinates in order. */
leo_location_status leo_search_next(
    leo_search_context *context,
    uint64_t generation,
    leo_search_point *points,
    uint32_t capacity,
    uint32_t *point_count);
leo_location_status leo_search_submit(
    leo_search_context *context,
    uint64_t generation,
    const leo_search_evaluation *evaluations,
    uint32_t evaluation_count);
leo_location_status leo_search_cancel(leo_search_context *context, uint64_t generation);
leo_location_status leo_search_get_result(
    const leo_search_context *context,
    uint64_t generation,
    leo_search_result *result);

#ifdef __cplusplus
}
#endif
#endif
