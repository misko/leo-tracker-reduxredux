#include "online.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <cstdlib>
#include <exception>
#include <iomanip>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <unordered_set>
#include <utility>

namespace leo::adaptive::online {
namespace {

bool tagged_digest(const std::string& value) {
    return value.size() == 71 && value.compare(0, 7, "sha256:") == 0 &&
        value.find_first_not_of("0123456789abcdef", 7) == std::string::npos;
}

bool numeric_text(const std::string& value) {
    if (value.empty()) return false;
    errno = 0;
    char* end = nullptr;
    const double parsed = std::strtod(value.c_str(), &end);
    return errno == 0 && end == value.c_str() + value.size() && std::isfinite(parsed);
}

std::string canonical_number(double value) {
    std::ostringstream output;
    output << std::setprecision(std::numeric_limits<double>::max_digits10) << value;
    return output.str();
}

bool valid_observation(const Observation& value) {
    return tagged_digest(value.candidate_id) && tagged_digest(value.source_group_id) &&
        value.generation != 0 && value.receiver <= 1 && value.channel >= 1 && value.channel <= 4 &&
        std::isfinite(value.actual_rf_hz) && value.actual_rf_hz > 0.0 &&
        std::isfinite(value.measured_cfo_hz) && std::isfinite(value.exact_score) &&
        std::isfinite(value.control_score) && std::isfinite(value.margin) &&
        value.exact_score >= 0.0 && value.control_score >= 0.0 && value.margin > 0.0 &&
        std::abs(value.margin - (value.exact_score - value.control_score)) <=
            std::max(1.0e-12, 1.0e-12 * std::max(
                std::abs(value.margin), std::abs(value.exact_score - value.control_score))) &&
        value.support_start_utc_ns > 0 &&
        value.support_start_utc_ns <= value.support_center_utc_ns &&
        value.support_center_utc_ns < value.support_end_utc_ns &&
        std::isfinite(value.standard_uncertainty_hz) && value.standard_uncertainty_hz > 0.0 &&
        std::isfinite(value.moment2) && std::isfinite(value.moment3) && value.moment2 >= 0.0;
}

bool support_matches(
    const Observation& observation,
    const pipeline::SupportAuthority& support) {
    if (!(support.support_start_utc_ns == observation.support_start_utc_ns &&
        support.support_center_utc_ns == observation.support_center_utc_ns &&
        support.support_end_utc_ns == observation.support_end_utc_ns &&
        numeric_text(support.moment0) && numeric_text(support.moment1) &&
        numeric_text(support.moment2) && numeric_text(support.moment3))) return false;
    return std::strtod(support.moment0.c_str(), nullptr) == 1.0 &&
        std::strtod(support.moment1.c_str(), nullptr) == 0.0 &&
        std::strtod(support.moment2.c_str(), nullptr) == observation.moment2 &&
        std::strtod(support.moment3.c_str(), nullptr) == observation.moment3;
}

tracking::Candidate to_candidate(const Observation& value) {
    return tracking::Candidate{
        value.candidate_id,
        value.source_group_id,
        static_cast<int>(value.receiver),
        static_cast<int>(value.channel),
        value.upper_edge ? "upper" : "lower",
        value.actual_rf_hz,
        value.support_start_utc_ns,
        value.support_center_utc_ns,
        value.support_end_utc_ns,
        value.measured_cfo_hz,
        value.exact_score,
        value.control_score,
        value.margin,
    };
}

leo_location_site make_site(
    double origin_latitude_deg,
    double origin_longitude_deg,
    double east_km,
    double north_km) {
    constexpr double pi = 3.14159265358979323846;
    constexpr double mean_earth_radius_km = 6371.0088;
    constexpr double semi_major_axis_km = 6378.137;
    constexpr double flattening = 1.0 / 298.257223563;
    constexpr double eccentricity_squared = flattening * (2.0 - flattening);
    const double angular = std::hypot(east_km, north_km) / mean_earth_radius_km;
    const double bearing = std::atan2(east_km, north_km);
    const double latitude0 = origin_latitude_deg * pi / 180.0;
    const double longitude0 = origin_longitude_deg * pi / 180.0;
    const double latitude = std::asin(
        std::sin(latitude0) * std::cos(angular) +
        std::cos(latitude0) * std::sin(angular) * std::cos(bearing));
    const double longitude = longitude0 + std::atan2(
        std::sin(bearing) * std::sin(angular) * std::cos(latitude0),
        std::cos(angular) - std::sin(latitude0) * std::sin(latitude));
    const double prime_vertical = semi_major_axis_km /
        std::sqrt(1.0 - eccentricity_squared * std::sin(latitude) * std::sin(latitude));
    leo_location_site site{};
    site.ecef_km[0] = prime_vertical * std::cos(latitude) * std::cos(longitude);
    site.ecef_km[1] = prime_vertical * std::cos(latitude) * std::sin(longitude);
    site.ecef_km[2] = prime_vertical * (1.0 - eccentricity_squared) * std::sin(latitude);
    site.up[0] = std::cos(latitude) * std::cos(longitude);
    site.up[1] = std::cos(latitude) * std::sin(longitude);
    site.up[2] = std::sin(latitude);
    return site;
}

bool same_point(const tracking::TrackPoint& left, const tracking::TrackPoint& right) {
    return left.candidate_id == right.candidate_id &&
        left.source_group_id == right.source_group_id &&
        left.relative_alias_index == right.relative_alias_index &&
        left.normalized_raw_cfo_hz == right.normalized_raw_cfo_hz &&
        left.normalized_dealiased_cfo_hz == right.normalized_dealiased_cfo_hz;
}

bool same_track(const tracking::Track& left, const tracking::Track& right) {
    if (left.segment_id != right.segment_id || left.tracklet_id != right.tracklet_id ||
        left.lane.channel != right.lane.channel || left.lane.edge != right.lane.edge ||
        left.lane.receiver_id != right.lane.receiver_id ||
        left.lane.actual_rf_hz != right.lane.actual_rf_hz ||
        left.start_utc_ns != right.start_utc_ns || left.end_utc_ns != right.end_utc_ns ||
        left.reference_utc_ns != right.reference_utc_ns ||
        left.normalized_rate_hz_per_s != right.normalized_rate_hz_per_s ||
        left.normalized_intercept_hz != right.normalized_intercept_hz ||
        left.residual_rms_hz != right.residual_rms_hz ||
        left.residual_max_hz != right.residual_max_hz ||
        left.weighted_support != right.weighted_support ||
        left.points.size() != right.points.size()) return false;
    for (std::size_t index = 0; index < left.points.size(); ++index) {
        if (!same_point(left.points[index], right.points[index])) return false;
    }
    return true;
}

bool exact_double(double left, double right) {
    return std::memcmp(&left, &right, sizeof(left)) == 0;
}

bool exact_score_config(const leo_score_config& left, const leo_score_config& right) {
    return left.tau_first_s == right.tau_first_s && left.tau_last_s == right.tau_last_s &&
        left.tau_step_s == right.tau_step_s && exact_double(left.carrier_hz, right.carrier_hz) &&
        exact_double(left.speed_of_light_km_s, right.speed_of_light_km_s) &&
        exact_double(left.unmatched_penalty_hz, right.unmatched_penalty_hz);
}

bool exact_site(const leo_location_site& left, const leo_location_site& right) {
    for (unsigned index = 0; index < 3; ++index) {
        if (!exact_double(left.ecef_km[index], right.ecef_km[index]) ||
            !exact_double(left.up[index], right.up[index])) return false;
    }
    return true;
}

bool exact_doubles(const std::vector<double>& left, const std::vector<double>& right) {
    return left.size() == right.size() && (left.empty() ||
        std::memcmp(left.data(), right.data(), left.size() * sizeof(double)) == 0);
}

bool exact_owned_track(const pipeline::OwnedLocationTrack& left, std::uint64_t left_key,
                       std::uint32_t left_weight,
                       const pipeline::OwnedLocationTrack& right,
                       const leo_location_track& right_record) {
    return left_key == right_record.track_key && left_weight == right_record.weight_s &&
        left.times_s.size() == right_record.observation_count &&
        left.tracklet_id == right.tracklet_id && left.support_digest == right.support_digest &&
        left.partition_seed == right.partition_seed &&
        left.observation_ids == right.observation_ids &&
        exact_doubles(left.times_s, right.times_s) &&
        exact_doubles(left.measured_hz, right.measured_hz) &&
        left.training_mask == right.training_mask;
}

template <class T> bool add_bytes(std::size_t* total, T count, std::size_t width) {
    const std::size_t value = static_cast<std::size_t>(count);
    if (value > (std::numeric_limits<std::size_t>::max() - *total) / width) return false;
    *total += value * width;
    return true;
}

SearchState state_for(Status status) {
    switch (status) {
    case Status::running_unconverged: return SearchState::running_unconverged;
    case Status::complete: return SearchState::complete;
    case Status::cancelled: return SearchState::cancelled;
    case Status::stale: return SearchState::stale;
    case Status::error: return SearchState::error;
    default: return SearchState::idle;
    }
}

}  // namespace

pipeline::SupportAuthority derive_support_authority(const Observation& observation) {
    if (!valid_observation(observation)) {
        throw std::invalid_argument("invalid observation support");
    }
    return pipeline::SupportAuthority{
        observation.support_start_utc_ns,
        observation.support_center_utc_ns,
        observation.support_end_utc_ns,
        "1.0",
        "0.0",
        canonical_number(observation.moment2),
        canonical_number(observation.moment3),
    };
}

ReferenceComparison compare_reference(
    const Snapshot& actual,
    const tracking::Result& expected) {
    ReferenceComparison comparison{};
    comparison.expected_tracks = expected.tracks.size();
    comparison.actual_tracks = actual.tracking_result.tracks.size();
    const std::size_t shared = std::min(comparison.expected_tracks, comparison.actual_tracks);
    for (std::size_t index = 0; index < shared; ++index) {
        if (!same_track(actual.tracking_result.tracks[index], expected.tracks[index])) {
            ++comparison.mismatched_tracks;
            const auto& left = actual.tracking_result.tracks[index].points;
            const auto& right = expected.tracks[index].points;
            const std::size_t point_shared = std::min(left.size(), right.size());
            comparison.mismatched_points +=
                std::max(left.size(), right.size()) - point_shared;
            for (std::size_t point = 0; point < point_shared; ++point) {
                comparison.mismatched_points += !same_point(left[point], right[point]);
            }
        }
    }
    comparison.mismatched_tracks +=
        std::max(comparison.expected_tracks, comparison.actual_tracks) - shared;
    comparison.exact = actual.tracking_result.config_digest == expected.config_digest &&
        actual.tracking_result.input_candidate_count == expected.input_candidate_count &&
        actual.tracking_result.used_candidate_count == expected.used_candidate_count &&
        comparison.mismatched_tracks == 0;
    return comparison;
}

struct Coordinator::Impl {
    struct Stored {
        Observation observation;
        pipeline::SupportAuthority support;
    };

