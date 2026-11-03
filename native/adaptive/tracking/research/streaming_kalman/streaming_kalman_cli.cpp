#include "streaming_kalman.hpp"

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
std::vector<std::string> split(const std::string& line) { std::vector<std::string> out;
    std::size_t begin=0;for(;;){auto end=line.find('\t',begin);out.push_back(line.substr(begin,
    end==std::string::npos?end:end-begin));if(end==std::string::npos)return out;begin=end+1;} }
template<class T>T integer(const std::string& s,const char* name) { errno=0;char* end=nullptr;
    long long x=std::strtoll(s.c_str(),&end,10);if(errno||end!=s.c_str()+s.size()||
    x<static_cast<long long>(std::numeric_limits<T>::min())||x>static_cast<long long>(
        std::numeric_limits<T>::max()))
        throw std::runtime_error(std::string("invalid ")+name);
    return static_cast<T>(x); }
double number(const std::string& s,const char* name){errno=0;char* end=nullptr;double x=std::strtod(
    s.c_str(),&end);if(errno||end!=s.c_str()+s.size()||!std::isfinite(x))throw std::runtime_error(
    std::string("invalid ")+name);return x;}
leo::adaptive::tracking::Candidate candidate(const std::vector<std::string>& f,std::size_t line) {
    if(f.size()!=13)throw std::runtime_error("line "+std::to_string(line)+" must contain 13 fields");
    return {f[0],f[1],integer<int>(f[2],"receiver"),integer<int>(f[3],"channel"),f[4],
        number(f[5],"RF"),integer<std::int64_t>(f[6],"start"),integer<std::int64_t>(f[7],"center"),
        integer<std::int64_t>(f[8],"end"),number(f[9],"CFO"),number(f[10],"exact"),
        number(f[11],"control"),number(f[12],"margin")}; }
}
int main(int argc,char** argv) {
    if(argc!=2){std::cerr<<"usage: "<<argv[0]<<" CANDIDATES.tsv\n";return 2;}
    try {
        std::ifstream input(argv[1]);if(!input)throw std::runtime_error("cannot open candidate input");
        const std::string header="candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\t"
            "support_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\tmeasured_cfo_hz\t"
            "exact_score\tcontrol_score\tmargin";
        std::string line;if(!std::getline(input,line)||line!=header)throw std::runtime_error("unsupported header");
        std::vector<leo::adaptive::tracking::Candidate> values;std::size_t line_number=1;
        while(std::getline(input,line)){++line_number;if(!line.empty())values.push_back(candidate(split(line),line_number));}
        leo::adaptive::tracking::research::streaming_kalman::Config config;
        auto begin=std::chrono::steady_clock::now();auto result=
            leo::adaptive::tracking::research::streaming_kalman::reconstruct(values,config);
        double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
        std::cout<<std::setprecision(17)<<"SUMMARY\t"<<result.input_candidate_count<<'\t'<<
            result.used_candidate_count<<'\t'<<result.tracks.size()<<"\nCONFIG\tresearch:streaming-kalman-2state-v1"
            ":measurement-sigma-400:acceleration-sigma-60:innovation-gate-5000"
            ":rolling-pair-births:hypothesis-bank:no-exclusive-assignment\n";
        std::cerr<<"INPUT\t"<<argv[1]<<'\t'<<values.size()<<"\nTIMING\treconstruct_s\t"<<seconds<<
            "\nSTATS\t"<<result.stats.lanes<<'\t'<<result.stats.source_groups<<'\t'<<
            result.stats.rolling_births<<'\t'<<result.stats.predictions<<'\t'<<
            result.stats.accepted_updates<<'\t'<<result.stats.missed_detection_branches<<'\t'<<
            result.stats.peak_hypotheses<<'\n';
        for(std::size_t i=0;i<result.tracks.size();++i){const auto& t=result.tracks[i];
            std::cout<<"TRACK\t"<<i<<'\t'<<t.segment_id<<'\t'<<t.tracklet_id<<'\t'<<t.lane.receiver_id<<'\t'<<
            t.lane.channel<<'\t'<<t.lane.edge<<'\t'<<t.lane.actual_rf_hz<<'\t'<<t.start_utc_ns<<'\t'<<
            t.end_utc_ns<<'\t'<<t.reference_utc_ns<<'\t'<<t.normalized_rate_hz_per_s<<'\t'<<
            t.normalized_intercept_hz<<'\t'<<t.residual_rms_hz<<'\t'<<t.residual_max_hz<<'\t'<<
            t.weighted_support<<'\t'<<t.points.size()<<'\n';
            for(const auto& p:t.points)std::cout<<"POINT\t"<<i<<'\t'<<p.candidate_id<<'\t'<<p.source_group_id<<
                '\t'<<p.relative_alias_index<<'\t'<<p.normalized_raw_cfo_hz<<'\t'<<p.normalized_dealiased_cfo_hz<<'\n';}
    } catch(const std::exception& e){std::cerr<<"streaming-kalman: "<<e.what()<<'\n';return 1;}return 0;
}
