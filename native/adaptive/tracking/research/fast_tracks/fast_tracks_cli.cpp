#include "fast_tracks.hpp"

#include <cerrno>
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
        fields.push_back(line.substr(begin,end==std::string::npos ? end : end-begin));
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
    if(errno || end!=text.c_str()+text.size())
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
    if(argc!=2 && (argc!=4 || std::string(argv[2])!="--max-gap")) {
        std::cerr<<"usage: "<<argv[0]<<" CANDIDATES.tsv [--max-gap 4|8]\n";
        return 2;
    }
    try {
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
        leo::adaptive::tracking::research::fast_tracks::Config config;
        if(argc==4) {
            config.maximum_gap_s=number(argv[3],"maximum gap");
            if(config.maximum_gap_s!=4.0 && config.maximum_gap_s!=8.0)
                throw std::runtime_error("maximum gap must be 4 or 8 seconds");
        }
        const auto result=leo::adaptive::tracking::research::fast_tracks::reconstruct(
            candidates,config);
        std::cout<<std::setprecision(17);
        std::cout<<"SUMMARY\t"<<result.input_candidate_count<<'\t'
            <<result.used_candidate_count<<'\t'<<result.tracks.size()<<'\n';
        std::cout<<"CONFIG\tresearch:bounded-continuity-beam-v1-gap-"
            <<static_cast<unsigned>(config.maximum_gap_s)<<"s\n";
        std::cerr<<"STATS\t"<<result.stats.lanes<<'\t'<<result.stats.source_groups<<'\t'
            <<result.stats.peel_passes<<'\t'<<result.stats.nodes_created<<'\t'
            <<result.stats.maximum_live_beam<<'\t'
            <<result.stats.exact_duplicates_consolidated<<'\n';
        for(std::size_t index=0;index<result.tracks.size();++index) {
            const auto& track=result.tracks[index];
            std::cout<<"TRACK\t"<<index<<"\tresearch-segment-"<<index
                <<"\tresearch-track-"<<index<<'\t'<<track.lane.receiver_id<<'\t'
                <<track.lane.channel<<'\t'<<track.lane.edge<<'\t'<<track.lane.actual_rf_hz<<'\t'
                <<track.start_utc_ns<<'\t'<<track.end_utc_ns<<'\t'<<track.reference_utc_ns<<'\t'
                <<track.normalized_rate_hz_per_s<<'\t'<<track.normalized_intercept_hz<<'\t'
                <<track.residual_rms_hz<<'\t'<<track.residual_max_hz<<'\t'
                <<track.weighted_support<<'\t'<<track.points.size()<<'\n';
            for(const auto& point:track.points)
                std::cout<<"POINT\t"<<index<<'\t'<<point.candidate_id<<'\t'
                    <<point.source_group_id<<'\t'<<point.relative_alias_index<<'\t'
                    <<point.normalized_raw_cfo_hz<<'\t'
                    <<point.normalized_dealiased_cfo_hz<<'\n';
        }
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"fast-tracks: "<<error.what()<<'\n';
        return 1;
    }
}