    struct CacheAuthority {
        pipeline::OwnedLocationTrack owned;
        std::uint64_t track_key{};
        std::uint32_t weight_s{};
    };
    struct CacheValue {
        leo_track_score score{};
        leo_score_stats stats{};
        bool valid{};
    };
    struct CacheSite {
        leo_location_site site{};
        std::vector<CacheValue> values;
    };
    struct CacheState {
        std::uint64_t stream_generation{};
        std::uint64_t orbit_generation{};
        leo_score_config score{};
        std::vector<CacheAuthority> authority;
        std::vector<CacheSite> sites;
        std::size_t payload_bytes{};
        bool ready{};
    };

    explicit Impl(Config value, SessionAuthority session)
        : config(std::move(value)), authority(std::move(session)) {
        if (config.maximum_history_observations == 0 ||
            config.maximum_history_observations > config.tracking.maximum_input_points ||
            config.history_window_ns <= 0 || config.maximum_tracks == 0 ||
            config.maximum_tracks > 128 || config.maximum_satellites == 0 ||
            config.maximum_satellites > 20'000 || config.maximum_knots < 2 ||
            config.maximum_knots > 2'000 || config.maximum_search_points == 0 ||
            config.maximum_search_points > 100'000 ||
            config.maximum_observations_per_track < 6 ||
            config.maximum_observations_per_track > 100'000 ||
            (config.publication_search_policy !=
                    PublicationSearchPolicy::invalidate_on_publish &&
             config.publication_search_policy !=
                    PublicationSearchPolicy::pin_started_snapshot) ||
            config.scoring_execution.workers < 1 ||
            config.scoring_execution.workers > 4 ||
            (config.scoring_execution.workers == 1 &&
                (config.scoring_execution.context || config.scoring_execution.run)) ||
            (config.scoring_execution.workers > 1 && !config.scoring_execution.run) ||
            config.maximum_exact_score_cache_bytes > 256U * 1024U * 1024U ||
            authority.session_id.empty() ||
            !tagged_digest(authority.input_manifest_digest) ||
            authority.session_start_utc_ns <= 0) {
            throw std::invalid_argument("invalid online coordinator configuration");
        }
        const std::size_t states = static_cast<std::size_t>(config.maximum_satellites) *
            config.maximum_knots;
        if (states > std::numeric_limits<std::size_t>::max() /
                (2U * sizeof(leo_orbit_state)) ||
            states * 2U * sizeof(leo_orbit_state) > config.maximum_orbit_bytes) {
            throw std::invalid_argument("orbit arena exceeds configured memory bound");
        }
        orbit.reset(leo_orbit_context_create(
            config.maximum_satellites, config.maximum_knots));
        search.reset(leo_search_context_create(config.maximum_search_points));
        scorers.reserve(config.scoring_execution.workers);
        for (std::uint32_t worker = 0;
             worker < config.scoring_execution.workers; ++worker) {
            scorers.emplace_back(leo_score_context_create(
                config.maximum_observations_per_track, 1024));
        }
        score_partials.resize(config.scoring_execution.workers);
        cache_stats_partials.resize(config.scoring_execution.workers);
        cache_stats.enabled = config.maximum_exact_score_cache_bytes != 0;
        if (!orbit || !search ||
            std::any_of(scorers.begin(), scorers.end(),
                [](const auto& scorer) { return !scorer; })) throw std::bad_alloc();
    }

