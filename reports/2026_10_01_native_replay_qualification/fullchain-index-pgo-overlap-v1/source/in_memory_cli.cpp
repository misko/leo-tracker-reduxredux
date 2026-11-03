// Explicit replay adapter. Large orbit and location inputs stay in memory;
// component interaction uses public track/orbit/search ports only.
#include "checkpoint_input.hpp"
#include "track_input.hpp"
#include "selection.hpp"
#include "session.hpp"
#include "tle_input.hpp"
#include "json_output.hpp"
#include <chrono>
#include <cstdio>
#include <fstream>
#include <memory>
#include <iostream>

namespace {
using Clock=std::chrono::steady_clock;
struct FileCloser {void operator()(FILE* value)const {if(value)std::fclose(value);}};
double number(const char* text) {
    errno=0;char* end=nullptr;double value=std::strtod(text,&end);
    if(errno || !*text || *end || !std::isfinite(value))throw std::invalid_argument("invalid number");
    return value;
}
unsigned positive_integer(const char* text) {
    double value=number(text);
    if(value<1 || value>2000 || value!=std::floor(value))throw std::invalid_argument("invalid integer");
    return static_cast<unsigned>(value);
}
void timing(const char* stage,Clock::time_point begin) {
    std::fprintf(stderr,"{\"kind\":\"stage\",\"stage\":\"%s\",\"wall_s\":%.17g}\n",stage,
        std::chrono::duration<double>(Clock::now()-begin).count());
}
}

int main(int argc,char** argv) {
    if(argc!=13) {
        std::cerr<<"usage: leo-memory-position OBSERVATIONS GRAPH TRACKS TLES KNOT_START_S KNOT_STEP_S KNOT_COUNT LATITUDE LONGITUDE RADIUS_KM WORKERS ASSOCIATIONS.json\n";
        return 2;
    }
    try {
        const double start=number(argv[5]),step=number(argv[6]);
        const auto knots=positive_integer(argv[7]),workers=positive_integer(argv[11]);
        leo::adaptive::location::SearchOptions options{number(argv[8]),number(argv[9]),number(argv[10]),workers,true};
        if(step<=0 || knots<2 || workers>2 || std::abs(options.latitude_deg)>90 ||
           std::abs(options.longitude_deg)>180 || options.radius_km<=0 || options.radius_km>500)
            throw std::invalid_argument("invalid execution geometry");
        leo::adaptive::pipeline::LocationTrackBatch tracks;
        int64_t origin=0;
        auto began=Clock::now();
        {
            std::ifstream observations_input(argv[1]),graph_input(argv[2]),track_input(argv[3]);
            if(!observations_input || !graph_input || !track_input)throw std::runtime_error("cannot open checkpoints");
            const auto observations=leo::adaptive::pipeline::checkpoint::read_candidates(observations_input);
            const auto authority=leo::adaptive::pipeline::checkpoint::read_authority(graph_input);
            origin=authority.session_start_utc_ns;
            const auto hypotheses=leo::adaptive::pipeline::read_track_checkpoint(track_input,observations);
            leo::adaptive::pipeline::SelectionAudit audit;
            const auto selected=leo::adaptive::pipeline::select_exclusive_candidates(hypotheses,observations,audit);
            tracks=leo::adaptive::pipeline::make_location_tracks(selected,authority);
            std::fprintf(stderr,"{\"selection\":\"exclusive-candidates-longest-v1\",\"input_tracks\":%zu,\"output_tracks\":%zu,\"reused_memberships_removed\":%zu,\"insufficient_memberships_removed\":%zu}\n",
                audit.input_tracks,audit.output_tracks,audit.reused_memberships_removed,audit.insufficient_memberships_removed);
        }
        timing("track_conversion",began);
        began=Clock::now();
        using Orbit=std::unique_ptr<leo_orbit_context,decltype(&leo_orbit_context_destroy)>;
        Orbit orbit(nullptr,leo_orbit_context_destroy);leo_orbit_snapshot snapshot{};
        {
            std::ifstream input(argv[4]);
            const auto records=leo::adaptive::location::read_tle_records(input);
            orbit.reset(leo_orbit_context_create(static_cast<uint32_t>(records.size()),knots));
            if(!orbit)throw std::runtime_error("orbit allocation failed");
            const auto status=leo_orbit_build_tle(orbit.get(),1,origin,start,step,knots,
                records.data(),static_cast<uint32_t>(records.size()),&snapshot);
            if(status!=LEO_LOCATION_OK)throw std::runtime_error("orbit build failed: "+std::to_string(status));
        }
        timing("orbit_generation",began);
        std::unique_ptr<FILE,FileCloser> associations(std::fopen(argv[12],"wx"));
        if(!associations)throw std::runtime_error("association output exists or cannot be created");
        leo::adaptive::location::SearchOutput result;
        auto progress=[](void*,const leo::adaptive::location::SearchProgress& event) {
            if(event.associations)std::fprintf(stderr,"{\"kind\":\"selected_associations\",\"wall_s\":%.17g}\n",event.wall_s);
            else std::fprintf(stderr,"{\"kind\":\"search_point\",\"sequence\":%u,\"east_km\":%.17g,\"north_km\":%.17g,\"score_hz\":%.17g,\"wall_s\":%.17g}\n",
                event.sequence,event.east_km,event.north_km,event.score_hz,event.wall_s);
            std::fflush(stderr);
        };
        const auto status=leo::adaptive::location::search_location({&snapshot,tracks.records.data(),
            static_cast<uint32_t>(tracks.records.size())},options,result,progress);
        if(status!=LEO_LOCATION_OK)throw std::runtime_error("location search failed: "+std::to_string(status));
        if(!leo::adaptive::location::json::write_associations(associations.get(),result) ||
           !leo::adaptive::location::json::write_search(stdout,result))throw std::runtime_error("result write failed");
        return 0;
    } catch(const std::exception& error) {std::cerr<<"memory-position: "<<error.what()<<'\n';return 1;}
}
