/* Explicit-path fixture/replay adapter for the reusable location C ABI.
 * The LOC1 format is research-private and intentionally not an application
 * persistence contract. */
#include "location.h"
#ifdef LEO_RESEARCH_IMMUTABLE_ORBIT
#include "research/immutable_orbit.hpp"
#endif

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <memory>
#include <thread>
#include <vector>
#ifdef LEO_RESEARCH_SEARCH_PROGRESS
#include <chrono>
#endif

namespace {
struct TrackOwned {
    std::vector<double> times;
    std::vector<double> measured;
    std::vector<uint8_t> training;
};

struct Fixture {
    leo_orbit_snapshot snapshot{};
    std::vector<leo_location_site> sites;
    std::vector<TrackOwned> owned_tracks;
    std::vector<leo_location_track> tracks;
    std::vector<int32_t> ids;
    std::vector<leo_orbit_state> states;
    uint32_t maximum_observations{};
};

struct FileCloser {
    void operator()(FILE *file) const {
        if (file != nullptr) {
            std::fclose(file);
        }
    }
};

bool read_exact(FILE *file, void *destination, size_t size, size_t count) {
    return std::fread(destination, size, count, file) == count;
}

bool load_fixture(const char *path, Fixture *fixture) {
    std::unique_ptr<FILE, FileCloser> file(std::fopen(path, "rb"));
    if (!file) {
        return false;
    }
    uint32_t header[5];
    double grid[2];
    if (!read_exact(file.get(), header, sizeof(uint32_t), 5) ||
        !read_exact(file.get(), grid, sizeof(double), 2) || header[0] != 0x31434f4c ||
        header[1] == 0 || header[1] > 20000 || header[2] < 2 || header[2] > 2000 ||
        header[3] == 0 || header[3] > 128 || header[4] == 0 || header[4] > 128 ||
        !std::isfinite(grid[0]) || !std::isfinite(grid[1]) || grid[1] <= 0.0) {
        return false;
    }
    const uint32_t satellites = header[1];
    const uint32_t knots = header[2];
    const uint32_t tracks = header[3];
    const uint32_t points = header[4];
    fixture->sites.resize(points);
    if (!read_exact(file.get(), fixture->sites.data(), sizeof(double), points * 6)) {
        return false;
    }
    fixture->owned_tracks.resize(tracks);
    fixture->tracks.resize(tracks);
    for (uint32_t index = 0; index < tracks; ++index) {
        uint32_t dimensions[2];
        if (!read_exact(file.get(), dimensions, sizeof(uint32_t), 2) || dimensions[0] < 6 ||
            dimensions[0] > 100000 || dimensions[1] == 0) {
            return false;
        }
        TrackOwned &owned = fixture->owned_tracks[index];
        owned.times.resize(dimensions[0]);
        owned.measured.resize(dimensions[0]);
        owned.training.resize(dimensions[0]);
        if (!read_exact(file.get(), owned.times.data(), sizeof(double), dimensions[0]) ||
            !read_exact(file.get(), owned.measured.data(), sizeof(double), dimensions[0]) ||
            !read_exact(file.get(), owned.training.data(), sizeof(uint8_t), dimensions[0])) {
            return false;
        }
        fixture->tracks[index] = leo_location_track{
            index,
            dimensions[0],
            dimensions[1],
            owned.times.data(),
            owned.measured.data(),
            owned.training.data(),
        };
        fixture->maximum_observations =
            std::max(fixture->maximum_observations, dimensions[0]);
    }
    fixture->ids.resize(satellites);
    const size_t state_count = static_cast<size_t>(satellites) * knots;
    fixture->states.resize(state_count);
    if (!read_exact(file.get(), fixture->ids.data(), sizeof(int32_t), satellites) ||
        !read_exact(file.get(), fixture->states.data(), sizeof(leo_orbit_state), state_count) ||
        std::fgetc(file.get()) != EOF) {
        return false;
    }
    fixture->snapshot = leo_orbit_snapshot{
        1,
        0,
        grid[0],
        grid[1],
        satellites,
        knots,
        fixture->ids.data(),
        fixture->states.data(),
    };
    return true;
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

struct ScoreEngine {
    explicit ScoreEngine(const Fixture &fixture, unsigned requested_workers)
        : workers(requested_workers), partials(requested_workers) {
        contexts.reserve(workers);
        for (unsigned worker = 0; worker < workers; ++worker) {
            contexts.push_back(leo_score_context_create(fixture.maximum_observations, 11));
#ifdef LEO_RESEARCH_IMMUTABLE_ORBIT
            if(contexts.back() && !leo::location::research::bind_immutable_orbit(contexts.back(),&fixture.snapshot)) {
                leo_score_context_destroy(contexts.back());contexts.back()=nullptr;
            }
#endif
            partials[worker].resize(fixture.tracks.size());
        }
    }

    ~ScoreEngine() {
        for (leo_score_context *context : contexts) {
            leo_score_context_destroy(context);
        }
    }

    bool valid() const {
        return workers != 0 &&
            std::all_of(contexts.begin(), contexts.end(), [](const auto *value) {
                return value != nullptr;
            });
    }

    unsigned workers;
#ifdef LEO_RESEARCH_CAPPED_SEARCH
    bool objective_only=false;
#endif
    std::vector<leo_score_context *> contexts;
    std::vector<std::vector<leo_track_score>> partials;
#ifdef LEO_RESEARCH_SCORE_WARM_START
    std::vector<leo_track_score> previous;
#endif
};

bool score_site(
    ScoreEngine *engine,
    const Fixture &fixture,
    const leo_location_site &site,
    std::vector<leo_track_score> *tracks,
    leo_point_score *point) {
    leo_score_config config = leo_score_default_config();
    std::vector<leo_location_status> statuses(engine->workers, LEO_LOCATION_STATE);
    std::vector<std::thread> threads;
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
                auto found=std::find(fixture.ids.begin(),fixture.ids.end(),previous.candidate_id);
                if(found==fixture.ids.end()) continue;
                const uint32_t seed=static_cast<uint32_t>(found-fixture.ids.begin());
                auto status=leo_score_partition(engine->contexts[worker],&fixture.snapshot,
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
                engine->contexts[worker],
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

int run_score(const Fixture &fixture, unsigned workers) {
    ScoreEngine engine(fixture, workers);
    if (!engine.valid()) {
        return 3;
    }
    std::vector<leo_track_score> tracks(fixture.tracks.size());
    std::printf("{\"points\":[");
    for (size_t point_index = 0; point_index < fixture.sites.size(); ++point_index) {
        leo_point_score point{};
        if (!score_site(&engine, fixture, fixture.sites[point_index], &tracks, &point)) {
            return 4;
        }
        std::printf(
            "%s{\"score_hz\":%.17g,\"matched_tracks\":%u,\"tracks\":[",
            point_index == 0 ? "" : ",",
            point.residual_rmse_hz,
            point.matched_track_count);
        for (size_t track = 0; track < tracks.size(); ++track) {
            const leo_track_score &score = tracks[track];
            std::printf(
                "%s{\"candidate_id\":%d,\"tau_s\":%d,\"held_hz\":%.17g,"
                "\"fit_hz\":%.17g,\"offset_hz\":%.17g}",
                track == 0 ? "" : ",",
                score.candidate_id,
                score.tau_s,
                score.heldout_rms_hz,
                score.training_rms_hz,
                score.frequency_offset_hz);
        }
        std::printf("]}");
    }
    std::printf("]}\n");
    return 0;
}

int run_search(
    const Fixture &fixture,
    double latitude_deg,
    double longitude_deg,
    double radius_km,
    unsigned workers) {
    ScoreEngine scorer(fixture, workers);
#ifdef LEO_RESEARCH_CAPPED_SEARCH
    scorer.objective_only=true;
#endif
    std::unique_ptr<leo_search_context, decltype(&leo_search_context_destroy)> search(
        leo_search_context_create(400), &leo_search_context_destroy);
    if (!scorer.valid() || !search) {
        return 3;
    }
    leo_search_policy policy = leo_search_default_policy(radius_km);
    constexpr uint64_t generation = 1;
    if (leo_search_begin(search.get(), generation, &policy) != LEO_LOCATION_OK) {
        return 2;
    }
    std::vector<leo_track_score> tracks(fixture.tracks.size());
    std::vector<leo_search_evaluation> inventory;
    inventory.reserve(policy.budget_points);
    for (;;) {
        leo_search_point points[128];
        uint32_t count = 0;
        const leo_location_status status =
            leo_search_next(search.get(), generation, points, 128, &count);
        if (status == LEO_LOCATION_DONE) {
            break;
        }
        if (status != LEO_LOCATION_OK) {
            return 4;
        }
        std::vector<leo_search_evaluation> evaluations(count);
        for (uint32_t index = 0; index < count; ++index) {
#ifdef LEO_RESEARCH_SEARCH_PROGRESS
            auto point_begin=std::chrono::steady_clock::now();
#endif
            const leo_location_site site = make_site(
                latitude_deg, longitude_deg, points[index].east_km, points[index].north_km);
            leo_point_score score{};
            if (!score_site(&scorer, fixture, site, &tracks, &score)) {
                return 4;
            }
            evaluations[index] = leo_search_evaluation{
                points[index].east_km, points[index].north_km, score.weighted_mse_hz2};
            inventory.push_back(evaluations[index]);
#ifdef LEO_RESEARCH_SEARCH_PROGRESS
            std::fprintf(stderr,"{\"kind\":\"search_point\",\"sequence\":%zu,\"east_km\":%.17g,\"north_km\":%.17g,\"score_hz\":%.17g,\"wall_s\":%.17g}\n",
                inventory.size()-1,points[index].east_km,points[index].north_km,
                score.residual_rmse_hz,std::chrono::duration<double>(std::chrono::steady_clock::now()-point_begin).count());
            std::fflush(stderr);
#endif
        }
        if (leo_search_submit(search.get(), generation, evaluations.data(), count) !=
            LEO_LOCATION_OK) {
            return 4;
        }
    }
    leo_search_result result{};
    if (leo_search_get_result(search.get(), generation, &result) != LEO_LOCATION_OK ||
        !result.has_incumbent) {
        return 4;
    }
    std::printf(
        "{\"schema\":\"org.leo.native-adaptive-location-search/v2\","
        "\"evaluated_points\":%u,\"budget_points\":%u,\"deferred_cells\":%u,"
        "\"complete\":%s,\"stop_reason\":\"%s\",\"selected\":{\"east_km\":%.17g,"
        "\"north_km\":%.17g,\"score_hz\":%.17g},\"evaluations\":[",
        result.evaluated_points,
        policy.budget_points,
        result.deferred_cells,
        result.complete ? "true" : "false",
        result.complete ? "frontier-exhausted" : "point-budget-reached",
        result.incumbent.east_km,
        result.incumbent.north_km,
        std::sqrt(result.incumbent.weighted_mse_hz2));
    for (size_t index = 0; index < inventory.size(); ++index) {
        std::printf(
            "%s[%.17g,%.17g,%.17g]",
            index == 0 ? "" : ",",
            inventory[index].east_km,
            inventory[index].north_km,
            std::sqrt(inventory[index].weighted_mse_hz2));
    }
    std::printf("]}\n");
    return 0;
}

bool parse_workers(const char *text, unsigned *workers) {
    if (text == nullptr || workers == nullptr) {
        return false;
    }
    char *end = nullptr;
    const unsigned long parsed = std::strtoul(text, &end, 10);
    if (end == text || *end != '\0' || (parsed != 1 && parsed != 2)) {
        return false;
    }
    *workers = static_cast<unsigned>(parsed);
    return true;
}
}  // namespace

int main(int argc, char **argv) {
    if (argc < 3 || (std::strcmp(argv[1], "score") != 0 &&
                     std::strcmp(argv[1], "score-at") != 0 &&
                     std::strcmp(argv[1], "search") != 0)) {
        std::fprintf(
            stderr,
            "usage: %s score FIXTURE [WORKERS] | "
            "search FIXTURE LATITUDE LONGITUDE RADIUS_KM [WORKERS] | "
            "score-at FIXTURE ORIGIN_LAT ORIGIN_LON EAST_KM NORTH_KM [WORKERS]\n",
            argv[0]);
        return 2;
    }
    Fixture fixture;
    if (!load_fixture(argv[2], &fixture)) {
        std::fprintf(stderr, "invalid location fixture\n");
        return 2;
    }
    if (std::strcmp(argv[1], "score") == 0) {
        if (argc != 3 && argc != 4) {
            return 2;
        }
        unsigned workers = 1;
        return (argc == 3 || parse_workers(argv[3], &workers)) ? run_score(fixture, workers) : 2;
    }
    if(std::strcmp(argv[1],"score-at")==0) {
        if(argc!=7 && argc!=8) return 2;
        double values[4];
        for(unsigned i=0;i<4;++i) {
            char* end=nullptr;values[i]=std::strtod(argv[3+i],&end);
            if(end==argv[3+i] || *end!='\0' || !std::isfinite(values[i])) return 2;
        }
        if(values[0]<-90 || values[0]>90 || values[1]<-180 || values[1]>180) return 2;
        unsigned workers=1;
        if(argc==8 && !parse_workers(argv[7],&workers)) return 2;
        fixture.sites={make_site(values[0],values[1],values[2],values[3])};
        return run_score(fixture,workers);
    }
    if (argc != 6 && argc != 7) {
        return 2;
    }
    char *end = nullptr;
    const double latitude = std::strtod(argv[3], &end);
    if (end == argv[3] || *end != '\0') {
        return 2;
    }
    const double longitude = std::strtod(argv[4], &end);
    if (end == argv[4] || *end != '\0') {
        return 2;
    }
    const double radius = std::strtod(argv[5], &end);
    if (end == argv[5] || *end != '\0' || !std::isfinite(latitude) ||
        !std::isfinite(longitude) || !std::isfinite(radius)) {
        return 2;
    }
    unsigned workers = 1;
    return (argc == 6 || parse_workers(argv[6], &workers))
        ? run_search(fixture, latitude, longitude, radius, workers)
        : 2;
}