    static std::size_t cache_payload(const CacheState& state) {
        std::size_t total = state.authority.capacity() * sizeof(CacheAuthority) +
            state.sites.capacity() * sizeof(CacheSite);
        for (const auto& item : state.authority) {
            const auto& owned = item.owned;
            if (!add_bytes(&total, owned.tracklet_id.capacity(), sizeof(char)) ||
                !add_bytes(&total, owned.support_digest.capacity(), sizeof(char)) ||
                !add_bytes(&total, owned.partition_seed.capacity(), sizeof(char)) ||
                !add_bytes(&total, owned.times_s.capacity(), sizeof(double)) ||
                !add_bytes(&total, owned.measured_hz.capacity(), sizeof(double)) ||
                !add_bytes(&total, owned.training_mask.capacity(), sizeof(std::uint8_t)) ||
                !add_bytes(&total, owned.observation_ids.capacity(), sizeof(std::string)))
                return std::numeric_limits<std::size_t>::max();
            for (const auto& identity : owned.observation_ids)
                if (!add_bytes(&total, identity.capacity(), sizeof(char)))
                    return std::numeric_limits<std::size_t>::max();
        }
        for (const auto& site : state.sites)
            if (!add_bytes(&total, site.values.capacity(), sizeof(CacheValue)))
                return std::numeric_limits<std::size_t>::max();
        return total;
    }

    static std::size_t projected_authority_payload(const Snapshot& snapshot) {
        std::size_t total = 0;
        if (!add_bytes(&total, snapshot.location_tracks.owned.size(), sizeof(CacheAuthority)))
            return std::numeric_limits<std::size_t>::max();
        for (const auto& owned : snapshot.location_tracks.owned) {
            if (!add_bytes(&total, std::max<std::size_t>(owned.tracklet_id.size(), 15), sizeof(char)) ||
                !add_bytes(&total, std::max<std::size_t>(owned.support_digest.size(), 15), sizeof(char)) ||
                !add_bytes(&total, std::max<std::size_t>(owned.partition_seed.size(), 15), sizeof(char)) ||
                !add_bytes(&total, owned.times_s.size(), sizeof(double)) ||
                !add_bytes(&total, owned.measured_hz.size(), sizeof(double)) ||
                !add_bytes(&total, owned.training_mask.size(), sizeof(std::uint8_t)) ||
                !add_bytes(&total, owned.observation_ids.size(), sizeof(std::string)))
                return std::numeric_limits<std::size_t>::max();
            for (const auto& identity : owned.observation_ids)
                if (!add_bytes(&total, std::max<std::size_t>(identity.size(), 15), sizeof(char)))
                    return std::numeric_limits<std::size_t>::max();
        }
        return total;
    }

    void clear_cache() {
        cache = CacheState{};
        cache_stats.retained_payload_bytes = 0;
        cache_stats.retained_sites = 0;
    }

    bool prepare_cache(const std::shared_ptr<const Snapshot>& snapshot,
                       const leo_score_config& score) {
        if (config.maximum_exact_score_cache_bytes == 0) return false;
        try {
            const bool same_scope = cache.ready &&
                cache.stream_generation == snapshot->stream_generation &&
                cache.orbit_generation == orbit_generation &&
                exact_score_config(cache.score, score);
            if (cache.ready && !same_scope) clear_cache();
            const std::size_t authority_projection = projected_authority_payload(*snapshot);
            const std::size_t minimum_site = sizeof(CacheSite) +
                snapshot->location_tracks.owned.size() * sizeof(CacheValue);
            if (authority_projection == std::numeric_limits<std::size_t>::max() ||
                minimum_site == 0 || cache.payload_bytes >=
                    config.maximum_exact_score_cache_bytes ||
                authority_projection >= config.maximum_exact_score_cache_bytes-
                    cache.payload_bytes)
                return false;
            const std::size_t maximum_sites = std::min<std::size_t>(
                (config.maximum_exact_score_cache_bytes-cache.payload_bytes-
                    authority_projection)/minimum_site,
                config.maximum_search_points);
            if (maximum_sites == 0) return false;
            CacheState next;
            next.stream_generation = snapshot->stream_generation;
            next.orbit_generation = orbit_generation;
            next.score = score;
            next.authority.reserve(snapshot->location_tracks.owned.size());
            for (std::size_t index = 0; index < snapshot->location_tracks.owned.size(); ++index) {
                next.authority.push_back(CacheAuthority{
                    snapshot->location_tracks.owned[index],
                    snapshot->location_tracks.records[index].track_key,
                    snapshot->location_tracks.records[index].weight_s});
            }
            const bool compatible = cache.ready && same_scope;
            next.payload_bytes = cache_payload(next);
            if (next.payload_bytes == std::numeric_limits<std::size_t>::max() ||
                next.payload_bytes >= config.maximum_exact_score_cache_bytes)
                return false;
            next.sites.reserve(maximum_sites);
            next.payload_bytes = cache_payload(next);
            if (next.payload_bytes > config.maximum_exact_score_cache_bytes ||
                cache.payload_bytes > config.maximum_exact_score_cache_bytes-next.payload_bytes)
                return false;
            if (compatible) {
                for (const auto& old_site : cache.sites) {
                    const std::size_t value_bytes =
                        next.authority.size() * sizeof(CacheValue);
                    if (next.sites.size() >= maximum_sites ||
                        value_bytes > config.maximum_exact_score_cache_bytes-
                            cache.payload_bytes-next.payload_bytes)
                        break;
                    CacheSite migrated;
                    migrated.site = old_site.site;
                    migrated.values.resize(next.authority.size());
                    for (std::size_t right = 0; right < next.authority.size(); ++right) {
                        const auto& record = snapshot->location_tracks.records[right];
                        for (std::size_t left = 0; left < cache.authority.size(); ++left) {
                            if (left < old_site.values.size() && old_site.values[left].valid &&
                                exact_owned_track(cache.authority[left].owned,
                                    cache.authority[left].track_key,
                                    cache.authority[left].weight_s,
                                    next.authority[right].owned, record)) {
                                migrated.values[right] = old_site.values[left];
                                break;
                            }
                        }
                    }
                    next.sites.push_back(std::move(migrated));
                    next.payload_bytes = cache_payload(next);
                    if (next.payload_bytes > config.maximum_exact_score_cache_bytes ||
                        cache.payload_bytes >
                            config.maximum_exact_score_cache_bytes-next.payload_bytes) {
                        next.sites.pop_back();
                        break;
                    }
                }
            }
            next.ready = true;
            next.payload_bytes = cache_payload(next);
            cache = std::move(next);
            cache_stats.retained_payload_bytes = cache.payload_bytes;
            cache_stats.retained_sites = cache.sites.size();
            return true;
        } catch (...) { return false; }
    }

