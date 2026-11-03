#include "session.hpp"
#include <cassert>
#include <cmath>
#include <cstring>
#include <thread>

struct Progress {
    std::thread::id caller=std::this_thread::get_id();
    unsigned points=0,associations=0;
};
int main() {
    using namespace leo::adaptive::location;
    int32_t ids[2]={11,22};leo_orbit_state states[4]{};
    for(auto& state:states)state.position_km[0]=7000;
    leo_orbit_snapshot orbit{1,123,-60,360,2,2,ids,states};
    double times[6]={0,1,2,3,4,5},measured[6]={0,1,2,3,4,5};
    uint8_t training[6]={1,1,1,0,0,0};
    leo_location_track track{7,6,10,times,measured,training};
    auto before=states[0];SearchOptions options{0,0,250,1,true};SearchOutput serial,parallel;
    Progress p;
    auto callback=[](void* opaque,const SearchProgress& event) {
        auto& p=*static_cast<Progress*>(opaque);
        assert(std::this_thread::get_id()==p.caller && event.wall_s>=0);
        if(event.associations)++p.associations;
        else assert(event.sequence==p.points++);
    };
    LocationInputView input{&orbit,&track,1};
    assert(search_location(input,options,serial,callback,&p)==LEO_LOCATION_OK);
    assert(p.points==400 && p.associations==1 && serial.evaluations.size()==400);
    assert(serial.result.has_incumbent && serial.associations.size()==1);
    assert(std::abs(serial.selected_score.residual_rmse_hz-std::sqrt(29.0/3))<1e-12);
    assert(std::memcmp(&before,&states[0],sizeof(before))==0 && measured[5]==5);
    options.workers=2;
    assert(search_location(input,options,parallel)==LEO_LOCATION_OK);
    assert(parallel.evaluations.size()==serial.evaluations.size());
    for(size_t i=0;i<serial.evaluations.size();++i) {
        const auto& a=serial.evaluations[i];const auto& b=parallel.evaluations[i];
        assert(a.east_km==b.east_km && a.north_km==b.north_km && a.weighted_mse_hz2==b.weighted_mse_hz2);
    }
    assert(serial.associations[0].candidate_id==parallel.associations[0].candidate_id);
    assert(serial.associations[0].tau_s==parallel.associations[0].tau_s);
    const auto saved=parallel.result.evaluated_points;
    options.workers=3;
    assert(search_location(input,options,parallel)==LEO_LOCATION_INVALID);
    assert(parallel.result.evaluated_points==saved);
    options.workers=1;options.full_associations=false;
    assert(search_location(input,options,parallel)==LEO_LOCATION_OK && parallel.associations.empty());
    auto fail=[](void*,const SearchProgress&){throw 1;};
    assert(search_location(input,options,parallel,fail)==LEO_LOCATION_STATE);
    assert(parallel.result.evaluated_points==saved && parallel.associations.empty());
    orbit.states=nullptr;
    assert(search_location(input,options,parallel)==LEO_LOCATION_INVALID);
}
