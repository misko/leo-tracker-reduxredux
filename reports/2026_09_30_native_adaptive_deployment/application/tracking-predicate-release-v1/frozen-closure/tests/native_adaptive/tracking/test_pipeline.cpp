#include "pipeline.hpp"

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
        std::cout<<"pipeline unit tests passed\n";return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