    struct OrbitDeleter {
        void operator()(leo_orbit_context* value) const { leo_orbit_context_destroy(value); }
    };
    struct SearchDeleter {
        void operator()(leo_search_context* value) const { leo_search_context_destroy(value); }
    };
    struct ScoreDeleter {
        void operator()(leo_score_context* value) const { leo_score_context_destroy(value); }
    };

    void clear_search_inputs() {
        cache_search_enabled = false;
        search_snapshot.reset();
        pending_search_points.clear();
        pending_search_evaluations.clear();
        score_scratch.clear();
        for (auto& partial : score_partials) partial.clear();
        for (auto& partial : cache_stats_partials) partial.clear();
    }

    void invalidate_search() {
        if (search_active) {
            (void)leo_search_cancel(search.get(), search_generation);
            last_search.state = SearchState::stale;
            last_search.status = Status::stale;
            search_active = false;
        }
        clear_search_inputs();
    }

    std::size_t prune(std::int64_t watermark) {
        const std::int64_t cutoff = watermark > config.history_window_ns
            ? watermark - config.history_window_ns : 0;
        std::size_t removed = 0;
        while (!history.empty() && history.begin()->first.first < cutoff) {
            identities.erase(history.begin()->second.observation.candidate_id);
            history.erase(history.begin());
            ++removed;
        }
        while (history.size() > config.maximum_history_observations) {
            identities.erase(history.begin()->second.observation.candidate_id);
            history.erase(history.begin());
            ++removed;
            ++history_capacity_evictions;
        }
        return removed;
    }

    bool snapshot_expired(const std::shared_ptr<const Snapshot>& snapshot) const {
        return snapshot && causal_watermark > snapshot->watermark_utc_ns &&
            causal_watermark > config.history_window_ns &&
            snapshot->watermark_utc_ns < causal_watermark - config.history_window_ns;
    }

    void expire_snapshot_if_needed() {
        if (search_active && snapshot_expired(search_snapshot)) invalidate_search();
        if (snapshot_expired(current)) current.reset();
    }

    SearchResult result(Status status) {
        last_search.status = status;
        last_search.state = state_for(status);
        if (search_generation != 0 && status != Status::stale) {
            leo_search_result native{};
            if (leo_search_get_result(search.get(), search_generation, &native) == LEO_LOCATION_OK) {
                last_search.evaluated_points = native.evaluated_points +
                    static_cast<std::uint32_t>(pending_search_evaluations.size());
                last_search.deferred_cells = native.deferred_cells;
            }
        }
        return last_search;
    }

    SearchResult finish_result(Status status) {
        SearchResult finished = result(status);
        clear_search_inputs();
        return finished;
    }

    Status finish_evaluation(const leo_search_point& point, const std::vector<leo_location_track>& records,
                             const leo_score_stats& score_stats,
                             leo_search_evaluation* evaluation) {
        leo_point_score score{};
        if (leo_point_score_finish(records.data(), static_cast<std::uint32_t>(records.size()),
                score_scratch.data(), &search_config.score, &score) != LEO_LOCATION_OK)
            return Status::error;
        *evaluation = {point.east_km, point.north_km, score.weighted_mse_hz2};
        const auto& incumbent = last_search.incumbent;
        if (!last_search.has_incumbent ||
            evaluation->weighted_mse_hz2 < incumbent.weighted_mse_hz2 ||
            (evaluation->weighted_mse_hz2 == incumbent.weighted_mse_hz2 &&
             (evaluation->east_km < incumbent.east_km ||
              (evaluation->east_km == incumbent.east_km &&
               evaluation->north_km < incumbent.north_km)))) {
            last_search.has_incumbent = true;
            last_search.incumbent = *evaluation;
            last_search.incumbent_residual_rmse_hz = score.residual_rmse_hz;
            last_search.incumbent_matched_tracks = score.matched_track_count;
            last_search.incumbent_unmatched_tracks = score.unmatched_track_count;
            last_search.incumbent_evaluated_satellite_tracks =
                score_stats.evaluated_satellite_tracks;
            last_search.incumbent_rejected_satellite_tracks =
                score_stats.rejected_satellite_tracks;
        }
        return Status::ok;
    }

