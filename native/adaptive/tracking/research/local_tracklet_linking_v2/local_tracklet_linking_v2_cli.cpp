#include "local_tracklet_linking_v2.hpp"
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
std::vector<std::string> split(const std::string&s){std::vector<std::string>v;std::size_t b=0;for(;;){auto e=s.find('\t',b);v.push_back(s.substr(b,e==std::string::npos?e:e-b));if(e==std::string::npos)return v;b=e+1;}}
double num(const std::string&s){char*e=nullptr;errno=0;double v=std::strtod(s.c_str(),&e);if(errno||e!=s.c_str()+s.size()||!std::isfinite(v))throw std::runtime_error("invalid number");return v;}
template<class T>T integer(const std::string&s){char*e=nullptr;errno=0;long long v=std::strtoll(s.c_str(),&e,10);if(errno||e!=s.c_str()+s.size())throw std::runtime_error("invalid integer");return static_cast<T>(v);}
leo::adaptive::tracking::Candidate candidate(const std::vector<std::string>&f){if(f.size()!=13)throw std::runtime_error("candidate row must have 13 fields");return{f[0],f[1],integer<int>(f[2]),integer<int>(f[3]),f[4],num(f[5]),integer<std::int64_t>(f[6]),integer<std::int64_t>(f[7]),integer<std::int64_t>(f[8]),num(f[9]),num(f[10]),num(f[11]),num(f[12])};}
}
int main(int argc,char**argv){if(argc!=2){std::cerr<<"usage: "<<argv[0]<<" INPUT.tsv\n";return 2;}try{std::ifstream in(argv[1]);if(!in)throw std::runtime_error("cannot open input");std::string line;const std::string header="candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\tsupport_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\tmeasured_cfo_hz\texact_score\tcontrol_score\tmargin";if(!std::getline(in,line)||line!=header)throw std::runtime_error("unsupported header");std::vector<leo::adaptive::tracking::Candidate> v;while(std::getline(in,line))if(!line.empty())v.push_back(candidate(split(line)));auto begin=std::chrono::steady_clock::now();auto r=leo::adaptive::tracking::research::local_tracklet_linking_v2::reconstruct(v);double sec=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();std::cout<<std::setprecision(17)<<"SUMMARY\t"<<r.input_candidate_count<<'\t'<<r.used_candidate_count<<'\t'<<r.tracks.size()<<"\nCONFIG\tresearch:local-linear-tracklets-v2-per-window-diverse-16:8s:4s-overlap:two-pass-chronological-linking:hypothesis-bank:no-exclusive-assignment:gate-2500:link-5000:maxgap-4:minsupport-8:minspan-4:rate-15000\n";std::cerr<<std::setprecision(17)<<"TIMING\treconstruct_s\t"<<sec<<"\nSTATS\t"<<r.stats.lanes<<'\t'<<r.stats.windows<<'\t'<<r.stats.local_seeds<<'\t'<<r.stats.fragments<<'\t'<<r.stats.link_tests<<'\n';for(std::size_t i=0;i<r.tracks.size();++i){auto&t=r.tracks[i];std::cout<<"TRACK\t"<<i<<'\t'<<t.segment_id<<'\t'<<t.tracklet_id<<'\t'<<t.lane.receiver_id<<'\t'<<t.lane.channel<<'\t'<<t.lane.edge<<'\t'<<t.lane.actual_rf_hz<<'\t'<<t.start_utc_ns<<'\t'<<t.end_utc_ns<<'\t'<<t.reference_utc_ns<<'\t'<<t.normalized_rate_hz_per_s<<'\t'<<t.normalized_intercept_hz<<'\t'<<t.residual_rms_hz<<'\t'<<t.residual_max_hz<<'\t'<<t.weighted_support<<'\t'<<t.points.size()<<'\n';for(auto&p:t.points)std::cout<<"POINT\t"<<i<<'\t'<<p.candidate_id<<'\t'<<p.source_group_id<<'\t'<<p.relative_alias_index<<'\t'<<p.normalized_raw_cfo_hz<<'\t'<<p.normalized_dealiased_cfo_hz<<'\n';}return 0;}catch(const std::exception&e){std::cerr<<"local-tracklet-linking-v2: "<<e.what()<<'\n';return 1;}}
