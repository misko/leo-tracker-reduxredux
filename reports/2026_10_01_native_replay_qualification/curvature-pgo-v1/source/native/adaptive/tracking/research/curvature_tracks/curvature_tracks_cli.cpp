#include "curvature_tracks.hpp"

#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<std::string> split_tabs(const std::string& line) {
    std::vector<std::string> fields;
    std::size_t begin=0;
    for(;;) {
        const auto end=line.find('\t',begin);
        fields.push_back(line.substr(begin,end==std::string::npos ? end:end-begin));
        if(end==std::string::npos) return fields;
        begin=end+1;
    }
}

template <typename Integer>
Integer integer(const std::string& text,const char* name) {
    errno=0;char* end=nullptr;
    const long long value=std::strtoll(text.c_str(),&end,10);
    if(errno || end!=text.c_str()+text.size() ||
       value<static_cast<long long>(std::numeric_limits<Integer>::min()) ||
       value>static_cast<long long>(std::numeric_limits<Integer>::max()))
        throw std::runtime_error(std::string("invalid ")+name);
    return static_cast<Integer>(value);
}

double number(const std::string& text,const char* name) {
    errno=0;char* end=nullptr;
    const double value=std::strtod(text.c_str(),&end);
    if(errno || end!=text.c_str()+text.size() || !std::isfinite(value))
        throw std::runtime_error(std::string("invalid ")+name);
    return value;
}

leo::adaptive::tracking::Candidate candidate(const std::vector<std::string>& fields,
                                              std::size_t line) {
    if(fields.size()!=13) throw std::runtime_error(
        "line "+std::to_string(line)+" must contain 13 tab-separated fields");
    return {fields[0],fields[1],integer<int>(fields[2],"receiver"),
        integer<int>(fields[3],"channel"),fields[4],number(fields[5],"RF"),
        integer<std::int64_t>(fields[6],"support start"),
        integer<std::int64_t>(fields[7],"support center"),
        integer<std::int64_t>(fields[8],"support end"),number(fields[9],"CFO"),
        number(fields[10],"exact score"),number(fields[11],"control score"),
        number(fields[12],"margin")};
}

std::vector<leo::adaptive::tracking::research::curvature_tracks::SeedTrack>
read_seeds(const std::string& path) {
    using SeedTrack=leo::adaptive::tracking::research::curvature_tracks::SeedTrack;
    std::ifstream input(path);
    if(!input) throw std::runtime_error("cannot open seed track input");
    std::vector<SeedTrack> seeds;
    std::map<std::size_t,std::size_t> positions;
    std::string line;
    std::size_t line_number=0;
    while(std::getline(input,line)) {
        ++line_number;
        const auto fields=split_tabs(line);
        if(fields.empty()) continue;
        if(fields[0]=="TRACK") {
            if(fields.size()!=17) throw std::runtime_error(
                "seed TRACK line "+std::to_string(line_number)+" must contain 17 fields");
            const auto signed_index=integer<std::int64_t>(fields[1],"seed track index");
            if(signed_index<0) throw std::runtime_error("negative seed track index");
            const std::size_t index=static_cast<std::size_t>(signed_index);
            if(!positions.emplace(index,seeds.size()).second)
                throw std::runtime_error("duplicate seed track index");
            seeds.push_back({{integer<int>(fields[5],"seed channel"),fields[6],
                integer<int>(fields[4],"seed receiver"),number(fields[7],"seed RF")},{}});
        } else if(fields[0]=="POINT") {
            if(fields.size()!=7) throw std::runtime_error(
                "seed POINT line "+std::to_string(line_number)+" must contain 7 fields");
            const auto signed_index=integer<std::int64_t>(fields[1],
                "seed point track index");
            if(signed_index<0) throw std::runtime_error("negative seed point track index");
            const std::size_t index=static_cast<std::size_t>(signed_index);
            auto position=positions.find(index);
            if(position==positions.end())
                throw std::runtime_error("seed POINT precedes its TRACK");
            seeds[position->second].points.push_back({fields[2],number(fields[6],
                "seed dealiased CFO")});
        }
    }
    if(seeds.empty()) throw std::runtime_error("seed track input is empty");
    return seeds;
}

}  // namespace