    Status evaluate_point_cached(const leo_search_point& point,
                                 const leo_location_site& site,
                                 leo_search_evaluation* evaluation) {
        const auto& records = search_snapshot->location_tracks.records;
        const std::uint32_t track_count = static_cast<std::uint32_t>(records.size());
        auto found = std::find_if(cache.sites.begin(), cache.sites.end(),
            [&](const CacheSite& value) { return exact_site(value.site, site); });
        std::vector<CacheValue> values(track_count);
        if (found != cache.sites.end()) values = found->values;
        std::vector<std::uint32_t> misses;
        misses.reserve(track_count);
        for (std::uint32_t index = 0; index < track_count; ++index) {
            if (values[index].valid) score_scratch[index] = values[index].score;
            else misses.push_back(index);
        }
        const std::uint32_t workers = config.scoring_execution.workers;
        if (!misses.empty()) {
            if (workers == 1) {
                for (const auto index : misses) {
                    leo_track_scores_clear(&score_scratch[index], 1);
                    leo_score_stats stats{};
                    if (leo_score_partition(scorers[0].get(), &orbit_snapshot, &records[index], 1,
                            &site, &search_config.score, 0, orbit_snapshot.satellite_count,
                            &score_scratch[index], &stats) != LEO_LOCATION_OK)
                        return Status::error;
                    values[index] = CacheValue{score_scratch[index], stats, true};
                }
            } else {
                std::array<leo_location_status, 4> statuses{};
                std::array<std::atomic<unsigned char>, 4> claimed{};
                std::array<unsigned char, 4> finished{};
                for (std::uint32_t worker = 0; worker < workers; ++worker) {
                    statuses[worker] = LEO_LOCATION_OK;
                    claimed[worker].store(0, std::memory_order_relaxed);
                }
                std::atomic<bool> invalid_index{false};
                struct Batch {
                    Impl& owner;
                    const std::vector<leo_location_track>& records;
                    const leo_location_site& site;
                    const std::vector<std::uint32_t>& misses;
                    std::array<leo_location_status, 4>& statuses;
                    std::array<std::atomic<unsigned char>, 4>& claimed;
                    std::array<unsigned char, 4>& finished;
                    std::atomic<bool>& invalid_index;
                    std::uint32_t workers;
                } batch{*this, records, site, misses, statuses, claimed, finished,
                        invalid_index, workers};
                try {
                    config.scoring_execution.run(config.scoring_execution.context, workers, &batch,
                        [](void* opaque, std::size_t raw) {
                            auto& state = *static_cast<Batch*>(opaque);
                            if (raw >= state.workers ||
                                state.claimed[raw].exchange(1, std::memory_order_relaxed)) {
                                state.invalid_index.store(true, std::memory_order_relaxed);
                                return;
                            }
                            const auto worker = static_cast<std::uint32_t>(raw);
                            const std::uint32_t satellites = state.owner.orbit_snapshot.satellite_count;
                            const std::uint32_t begin = static_cast<std::uint32_t>(
                                static_cast<std::uint64_t>(satellites) * worker / state.workers);
                            const std::uint32_t end = static_cast<std::uint32_t>(
                                static_cast<std::uint64_t>(satellites) * (worker + 1U) /
                                state.workers);
                            for (const auto index : state.misses) {
                                leo_track_scores_clear(
                                    &state.owner.score_partials[worker][index], 1);
                                state.owner.cache_stats_partials[worker][index] = {};
                                state.statuses[worker] = leo_score_partition(
                                    state.owner.scorers[worker].get(),
                                    &state.owner.orbit_snapshot, &state.records[index], 1,
                                    &state.site, &state.owner.search_config.score, begin, end,
                                    &state.owner.score_partials[worker][index],
                                    &state.owner.cache_stats_partials[worker][index]);
                                if (state.statuses[worker] != LEO_LOCATION_OK) break;
                            }
                            state.finished[worker] = 1;
                        });
                } catch (...) { return Status::error; }
                if (invalid_index.load(std::memory_order_relaxed)) return Status::error;
                for (std::uint32_t worker = 0; worker < workers; ++worker)
                    if (!finished[worker] || statuses[worker] != LEO_LOCATION_OK)
                        return Status::error;
                for (const auto index : misses) {
                    score_scratch[index] = score_partials[0][index];
                    leo_score_stats stats = cache_stats_partials[0][index];
                    for (std::uint32_t worker = 1; worker < workers; ++worker) {
                        const auto& part = cache_stats_partials[worker][index];
                        if (UINT64_MAX - stats.rejected_satellite_tracks <
                                part.rejected_satellite_tracks ||
                            UINT64_MAX - stats.evaluated_satellite_tracks <
                                part.evaluated_satellite_tracks ||
                            leo_track_scores_reduce(&score_scratch[index],
                                &score_partials[worker][index], 1) != LEO_LOCATION_OK)
                            return Status::error;
                        stats.rejected_satellite_tracks += part.rejected_satellite_tracks;
                        stats.evaluated_satellite_tracks += part.evaluated_satellite_tracks;
                    }
                    values[index] = CacheValue{score_scratch[index], stats, true};
                }
            }
        }
        leo_score_stats total{};
        for (const auto& value : values) {
            if (!value.valid || UINT64_MAX - total.rejected_satellite_tracks <
                    value.stats.rejected_satellite_tracks ||
                UINT64_MAX - total.evaluated_satellite_tracks <
                    value.stats.evaluated_satellite_tracks) return Status::error;
            total.rejected_satellite_tracks += value.stats.rejected_satellite_tracks;
            total.evaluated_satellite_tracks += value.stats.evaluated_satellite_tracks;
        }
        if (finish_evaluation(point, records, total, evaluation) != Status::ok)
            return Status::error;
        cache_stats.track_hits += track_count - misses.size();
        cache_stats.track_misses += misses.size();
        if (found != cache.sites.end()) {
            found->values = std::move(values);
        } else {
            while (cache.sites.size() >= cache.sites.capacity() && !cache.sites.empty()) {
                cache.sites.erase(cache.sites.begin());
                ++cache_stats.site_evictions;
            }
            if (cache.sites.size() < cache.sites.capacity()) {
                cache.sites.push_back(CacheSite{site, std::move(values)});
                ++cache_stats.site_insertions;
                cache.payload_bytes = cache_payload(cache);
                while (cache.payload_bytes > config.maximum_exact_score_cache_bytes &&
                       !cache.sites.empty()) {
                    cache.sites.erase(cache.sites.begin());
                    ++cache_stats.site_evictions;
                    cache.payload_bytes = cache_payload(cache);
                }
            }
        }
        cache.payload_bytes = cache_payload(cache);
        cache_stats.retained_payload_bytes = cache.payload_bytes;
        cache_stats.retained_sites = cache.sites.size();
        return Status::ok;
    }

