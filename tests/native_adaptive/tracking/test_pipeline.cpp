#include "pipeline.hpp"
#include "track_input.hpp"
#include "selection.hpp"
#include "checkpoint_input.hpp"

#include <cstdint>
#include <iostream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
std::string identity(int value){std::ostringstream out;out<<"sha256:"<<std::hex
    <<std::setfill('0')<<std::setw(64)<<value;return out.str();}
}

int main() {
    try {
        {
            const std::string row="id\tsource\t0\t3\tlower\t11200000000\t100\t200\t300\t10\t0.5\t0.1\t0.4\n";
            std::istringstream source("header\n"+row);
            const auto parsed=leo::adaptive::pipeline::checkpoint::read_candidates(source);
            require(parsed.size()==1 && parsed[0].candidate_id=="id" && parsed[0].measured_cfo_hz==10,
                    "checkpoint reader changed observation");
            for(const auto& replacement:std::vector<std::string>{"nan",""}) {
                auto bad=row;const auto at=bad.find("\t10\t");bad.replace(at+1,2,replacement);
                bool rejected=false;
                try {std::istringstream input("header\n"+bad);(void)leo::adaptive::pipeline::checkpoint::read_candidates(input);}
                catch(const std::exception&){rejected=true;}
                require(rejected,"invalid numerical checkpoint accepted");
            }
            const std::string graph="META\tsession\tdigest\t100\nheader\nid\t100\t200\t300\t1.0\t0\t1e-5\t0\n";
            std::istringstream graph_input(graph);
            const auto authority=leo::adaptive::pipeline::checkpoint::read_authority(graph_input);
            require(authority.candidates.at("id").moment2=="1e-5","support spelling changed");
            bool rejected=false;
            try {std::istringstream duplicate(graph+"id\t100\t200\t300\t1\t0\t0\t0\n");
                (void)leo::adaptive::pipeline::checkpoint::read_authority(duplicate);}
            catch(const std::exception&){rejected=true;}
            require(rejected,"duplicate support ID accepted");
        }
        constexpr std::int64_t base=1'800'000'000'000'000'000LL;
        std::vector<leo::adaptive::tracking::Candidate> input;
        leo::adaptive::pipeline::GraphAuthority authority{
            "session-1","sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",base,{}};
        for(int i=0;i<7;++i) {
            const auto center=base+static_cast<std::int64_t>(i)*600'000'000;
            const std::string id=identity(i+1);
            input.push_back({id,identity(i+101),0,1,"lower",11'200'000'000.0,
                center-10'000'000,center,center+10'000'000,10'000.0+500.0*i,1.0,0.2,0.8});
            authority.candidates.emplace(id,leo::adaptive::pipeline::SupportAuthority{
                center-10'000'000,center,center+10'000'000,"1.0","0.0","1e-05","0.0"});
        }
        const auto tracks=leo::adaptive::tracking::reconstruct(input);
        const auto batch=leo::adaptive::pipeline::make_location_tracks(tracks,authority);
        require(batch.records.size()==1,"location track count differs");
        require(batch.records[0].observation_count==7,"location support differs");
        require(batch.records[0].weight_s==4,"one-second weight differs");
        unsigned training=0;for(auto value:batch.owned[0].training_mask)training+=value;
        require(training==4,"training partition size differs");
        require(batch.owned[0].support_digest.size()==71,"support identity absent");
        require(batch.owned[0].partition_seed.size()==71,"partition identity absent");
        std::ostringstream checkpoint;
        checkpoint<<"SUMMARY\t7\t7\t1\nCONFIG\tresearch-swappable-tracker\n";
        checkpoint<<"TRACK\t0\toriginal-segment\toriginal-track\t0\t1\tlower\t11200000000\t"
                  <<input.front().support_start_utc_ns<<'\t'<<input.back().support_end_utc_ns
                  <<'\t'<<base<<"\t500\t10000\t0\t0\t7\t7\n";
        for(const auto& point:input)checkpoint<<"POINT\t0\t"<<point.candidate_id<<'\t'
            <<point.source_group_id<<"\t0\t"<<point.measured_cfo_hz<<'\t'<<point.measured_cfo_hz<<'\n';
        std::istringstream stream(checkpoint.str());
        const auto supplied=leo::adaptive::pipeline::read_track_checkpoint(stream,input);
        const auto supplied_batch=leo::adaptive::pipeline::make_location_tracks(supplied,authority);
        require(supplied_batch.records.size()==1 && supplied_batch.records[0].observation_count==7,
                "supplied memberships were not retained");
        for(std::size_t i=0;i<input.size();++i)
            require(supplied_batch.owned[0].measured_hz[i]==input[i].measured_cfo_hz,"supplied measurement changed");
        auto corrupt=checkpoint.str();
        const auto at=corrupt.find("\t10000\t10000\n");
        require(at!=std::string::npos,"test mutation missing");
        corrupt.replace(at,13,"\t9999\t10000\n");
        bool rejected=false;
        try {std::istringstream bad(corrupt);(void)leo::adaptive::pipeline::read_track_checkpoint(bad,input);}
        catch(const std::invalid_argument&){rejected=true;}
        require(rejected,"changed raw measurement accepted");
        leo::adaptive::pipeline::SelectionAudit audit;
        const auto too_short=leo::adaptive::pipeline::select_exclusive_candidates(supplied,input,audit);
        require(too_short.tracks.empty() && audit.insufficient_memberships_removed==7,
                "minimum independent fragment support not enforced");
        auto extended_input=input;
        auto extra=input.back();extra.candidate_id=identity(1000);extra.source_group_id=identity(1001);
        extra.support_start_utc_ns+=600'000'000;extra.support_center_utc_ns+=600'000'000;
        extra.support_end_utc_ns+=600'000'000;extra.measured_cfo_hz+=500;
        extended_input.push_back(extra);
        auto duplicated=supplied;auto tr=duplicated.tracks.front();
        tr.points.push_back({extra.candidate_id,extra.source_group_id,0,extra.measured_cfo_hz,extra.measured_cfo_hz});
        tr.end_utc_ns=extra.support_end_utc_ns;duplicated.tracks={tr,tr};duplicated.input_candidate_count=8;
        const auto exclusive=leo::adaptive::pipeline::select_exclusive_candidates(duplicated,extended_input,audit);
        require(exclusive.tracks.size()==1 && exclusive.used_candidate_count==8 && audit.reused_memberships_removed==8,
                "duplicate hypothesis counted as independent evidence");
        require(exclusive.tracks.front().points.size()==8,"exclusive selection changed unique membership");
        std::cout<<"pipeline unit tests passed\n";return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
