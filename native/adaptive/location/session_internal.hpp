#pragma once
#include "location.h"
#ifdef LEO_RESEARCH_WARM_ID_INDEX
#include "research/catalogue_index.hpp"
#endif
#ifdef LEO_RESEARCH_IMMUTABLE_ORBIT
#include "research/immutable_orbit.hpp"
#endif
#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
#include <thread>
#include <vector>

namespace leo::adaptive::location::detail {
namespace {
struct BorrowedInput {
    leo_orbit_snapshot snapshot{};
    std::vector<leo_location_track> tracks;
    uint32_t maximum_observations{};
};

inline leo_location_site make_site(
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

struct ScoreEngine {
    explicit ScoreEngine(const BorrowedInput &fixture, unsigned requested_workers)
        : workers(requested_workers), partials(requested_workers)
#ifdef LEO_RESEARCH_WARM_ID_INDEX
          , catalogue_index(fixture.snapshot.satellite_ids,fixture.snapshot.satellite_count)
#endif
    {
        contexts.reserve(workers);
        for (unsigned worker = 0; worker < workers; ++worker) {
            contexts.emplace_back(leo_score_context_create(fixture.maximum_observations, 11),leo_score_context_destroy);
#ifdef LEO_RESEARCH_IMMUTABLE_ORBIT
            if(contexts.back() && !leo::location::research::bind_immutable_orbit(contexts.back().get(),&fixture.snapshot)) {
                contexts.back().reset();
            }
#endif
            partials[worker].resize(fixture.tracks.size());
        }
    }

    bool valid() const {
        return workers != 0 &&
            std::all_of(contexts.begin(), contexts.end(), [](const auto& value) {
                return value != nullptr;
            });
    }

    unsigned workers;
#ifdef LEO_RESEARCH_CAPPED_SEARCH
    bool objective_only=false;
#endif
    std::vector<std::unique_ptr<leo_score_context,decltype(&leo_score_context_destroy)>> contexts;
    std::vector<std::vector<leo_track_score>> partials;
#ifdef LEO_RESEARCH_WARM_ID_INDEX
    leo::location::research::CatalogueIndex catalogue_index;
#endif
#ifdef LEO_RESEARCH_SCORE_WARM_START
    std::vector<leo_track_score> previous;
#endif
};

inline bool score_site(
    ScoreEngine *engine,
    const BorrowedInput &fixture,
    const leo_location_site &site,
    std::vector<leo_track_score> *tracks,
    leo_point_score *point) {
    leo_score_config config = leo_score_default_config();
    std::vector<leo_location_status> statuses(engine->workers, LEO_LOCATION_STATE);
    std::vector<std::thread> threads;
    struct JoinThreads {
        std::vector<std::thread>& values;
        ~JoinThreads(){for(auto& thread:values)if(thread.joinable())thread.join();}
    } join_threads{threads};
    threads.reserve(engine->workers > 1 ? engine->workers : 0);
    for (unsigned worker = 0; worker < engine->workers; ++worker) {
        auto evaluate = [&, worker] {
            std::vector<leo_track_score> &partial = engine->partials[worker];
            leo_track_scores_clear(partial.data(), static_cast<uint32_t>(partial.size()));
#ifdef LEO_RESEARCH_CAPPED_SEARCH
            if(engine->objective_only) {
                // Private objective sentinel, never an association result. A
                // score >= the cap contributes exactly the same regional loss.
                for(auto& score:partial) score=leo_track_score{1,
                    std::numeric_limits<int32_t>::max(),0,config.unmatched_penalty_hz,
                    std::numeric_limits<double>::infinity(),0};
            }
#endif
#ifdef LEO_RESEARCH_SCORE_WARM_START
            // Recompute a previous site's winner at THIS site. Its old score is
            // never reused, and the full satellite partition is still searched.
            for(size_t i=0;i<engine->previous.size();++i) {
                const auto& previous=engine->previous[i];
                if(!previous.matched) continue;
#ifdef LEO_RESEARCH_WARM_ID_INDEX
                const uint32_t seed=engine->catalogue_index.find(previous.candidate_id);
                if(seed==UINT32_MAX)continue;
#else
                auto found=std::find(fixture.snapshot.satellite_ids,(fixture.snapshot.satellite_ids+fixture.snapshot.satellite_count),previous.candidate_id);
                if(found==(fixture.snapshot.satellite_ids+fixture.snapshot.satellite_count)) continue;
                const uint32_t seed=static_cast<uint32_t>(found-fixture.snapshot.satellite_ids);
#endif
                auto status=leo_score_partition(engine->contexts[worker].get(),&fixture.snapshot,
                    &fixture.tracks[i],1,&site,&config,seed,seed+1,&partial[i],nullptr);
                if(status!=LEO_LOCATION_OK) { statuses[worker]=status;return; }
            }
#endif
            const uint32_t begin = static_cast<uint32_t>(
                static_cast<uint64_t>(fixture.snapshot.satellite_count) * worker /
                engine->workers);
            const uint32_t end = static_cast<uint32_t>(
                static_cast<uint64_t>(fixture.snapshot.satellite_count) * (worker + 1) /
                engine->workers);
            statuses[worker] = leo_score_partition(
                engine->contexts[worker].get(),
                &fixture.snapshot,
                fixture.tracks.data(),
                static_cast<uint32_t>(fixture.tracks.size()),
                &site,
                &config,
                begin,
                end,
                partial.data(),
                nullptr);
        };
        if (engine->workers == 1) {
            evaluate();
        } else {
            threads.emplace_back(evaluate);
        }
    }
    for (std::thread &thread : threads) {
        thread.join();
    }
    if (std::any_of(statuses.begin(), statuses.end(), [](leo_location_status status) {
            return status != LEO_LOCATION_OK;
        })) {
        return false;
    }
    *tracks = engine->partials[0];
    for (unsigned worker = 1; worker < engine->workers; ++worker) {
        if (leo_track_scores_reduce(
                tracks->data(),
                engine->partials[worker].data(),
                static_cast<uint32_t>(tracks->size())) != LEO_LOCATION_OK) {
            return false;
        }
    }
#ifdef LEO_RESEARCH_SCORE_WARM_START
    engine->previous=*tracks;
#endif
    return leo_point_score_finish(
               fixture.tracks.data(),
               static_cast<uint32_t>(fixture.tracks.size()),
               tracks->data(),
               &config,
               point) == LEO_LOCATION_OK;
}

} // internal linkage: research compilation flags may differ between adapters.
} // namespace leo::adaptive::location::detail