int main(int argc,char** argv) {
    if(argc<2) {
        std::cerr<<"usage: "<<argv[0]<<" CANDIDATES.tsv [--acceleration 0|125|250|500] "
                 <<"[--seeds COARSE.tsv] [--retain-originals]\n";
        return 2;
    }
    try {
        leo::adaptive::tracking::research::curvature_tracks::Config config;
        std::string seed_path;
        bool retain_originals=false;
        for(int argument=2;argument<argc;++argument) {
            const std::string option=argv[argument];
            if(option=="--acceleration" && argument+1<argc) {
                config.maximum_acceleration_hz_per_s2=number(argv[++argument],"acceleration");
            } else if(option=="--seeds" && argument+1<argc) {
                seed_path=argv[++argument];
            } else if(option=="--retain-originals") {
                retain_originals=true;
            } else throw std::runtime_error("unknown or incomplete option");
        }
        if(config.maximum_acceleration_hz_per_s2!=0.0 &&
           config.maximum_acceleration_hz_per_s2!=125.0 &&
           config.maximum_acceleration_hz_per_s2!=250.0 &&
           config.maximum_acceleration_hz_per_s2!=500.0)
            throw std::runtime_error("acceleration must be 0, 125, 250, or 500");
        if(retain_originals && seed_path.empty())
            throw std::runtime_error("--retain-originals requires --seeds");
        std::ifstream input(argv[1]);
        if(!input) throw std::runtime_error("cannot open candidate input");
        std::string line;
        const std::string header="candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\t"
            "actual_rf_hz\tsupport_start_utc_ns\tsupport_center_utc_ns\t"
            "support_end_utc_ns\tmeasured_cfo_hz\texact_score\tcontrol_score\tmargin";
        if(!std::getline(input,line) || line!=header)
            throw std::runtime_error("candidate input has an unsupported header");
        std::vector<leo::adaptive::tracking::Candidate> candidates;
        std::size_t line_number=1;
        while(std::getline(input,line)) {
            ++line_number;
            if(!line.empty()) candidates.push_back(candidate(split_tabs(line),line_number));
        }
        const auto seeds=seed_path.empty()
            ? std::vector<leo::adaptive::tracking::research::curvature_tracks::SeedTrack>{}
            : read_seeds(seed_path);
        const auto begin=std::chrono::steady_clock::now();
        const auto result=seeds.empty()
            ? leo::adaptive::tracking::research::curvature_tracks::reconstruct(candidates,config)
            : leo::adaptive::tracking::research::curvature_tracks::reconstruct_seeded(
                candidates,seeds,retain_originals,config);
        const double seconds=std::chrono::duration<double>(
            std::chrono::steady_clock::now()-begin).count();
        std::cout<<std::setprecision(17);
        std::cout<<"SUMMARY\t"<<result.input_candidate_count<<'\t'
            <<result.used_candidate_count<<'\t'<<result.tracks.size()<<'\n';
        std::cout<<"CONFIG\tresearch:bounded-curvature-local-state-v2-"
            <<(seeds.empty()?"local-pair-seeds":"native-coarse-seeds")<<"-a-"
            <<config.maximum_acceleration_hz_per_s2
            <<(retain_originals?":retained-original-alternatives":"")
            <<":hypothesis-bank:no-exclusive-assignment"
            <<":track-fields-linear-compatibility-summary\n";
        std::cerr<<"TIMING\treconstruct_s\t"<<seconds<<'\n';
        std::cerr<<"STATS\t"<<result.stats.lanes<<'\t'<<result.stats.source_groups<<'\t'
            <<result.stats.seeds_considered<<'\t'<<result.stats.seeds_retained<<'\t'
            <<result.stats.states_evaluated<<'\t'
            <<result.stats.exact_hypotheses_consolidated<<'\t'
            <<result.stats.near_hypotheses_consolidated<<'\t'
            <<result.stats.external_seed_tracks<<'\t'
            <<result.stats.retained_original_alternatives<<'\n';
        for(std::size_t index=0;index<result.tracks.size();++index) {
            const auto& item=result.tracks[index];
            const auto& track=item.compatibility_linear_summary;
            std::cout<<"TRACK\t"<<index<<'\t'<<track.segment_id<<'\t'
                <<track.tracklet_id<<'\t'<<track.lane.receiver_id<<'\t'
                <<track.lane.channel<<'\t'<<track.lane.edge<<'\t'
                <<track.lane.actual_rf_hz<<'\t'<<track.start_utc_ns<<'\t'
                <<track.end_utc_ns<<'\t'<<track.reference_utc_ns<<'\t'
                <<track.normalized_rate_hz_per_s<<'\t'
                <<track.normalized_intercept_hz<<'\t'<<track.residual_rms_hz<<'\t'
                <<track.residual_max_hz<<'\t'<<track.weighted_support<<'\t'
                <<track.points.size()<<'\n';
            for(const auto& point:track.points)
                std::cout<<"POINT\t"<<index<<'\t'<<point.candidate_id<<'\t'
                    <<point.source_group_id<<'\t'<<point.relative_alias_index<<'\t'
                    <<point.normalized_raw_cfo_hz<<'\t'
                    <<point.normalized_dealiased_cfo_hz<<'\n';
        }
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"curvature-tracks: "<<error.what()<<'\n';
        return 1;
    }
}
