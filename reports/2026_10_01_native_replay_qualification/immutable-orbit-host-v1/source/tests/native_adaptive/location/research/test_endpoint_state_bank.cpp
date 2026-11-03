#include "research/heldout_bound.hpp"
#include <cassert>

int main() {
    using leo::location::research::EndpointStateBank;
    using leo::location::research::cannot_win;
    int32_t ids[2]={1,2};leo_orbit_state states[4]{};
    for(auto& state:states) {state.position_km[0]=7000;state.velocity_km_s[1]=7;}
    states[1].position_km[1]=states[3].position_km[1]=70;
    leo_orbit_snapshot s{1,0,0,10,2,2,ids,states};
    double times[6]={2,3,4,5,6,7},measured[6]={0,20,40,60,80,100};
    uint8_t mask[6]={0,1,0,1,1,0};
    leo_location_track track{1,6,5,times,measured,mask};
    auto c=leo_score_default_config();c.tau_first_s=-2;c.tau_last_s=2;
    EndpointStateBank bank(sizeof(EndpointStateBank::Block));
    assert(bank.prepare(s,&track,1,c,0,2));
    auto* block=bank.block(0,0);assert(block && !block->valid);
    assert(!bank.block(0,1)); // Exact bounded-capacity fallback.
    assert(!bank.block(1,0) && !bank.block(0,2));
    leo_location_site site{{6378,0,0},{1,0,0}};
    leo_track_score incumbent{1,2,0,1,1,0};
    for(unsigned position=0;position<3;++position) {
        site.ecef_km[1]=position*10;
        for(unsigned rms=0;rms<=20000;rms+=100) {
            incumbent.heldout_rms_hz=rms;
            assert(cannot_win(s,0,track,site,c,3,incumbent)==
                cannot_win(s,0,track,site,c,3,incumbent,nullptr,nullptr,nullptr,block));
        }
    }
    assert(block->valid);
    assert(bank.prepare(s,&track,1,c,0,2) && bank.block(0,0)->valid);
    // Unchanged generation does not hide an authority mutation.
    states[0].position_km[0]+=1;
    assert(bank.prepare(s,&track,1,c,0,2) && !bank.block(0,0)->valid);
    auto mark=[&] {bank.block(0,0)->valid=1;};
    mark();times[0]+=.25;
    assert(bank.prepare(s,&track,1,c,0,2) && !bank.block(0,0)->valid);
    mark();mask[0]=1;
    assert(bank.prepare(s,&track,1,c,0,2) && !bank.block(0,0)->valid);
    mark();c.tau_step_s=2;
    assert(bank.prepare(s,&track,1,c,0,2) && !bank.block(0,0)->valid);
    mark();s.generation++;
    assert(bank.prepare(s,&track,1,c,0,2) && !bank.block(0,0)->valid);
    mark();s.knot_step_s=11;
    assert(bank.prepare(s,&track,1,c,0,2) && !bank.block(0,0)->valid);
    assert(bank.prepare(s,&track,1,c,1,2) && !bank.block(0,0) && !bank.block(0,1)->valid);
    assert(bank.prepare(s,&track,1,c,0,2,true));mark();
    assert(bank.prepare(s,&track,1,c,0,2,true) && bank.block(0,0)->valid);
    // Ending a declared immutable lifetime invalidates even a reused address.
    bank.invalidate();states[0].position_km[0]+=2;
    assert(bank.prepare(s,&track,1,c,0,2,true) && !bank.block(0,0)->valid);
    mark();assert(bank.prepare(s,&track,1,c,0,2,false) && !bank.block(0,0)->valid);
    mark();states[0].position_km[0]+=3;
    assert(bank.prepare(s,&track,1,c,0,2,false) && !bank.block(0,0)->valid);
    c.tau_last_s=100;assert(!bank.prepare(s,&track,1,c,0,2));
    EndpointStateBank disabled(0);assert(!disabled.prepare(s,&track,1,c,0,2));
}
