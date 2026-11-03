// Preparation-only diagnostic using the same public ports as in_memory_cli.
#include "checkpoint_input.hpp"
#include "track_input.hpp"
#include "selection.hpp"
#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sys/resource.h>

namespace {
using Clock=std::chrono::steady_clock;
double cpu(){rusage r{};if(getrusage(RUSAGE_SELF,&r))throw std::runtime_error("CPU clock failed");
    return r.ru_utime.tv_sec+r.ru_stime.tv_sec+(r.ru_utime.tv_usec+r.ru_stime.tv_usec)*1e-6;}
template<class F> auto stage(const char* name,F run){
    auto start=Clock::now();const double before=cpu();auto result=run();
    std::cerr<<std::setprecision(17)<<"{\"stage\":\""<<name<<"\",\"wall_s\":"
             <<std::chrono::duration<double>(Clock::now()-start).count()<<",\"cpu_s\":"<<cpu()-before<<"}\n";
    return result;
}
}
int main(int argc,char** argv){try{
    if(argc!=4)throw std::runtime_error("usage: preparation-bench OBSERVATIONS GRAPH TRACKS");
    std::ifstream observations_input(argv[1]),graph_input(argv[2]),track_input(argv[3]);
    if(!observations_input||!graph_input||!track_input)throw std::runtime_error("missing input");
    const auto observations=stage("read_observations",[&]{return leo::adaptive::pipeline::checkpoint::read_candidates(observations_input);});
    const auto authority=stage("read_support",[&]{return leo::adaptive::pipeline::checkpoint::read_authority(graph_input);});
    const auto hypotheses=stage("read_tracks",[&]{return leo::adaptive::pipeline::read_track_checkpoint(track_input,observations);});
    leo::adaptive::pipeline::SelectionAudit audit;
    const auto selected=stage("select",[&]{return leo::adaptive::pipeline::select_exclusive_candidates(hypotheses,observations,audit);});
    const auto batch=stage("location_tracks",[&]{return leo::adaptive::pipeline::make_location_tracks(selected,authority);});
    // Serialize every public output value for exact control/candidate comparison.
    std::cout<<std::setprecision(17)<<"AUTHORITY\t"<<authority.session_id<<'\t'<<authority.input_manifest_digest<<'\t'<<authority.session_start_utc_ns<<'\n';
    std::cout<<"AUDIT\t"<<audit.input_tracks<<'\t'<<audit.output_tracks<<'\t'
             <<audit.reused_memberships_removed<<'\t'<<audit.insufficient_memberships_removed<<'\n';
    for(size_t i=0;i<batch.records.size();++i){const auto& r=batch.records[i];const auto& o=batch.owned[i];
        std::cout<<"TRACK\t"<<r.track_key<<'\t'<<r.observation_count<<'\t'<<r.weight_s<<'\t'
                 <<o.tracklet_id<<'\t'<<o.support_digest<<'\t'<<o.partition_seed<<'\n';
        for(size_t j=0;j<r.observation_count;++j)
            std::cout<<"POINT\t"<<o.observation_ids[j]<<'\t'<<r.times_s[j]<<'\t'<<r.measured_hz[j]<<'\t'<<int(r.training_mask[j])<<'\n';
    }
    if(!std::cout)throw std::runtime_error("output failed");return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}}
