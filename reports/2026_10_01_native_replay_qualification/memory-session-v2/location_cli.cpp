/* Explicit-path fixture/replay adapter for the reusable location C ABI.
 * The LOC1 format is research-private and intentionally not an application
 * persistence contract. */
#include "location.h"
#include "session_internal.hpp"
#include "session.hpp"
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
using leo::adaptive::location::detail::make_site;
using leo::adaptive::location::detail::ScoreEngine;
using leo::adaptive::location::detail::score_site;
struct TrackOwned {
    std::vector<double> times;
    std::vector<double> measured;
    std::vector<uint8_t> training;
};

struct Fixture : leo::adaptive::location::detail::BorrowedInput {
    std::vector<leo_location_site> sites;
    std::vector<TrackOwned> owned_tracks;
    std::vector<int32_t> ids;
    std::vector<leo_orbit_state> states;
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

void write_track_point(FILE *output, const leo_point_score &point,
                       const std::vector<leo_track_score> &tracks) {
    std::fprintf(output,"{\"score_hz\":%.17g,\"matched_tracks\":%u,\"tracks\":[",
                 point.residual_rmse_hz,point.matched_track_count);
    for(size_t i=0;i<tracks.size();++i) {
        const auto& s=tracks[i];
        std::fprintf(output,"%s{\"candidate_id\":%d,\"tau_s\":%d,\"held_hz\":%.17g,"
                     "\"fit_hz\":%.17g,\"offset_hz\":%.17g}",i?",":"",
                     s.candidate_id,s.tau_s,s.heldout_rms_hz,s.training_rms_hz,s.frequency_offset_hz);
    }
    std::fprintf(output,"]}");
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
        if(point_index)std::printf(",");
        write_track_point(stdout,point,tracks);
    }
    std::printf("]}\n");
    return 0;
}

int run_search(
    const Fixture &fixture,
    double latitude_deg,
    double longitude_deg,
    double radius_km,
    unsigned workers, FILE *associations=nullptr) {
    using namespace leo::adaptive::location;
    SearchOutput completed;
    SearchOptions options{latitude_deg,longitude_deg,radius_km,workers,associations!=nullptr};
    ProgressCallback progress=nullptr;
#ifdef LEO_RESEARCH_SEARCH_PROGRESS
    progress=[](void*,const SearchProgress& event) {
        if(event.associations)
            std::fprintf(stderr,"{\"kind\":\"selected_associations\",\"wall_s\":%.17g}\n",event.wall_s);
        else std::fprintf(stderr,"{\"kind\":\"search_point\",\"sequence\":%u,\"east_km\":%.17g,\"north_km\":%.17g,\"score_hz\":%.17g,\"wall_s\":%.17g}\n",
            event.sequence,event.east_km,event.north_km,event.score_hz,event.wall_s);
        std::fflush(stderr);
    };
#endif
    const auto status=search_location({&fixture.snapshot,fixture.tracks.data(),
        static_cast<uint32_t>(fixture.tracks.size())},options,completed,progress);
    if(status!=LEO_LOCATION_OK)return status==LEO_LOCATION_INVALID?2:4;
    const auto& result=completed.result;
    const auto& policy=completed.policy;
    const auto& inventory=completed.evaluations;
    if(associations) {
        std::fprintf(associations,"{\"points\":[");
        write_track_point(associations,completed.selected_score,completed.associations);
        std::fprintf(associations,"]}\n");
        if(std::fflush(associations) || std::ferror(associations))return 4;
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