    Status evaluate_point(const leo_search_point& point, leo_search_evaluation* evaluation) {
        if (!evaluation || !search_snapshot) return Status::error;
        const auto& records = search_snapshot->location_tracks.records;
        const leo_location_site site = make_site(
            search_config.origin_latitude_deg,
            search_config.origin_longitude_deg,
            point.east_km,
            point.north_km);
        if (cache_search_enabled) {
            try { return evaluate_point_cached(point, site, evaluation); }
            catch (const std::bad_alloc&) {}
        }
        if (config.maximum_exact_score_cache_bytes != 0)
            ++cache_stats.cold_fallback_points;
        const auto track_count = static_cast<std::uint32_t>(records.size());
        const std::uint32_t workers = config.scoring_execution.workers;
        leo_score_stats score_stats{};
        leo_location_status status = LEO_LOCATION_OK;
        if (workers == 1) {
            leo_track_scores_clear(score_scratch.data(), track_count);
            status = leo_score_partition(
                scorers[0].get(), &orbit_snapshot, records.data(), track_count,
                &site, &search_config.score, 0, orbit_snapshot.satellite_count,
                score_scratch.data(), &score_stats);
        } else {
            std::array<leo_location_status, 4> statuses{};
            std::array<leo_score_stats, 4> statistics{};
            std::array<std::atomic<unsigned char>, 4> claimed{};
            std::array<unsigned char, 4> finished{};
            for (std::uint32_t worker = 0; worker < workers; ++worker) {
                statuses[worker] = LEO_LOCATION_STATE;
                claimed[worker].store(0, std::memory_order_relaxed);
                leo_track_scores_clear(score_partials[worker].data(), track_count);
            }
            std::atomic<bool> invalid_index{false};
            struct ScoreBatch {
                Impl& owner;
                const std::vector<leo_location_track>& records;
                const leo_location_site& site;
                std::array<leo_location_status, 4>& statuses;
                std::array<leo_score_stats, 4>& statistics;
                std::array<std::atomic<unsigned char>, 4>& claimed;
                std::array<unsigned char, 4>& finished;
                std::atomic<bool>& invalid_index;
                std::uint32_t workers;
            } batch{*this, records, site, statuses, statistics, claimed,
                    finished, invalid_index, workers};
            try {
                config.scoring_execution.run(
                    config.scoring_execution.context, workers, &batch,
                    [](void* opaque, std::size_t index) {
                        auto& state = *static_cast<ScoreBatch*>(opaque);
                        if (index >= state.workers ||
                            state.claimed[index].exchange(1, std::memory_order_relaxed)) {
                            state.invalid_index.store(true, std::memory_order_relaxed);
                            return;
                        }
                        const auto worker = static_cast<std::uint32_t>(index);
                        const std::uint32_t satellites =
                            state.owner.orbit_snapshot.satellite_count;
                        const std::uint32_t begin = static_cast<std::uint32_t>(
                            static_cast<std::uint64_t>(satellites) * worker /
                            state.workers);
                        const std::uint32_t end = static_cast<std::uint32_t>(
                            static_cast<std::uint64_t>(satellites) * (worker + 1U) /
                            state.workers);
                        state.statuses[worker] = leo_score_partition(
                            state.owner.scorers[worker].get(),
                            &state.owner.orbit_snapshot,
                            state.records.data(),
                            static_cast<std::uint32_t>(state.records.size()),
                            &state.site, &state.owner.search_config.score,
                            begin, end,
                            state.owner.score_partials[worker].data(),
                            &state.statistics[worker]);
                        state.finished[worker] = 1;
                    });
            } catch (...) {
                return Status::error;
            }
            if (invalid_index.load(std::memory_order_relaxed)) return Status::error;
            for (std::uint32_t worker = 0; worker < workers; ++worker) {
                if (!finished[worker] || statuses[worker] != LEO_LOCATION_OK)
                    return Status::error;
            }
            std::copy(score_partials[0].begin(), score_partials[0].end(),
                score_scratch.begin());
            score_stats = statistics[0];
            for (std::uint32_t worker = 1; worker < workers; ++worker) {
                if (UINT64_MAX - score_stats.rejected_satellite_tracks <
                        statistics[worker].rejected_satellite_tracks ||
                    UINT64_MAX - score_stats.evaluated_satellite_tracks <
                        statistics[worker].evaluated_satellite_tracks ||
                    leo_track_scores_reduce(
                        score_scratch.data(), score_partials[worker].data(),
                        track_count) != LEO_LOCATION_OK) {
                    return Status::error;
                }
                score_stats.rejected_satellite_tracks +=
                    statistics[worker].rejected_satellite_tracks;
                score_stats.evaluated_satellite_tracks +=
                    statistics[worker].evaluated_satellite_tracks;
            }
        }
        if (status != LEO_LOCATION_OK) return Status::error;
        return finish_evaluation(point, records, score_stats, evaluation);
    }

