#include "curvature_tracks.hpp"

#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
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

}  // namespace

int main(int argc,char** argv) {
    if(argc!=2 && (argc!=4 || std::string(argv[2])!="--acceleration")) {
        std::cerr<<"usage: "<<argv[0]<<" CANDIDATES.tsv [--acceleration 0|125|250|500]\n";
        return 2;
    }
    try {
        leo::adaptive::tracking::research::curvature_tracks::Config config;
        if(argc==4) {
            config.maximum_acceleration_hz_per_s2=number(argv[3],"acceleration");
            if(config.maximum_acceleration_hz_per_s2!=0.0 &&
               config.maximum_acceleration_hz_per_s2!=125.0 &&
               config.maximum_acceleration_hz_per_s2!=250.0 &&
               config.maximum_acceleration_hz_per_s2!=500.0)
                throw std::runtime_error("acceleration must be 0, 125, 250, or 500");
        }
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
        const auto begin=std::chrono::steady_clock::now();
        const auto result=leo::adaptive::tracking::research::curvature_tracks::reconstruct(
            candidates,config);
        const double seconds=std::chrono::duration<double>(
            std::chrono::steady_clock::now()-begin).count();
        std::cout<<std::setprecision(17);
        std::cout<<"SUMMARY\t"<<result.input_candidate_count<<'\t'
            <<result.used_candidate_count<<'\t'<<result.tracks.size()<<'\n';
        std::cout<<"CONFIG\tresearch:bounded-curvature-local-state-v1-a-"
            <<config.maximum_acceleration_hz_per_s2
            <<":track-fields-linear-compatibility-summary\n";
        std::cerr<<"TIMING\treconstruct_s\t"<<seconds<<'\n';
        std::cerr<<"STATS\t"<<result.stats.lanes<<'\t'<<result.stats.source_groups<<'\t'
            <<result.stats.seeds_considered<<'\t'<<result.stats.seeds_retained<<'\t'
            <<result.stats.states_evaluated<<'\t'
            <<result.stats.exact_hypotheses_consolidated<<'\t'
            <<result.stats.near_hypotheses_consolidated<<'\n';
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
