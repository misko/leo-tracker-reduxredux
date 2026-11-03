#include "pipeline.hpp"
#include "track_input.hpp"
#include "selection.hpp"
#include "checkpoint_input.hpp"

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

std::vector<leo::adaptive::tracking::Candidate> candidates(const std::string& path) {
    std::ifstream input(path);
    if(!input)throw std::runtime_error("cannot open candidates");
    return leo::adaptive::pipeline::checkpoint::read_candidates(input);
}
leo::adaptive::pipeline::GraphAuthority authority(const std::string& path) {
    std::ifstream input(path);
    if(!input)throw std::runtime_error("cannot open graph authority");
    return leo::adaptive::pipeline::checkpoint::read_authority(input);
}

}  // namespace

int main(int argc,char** argv) {
    if(argc==4 && std::string(argv[1])=="--validate-tracks") {
        try {
            const auto observations=candidates(argv[2]);
            std::ifstream supplied(argv[3]);
            if(!supplied)throw std::runtime_error("cannot open supplied track checkpoint");
            const auto parsed=leo::adaptive::pipeline::read_track_checkpoint(supplied,observations);
            std::cout<<"{\"tracks\":"<<parsed.tracks.size()<<",\"used_candidates\":"
                     <<parsed.used_candidate_count<<"}\n";
            return 0;
        } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
    }
    if(argc!=5 && !((argc==7 || (argc==8 && std::string(argv[7])=="--exclusive-candidates")) && std::string(argv[5])=="--tracks")) {
        std::cerr<<"usage: "<<argv[0]<<" CANDIDATES.tsv GRAPH.tsv AUTHORITY.loc1 OUTPUT.loc1 [--tracks TRACKS.tsv [--exclusive-candidates]]\n";
        return 2;
    }
    try {
        const auto observations=candidates(argv[1]);
        auto reconstructed=leo::adaptive::tracking::Result{};
        if(argc>=7) {
            std::ifstream supplied(argv[6]);
            if(!supplied)throw std::runtime_error("cannot open supplied track checkpoint");
            reconstructed=leo::adaptive::pipeline::read_track_checkpoint(supplied,observations);
        } else reconstructed=leo::adaptive::tracking::reconstruct(observations);
        if(argc==8) {
            leo::adaptive::pipeline::SelectionAudit audit;
            reconstructed=leo::adaptive::pipeline::select_exclusive_candidates(reconstructed,observations,audit);
            std::cerr<<"{\"selection\":\"exclusive-candidates-longest-v1\",\"input_tracks\":"<<audit.input_tracks
                     <<",\"output_tracks\":"<<audit.output_tracks<<",\"reused_memberships_removed\":"
                     <<audit.reused_memberships_removed<<",\"insufficient_memberships_removed\":"
                     <<audit.insufficient_memberships_removed<<"}\n";
        }
        const auto location=leo::adaptive::pipeline::make_location_tracks(
            reconstructed,authority(argv[2]));
        leo::adaptive::pipeline::write_loc1(argv[3],argv[4],location);
        std::ofstream evidence(std::string(argv[4])+".tracks.tsv");
        if(!evidence) throw std::runtime_error("cannot open pipeline evidence output");
        evidence<<std::setprecision(17);
        for(std::size_t track=0;track<location.owned.size();++track) {
            const auto& item=location.owned[track];
            evidence<<"TRACK\t"<<track<<'\t'<<item.tracklet_id<<'\t'<<item.support_digest
                    <<'\t'<<item.partition_seed<<'\t'<<item.observation_ids.size()<<'\n';
            for(std::size_t point=0;point<item.observation_ids.size();++point)
                evidence<<"POINT\t"<<track<<'\t'<<item.observation_ids[point]<<'\t'
                        <<item.times_s[point]<<'\t'<<item.measured_hz[point]<<'\t'
                        <<static_cast<unsigned>(item.training_mask[point])<<'\n';
        }
        if(!evidence) throw std::runtime_error("pipeline evidence write failed");
        if(argc==8) {
            std::ofstream memberships(std::string(argv[4])+".members.tsv");
            if(!memberships)throw std::runtime_error("cannot open selected membership evidence");
            memberships<<"track_index\tcandidate_id\tsource_group_id\talias\n";
            for(std::size_t i=0;i<reconstructed.tracks.size();++i)
                for(const auto& p:reconstructed.tracks[i].points)
                    memberships<<i<<'\t'<<p.candidate_id<<'\t'<<p.source_group_id<<'\t'<<p.relative_alias_index<<'\n';
            if(!memberships)throw std::runtime_error("selected membership evidence write failed");
        }
        std::size_t observation_count=0,training=0;
        for(const auto& item:location.owned) {
            observation_count+=item.observation_ids.size();
            for(auto selected:item.training_mask)training+=selected;
        }
        std::cout<<"tracks="<<location.owned.size()<<" observations="<<observation_count
                 <<" training="<<training<<" output="<<argv[4]<<'\n';
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"pipeline: "<<error.what()<<'\n';return 1;
    }
}