    Config config;
    SessionAuthority authority;
    std::uint64_t stream_generation{};
    std::uint64_t history_capacity_evictions{};
    std::int64_t causal_watermark{};
    std::uint64_t publication_generation{};
    std::map<std::pair<std::int64_t, std::string>, Stored> history;
    std::unordered_set<std::string> identities;
    std::shared_ptr<const Snapshot> current;
    std::int64_t last_published_watermark{};
    std::unique_ptr<leo_orbit_context, OrbitDeleter> orbit;
    leo_orbit_snapshot orbit_snapshot{};
    std::uint64_t orbit_generation{};
    std::unique_ptr<leo_search_context, SearchDeleter> search;
    std::vector<std::unique_ptr<leo_score_context, ScoreDeleter>> scorers;
    bool search_active{};
    std::uint64_t search_generation{};
    std::shared_ptr<const Snapshot> search_snapshot;
    std::vector<leo_search_point> pending_search_points;
    std::vector<leo_search_evaluation> pending_search_evaluations;
    std::vector<leo_track_score> score_scratch;
    std::vector<std::vector<leo_track_score>> score_partials;
    std::vector<std::vector<leo_score_stats>> cache_stats_partials;
    CacheState cache;
    ExactScoreCacheStats cache_stats{};
    bool cache_search_enabled{};
    SearchConfig search_config{};
    SearchResult last_search{};
};

Coordinator::Coordinator(Config config, SessionAuthority authority)
    : impl_(std::make_unique<Impl>(std::move(config), std::move(authority))) {}
Coordinator::~Coordinator() = default;
Coordinator::Coordinator(Coordinator&&) noexcept = default;
Coordinator& Coordinator::operator=(Coordinator&&) noexcept = default;

Status Coordinator::replace_stream_generation(std::uint64_t generation) {
    if (generation == 0 || generation <= impl_->stream_generation) return Status::invalid;
    impl_->invalidate_search();
    impl_->clear_cache();
    impl_->stream_generation = generation;
    impl_->history_capacity_evictions = 0;
    impl_->causal_watermark = 0;
    impl_->last_published_watermark = 0;
    impl_->history.clear();
    impl_->identities.clear();
    impl_->current.reset();
    return Status::ok;
}

IngestReceipt Coordinator::ingest(
    const Observation& observation,
    std::int64_t causal_watermark_utc_ns) {
    if (!valid_observation(observation)) return {Status::invalid, impl_->history.size(), 0};
    return ingest(observation, derive_support_authority(observation), causal_watermark_utc_ns);
}

IngestReceipt Coordinator::ingest(
    const Observation& observation,
    const pipeline::SupportAuthority& support,
    std::int64_t causal_watermark_utc_ns) {
    if (!valid_observation(observation) || !support_matches(observation, support) ||
        causal_watermark_utc_ns <= 0 ||
        (impl_->causal_watermark != 0 && causal_watermark_utc_ns < impl_->causal_watermark)) {
        return {Status::invalid, impl_->history.size(), 0};
    }
    if (observation.generation != impl_->stream_generation) {
        return {Status::stale_generation, impl_->history.size(), 0};
    }
    if (observation.support_end_utc_ns > causal_watermark_utc_ns) {
        return {Status::future_observation, impl_->history.size(), 0};
    }
    if (impl_->identities.count(observation.candidate_id)) {
        return {Status::duplicate, impl_->history.size(), 0};
    }
    impl_->history.emplace(
        std::make_pair(observation.support_end_utc_ns, observation.candidate_id),
        Impl::Stored{observation, support});
    impl_->identities.insert(observation.candidate_id);
    impl_->causal_watermark = causal_watermark_utc_ns;
    const std::size_t pruned = impl_->prune(causal_watermark_utc_ns);
    impl_->expire_snapshot_if_needed();
    return {Status::ok, impl_->history.size(), pruned};
}

Status Coordinator::advance_watermark(std::int64_t causal_watermark_utc_ns) {
    if (causal_watermark_utc_ns <= 0 ||
        (impl_->causal_watermark != 0 && causal_watermark_utc_ns < impl_->causal_watermark))
        return Status::invalid;
    impl_->causal_watermark = causal_watermark_utc_ns;
    (void)impl_->prune(causal_watermark_utc_ns);
    impl_->expire_snapshot_if_needed();
    return Status::ok;
}

Status Coordinator::publish(
    std::int64_t watermark_utc_ns,
    std::shared_ptr<const Snapshot>* snapshot) {
    if (snapshot == nullptr || watermark_utc_ns <= 0 || impl_->stream_generation == 0 ||
        impl_->causal_watermark == 0 || watermark_utc_ns > impl_->causal_watermark ||
        watermark_utc_ns <= impl_->last_published_watermark) {
        return Status::invalid;
    }
    std::vector<tracking::Candidate> candidates;
    pipeline::GraphAuthority graph{
        impl_->authority.session_id,
        impl_->authority.input_manifest_digest,
        impl_->authority.session_start_utc_ns,
        {},
    };
    for (const auto& item : impl_->history) {
        const auto& stored = item.second;
        if (stored.observation.support_end_utc_ns > watermark_utc_ns) continue;
        candidates.push_back(to_candidate(stored.observation));
        graph.candidates.emplace(stored.observation.candidate_id, stored.support);
    }
    if (candidates.empty()) return Status::no_observations;
    struct DispatchState {
        tracking::LaneExecution port;
        bool failed{};
    } dispatch{impl_->config.tracking_execution};
    tracking::LaneExecution execution{};
    if (dispatch.port.run) {
        execution={&dispatch,[](void* opaque,std::size_t count,void* context,
                                void (*task)(void*,std::size_t)) {
            auto& state=*static_cast<DispatchState*>(opaque);
            try { state.port.run(state.port.context,count,context,task); }
            catch (...) { state.failed=true;throw; }
        }};
    }
    try {
        tracking::Result tracks = tracking::reconstruct(candidates, impl_->config.tracking,
            execution);
        if (tracks.tracks.size() > impl_->config.maximum_tracks) return Status::capacity;
        pipeline::LocationTrackBatch location = pipeline::make_location_tracks(tracks, graph);
        auto next = std::make_shared<Snapshot>();
        next->generation = ++impl_->publication_generation;
        next->stream_generation = impl_->stream_generation;
        next->watermark_utc_ns = watermark_utc_ns;
        next->retained_observation_count = candidates.size();
        next->tracking_result = std::move(tracks);
        next->location_tracks = std::move(location);
        if (impl_->config.publication_search_policy ==
                PublicationSearchPolicy::invalidate_on_publish) {
            impl_->invalidate_search();
        }
        impl_->current = next;
        impl_->last_published_watermark = watermark_utc_ns;
        *snapshot = std::move(next);
        return Status::ok;
    } catch (const std::invalid_argument&) {
        return dispatch.failed ? Status::error : Status::invalid;
    } catch (...) {
        return Status::error;
    }
}

std::shared_ptr<const Snapshot> Coordinator::current_snapshot() const {
    return impl_->current;
}

Status Coordinator::replace_orbit(const OrbitBuild& build) {
    if (build.generation == 0 || build.generation <= impl_->orbit_generation ||
        build.start_utc_ns != impl_->authority.session_start_utc_ns ||
        build.records.empty() || build.records.size() > impl_->config.maximum_satellites ||
        build.knot_count < 2 || build.knot_count > impl_->config.maximum_knots) {
        return Status::invalid;
    }
    leo_orbit_snapshot next{};
    const leo_location_status status = leo_orbit_build_tle(
        impl_->orbit.get(), build.generation, build.start_utc_ns,
        build.knot_start_s, build.knot_step_s, build.knot_count,
        build.records.data(), static_cast<std::uint32_t>(build.records.size()), &next);
    if (status != LEO_LOCATION_OK) {
        return status == LEO_LOCATION_CAPACITY ? Status::capacity : Status::error;
    }
    impl_->invalidate_search();
    impl_->clear_cache();
    impl_->orbit_snapshot = next;
    impl_->orbit_generation = build.generation;
    return Status::ok;
}

Status Coordinator::begin_search(
    std::uint64_t snapshot_generation,
    const SearchConfig& config,
    SearchResult* result) {
    if (result == nullptr || !impl_->current ||
        impl_->current->generation != snapshot_generation ||
        !std::isfinite(config.origin_latitude_deg) ||
        !std::isfinite(config.origin_longitude_deg) ||
        config.origin_latitude_deg < -90.0 || config.origin_latitude_deg > 90.0 ||
        config.origin_longitude_deg < -180.0 || config.origin_longitude_deg > 180.0) {
        return Status::invalid;
    }
    if (impl_->orbit_generation == 0) return Status::no_orbit;
    if (impl_->current->location_tracks.records.empty()) return Status::no_tracks;
    const auto snapshot = impl_->current;
    std::uint32_t maximum_observations = 0;
    for (const auto& track : snapshot->location_tracks.records) {
        maximum_observations = std::max(maximum_observations, track.observation_count);
    }
    if (maximum_observations > impl_->config.maximum_observations_per_track) {
        return Status::capacity;
    }
    impl_->invalidate_search();
    ++impl_->search_generation;
    if (impl_->search_generation == 0) ++impl_->search_generation;
    const leo_location_status status = leo_search_begin(
        impl_->search.get(), impl_->search_generation, &config.policy);
    if (status != LEO_LOCATION_OK) return Status::invalid;
    const leo_location_site origin = make_site(
        config.origin_latitude_deg, config.origin_longitude_deg, 0.0, 0.0);
    if (leo_score_validate_inputs(
            &impl_->orbit_snapshot,
            snapshot->location_tracks.records.data(),
            static_cast<std::uint32_t>(snapshot->location_tracks.records.size()),
            &origin, &config.score) != LEO_LOCATION_OK) {
        (void)leo_search_cancel(impl_->search.get(), impl_->search_generation);
        return Status::invalid;
    }
    impl_->search_config = config;
    impl_->search_snapshot = snapshot;
    impl_->score_scratch.resize(snapshot->location_tracks.records.size());
    for (auto& partial : impl_->score_partials)
        partial.resize(snapshot->location_tracks.records.size());
    for (auto& partial : impl_->cache_stats_partials)
        partial.resize(snapshot->location_tracks.records.size());
    impl_->cache_search_enabled = impl_->prepare_cache(snapshot, config.score);
    impl_->pending_search_points.clear();
    impl_->pending_search_evaluations.clear();
    impl_->search_active = true;
    impl_->last_search = SearchResult{};
    impl_->last_search.state = SearchState::running_unconverged;
    impl_->last_search.status = Status::running_unconverged;
    impl_->last_search.search_generation = impl_->search_generation;
    impl_->last_search.snapshot_generation = snapshot_generation;
    impl_->last_search.orbit_generation = impl_->orbit_generation;
    *result = impl_->last_search;
    return Status::ok;
}

SearchResult Coordinator::resume_search(std::uint32_t maximum_points) {
    if (!impl_->search_active) return impl_->last_search;
    if (maximum_points == 0) return impl_->result(Status::running_unconverged);
    const bool bounded_batches = impl_->config.publication_search_policy ==
        PublicationSearchPolicy::pin_started_snapshot;
    std::uint32_t used = 0;
    impl_->last_search.required_points = 0;
    while (used < maximum_points) {
        if (bounded_batches && !impl_->pending_search_points.empty()) {
            const std::uint32_t remaining = static_cast<std::uint32_t>(
                impl_->pending_search_points.size() -
                impl_->pending_search_evaluations.size());
            const std::uint32_t count = std::min(remaining, maximum_points - used);
            for (std::uint32_t index = 0; index < count; ++index) {
                const std::size_t point_index = impl_->pending_search_evaluations.size();
                leo_search_evaluation evaluation{};
                if (impl_->evaluate_point(
                        impl_->pending_search_points[point_index], &evaluation) != Status::ok) {
                    impl_->search_active = false;
                    return impl_->finish_result(Status::error);
                }
                impl_->pending_search_evaluations.push_back(evaluation);
            }
            used += count;
            if (impl_->pending_search_evaluations.size() <
                    impl_->pending_search_points.size()) {
                impl_->last_search.required_points = static_cast<std::uint32_t>(
                    impl_->pending_search_points.size() -
                    impl_->pending_search_evaluations.size());
                return impl_->result(Status::running_unconverged);
            }
            const leo_location_status submit = leo_search_submit(
                impl_->search.get(), impl_->search_generation,
                impl_->pending_search_evaluations.data(),
                static_cast<std::uint32_t>(impl_->pending_search_evaluations.size()));
            if (submit != LEO_LOCATION_OK) {
                impl_->search_active = false;
                return impl_->finish_result(Status::error);
            }
            impl_->pending_search_points.clear();
            impl_->pending_search_evaluations.clear();
            continue;
        }
        std::uint32_t required = 0;
        leo_location_status status = leo_search_next(
            impl_->search.get(), impl_->search_generation, nullptr, 0, &required);
        if (status == LEO_LOCATION_DONE) {
            impl_->search_active = false;
            return impl_->finish_result(Status::complete);
        }
        if (status == LEO_LOCATION_CANCELLED) {
            impl_->search_active = false;
            return impl_->finish_result(Status::cancelled);
        }
        if (status != LEO_LOCATION_CAPACITY || required == 0) {
            impl_->search_active = false;
            return impl_->finish_result(Status::error);
        }
        if (!bounded_batches && required > maximum_points - used) {
            impl_->last_search.required_points = required;
            return impl_->result(Status::running_unconverged);
        }
        std::vector<leo_search_point> points(required);
        std::uint32_t count = 0;
        status = leo_search_next(
            impl_->search.get(), impl_->search_generation,
            points.data(), required, &count);
        if (status != LEO_LOCATION_OK || count != required) {
            impl_->search_active = false;
            return impl_->finish_result(Status::error);
        }
        if (bounded_batches) {
            impl_->pending_search_points = std::move(points);
            impl_->pending_search_evaluations.clear();
            continue;
        }
        std::vector<leo_search_evaluation> evaluations;
        evaluations.reserve(required);
        for (const auto& point : points) {
            leo_search_evaluation evaluation{};
            if (impl_->evaluate_point(point, &evaluation) != Status::ok) {
                impl_->search_active = false;
                return impl_->finish_result(Status::error);
            }
            evaluations.push_back(evaluation);
        }
        status = leo_search_submit(
            impl_->search.get(), impl_->search_generation,
            evaluations.data(), static_cast<std::uint32_t>(evaluations.size()));
        if (status != LEO_LOCATION_OK) {
            impl_->search_active = false;
            return impl_->finish_result(Status::error);
        }
        used += required;
    }
    // Settle DONE without scoring past the caller's point budget. A CAPACITY
    // response merely exposes the size of the next resumable native batch.
    std::uint32_t required = 0;
    const leo_location_status status = leo_search_next(
        impl_->search.get(), impl_->search_generation, nullptr, 0, &required);
    if (status == LEO_LOCATION_DONE) {
        impl_->search_active = false;
        return impl_->finish_result(Status::complete);
    }
    if (status != LEO_LOCATION_CAPACITY || required == 0) {
        impl_->search_active = false;
        return impl_->finish_result(Status::error);
    }
    impl_->last_search.required_points = required;
    return impl_->result(Status::running_unconverged);
}

SearchResult Coordinator::cancel_search() {
    if (!impl_->search_active) return impl_->last_search;
    const leo_location_status status =
        leo_search_cancel(impl_->search.get(), impl_->search_generation);
    impl_->search_active = false;
    return impl_->finish_result(
        status == LEO_LOCATION_OK ? Status::cancelled : Status::error);
}

std::size_t Coordinator::retained_observations() const { return impl_->history.size(); }
std::uint64_t Coordinator::history_capacity_evictions() const {
    return impl_->history_capacity_evictions;
}
std::int64_t Coordinator::causal_watermark_utc_ns() const { return impl_->causal_watermark; }
ExactScoreCacheStats Coordinator::exact_score_cache_stats() const { return impl_->cache_stats; }

}  // namespace leo::adaptive::online
