#include "research/heldout_bound.hpp"
#include <cassert>
#include <limits>
int main() {
    using leo::location::research::pair_cannot_win;
    assert(!pair_cannot_win(0,100,1,1));
    assert(!pair_cannot_win(0,100,2,50)); // A tie must survive.
    assert(pair_cannot_win(0,100,2,49));
    assert(!pair_cannot_win(0,100,2,std::numeric_limits<double>::infinity()));
    assert(!pair_cannot_win(0,std::numeric_limits<double>::quiet_NaN(),2,1));
    for(int a=-50;a<=50;a+=5) for(int b=-50;b<=50;b+=5)
        for(int offset=-100;offset<=100;offset+=5) {
            double actual=std::sqrt(((a-offset)*(a-offset)+(b-offset)*(b-offset))/2.0);
            assert(!pair_cannot_win(a,b,2,actual));
        }
    int32_t id=1;
    leo_orbit_state states[2]{};
    states[0].position_km[0]=states[1].position_km[0]=7000;
    leo_orbit_snapshot snapshot{1,0,0,10,1,2,&id,states};
    leo_location_site site{{6378,0,0},{1,0,0}};
    auto config=leo_score_default_config();config.tau_first_s=config.tau_last_s=0;
    double times[6]={0,1,2,3,4,5}, measured[6]={0,0,0,0,0,100};
    uint8_t mask[6]={0,1,1,1,1,0};
    leo_location_track track{1,6,5,times,measured,mask};
    leo_track_score incumbent{1,2,0,1,1,0};
    using leo::location::research::cannot_win;
    using leo::location::research::bounded_snapshot;
    assert(bounded_snapshot(snapshot,site,config));
    assert(cannot_win(snapshot,0,track,site,config,2,incumbent));
    incumbent.heldout_rms_hz=80;
    assert(!cannot_win(snapshot,0,track,site,config,2,incumbent));
    incumbent.matched=0;
    assert(!cannot_win(snapshot,0,track,site,config,2,incumbent));
    states[1].position_km[0]=std::numeric_limits<double>::quiet_NaN();
    assert(!bounded_snapshot(snapshot,site,config));
}
