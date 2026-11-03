#include "research/immutable_orbit.hpp"
#include <cassert>
#include <limits>

int main() {
    using namespace leo::location::research;
    int32_t ids[2]={1,2};leo_orbit_state states[4]{};
    for(auto& s:states){s.position_km[0]=7000;s.velocity_km_s[1]=7;}
    states[1].position_km[1]=states[3].position_km[1]=70;
    leo_orbit_snapshot snapshot{1,0,0,10,2,2,ids,states};
    auto* context=leo_score_context_create(6,11);
    auto* control=leo_score_context_create(6,11);assert(context && control);
    assert(!immutable_orbit_matches(context,&snapshot));
    assert(bind_immutable_orbit(context,&snapshot));
    assert(immutable_orbit_matches(context,&snapshot));
    auto changed=snapshot;changed.generation++;
    assert(!immutable_orbit_matches(context,&changed));
    changed=snapshot;changed.knot_step_s=11;
    assert(!immutable_orbit_matches(context,&changed));
    changed=snapshot;changed.start_utc_ns++;
    assert(!immutable_orbit_matches(context,&changed));
    leo_orbit_state copy[4];for(unsigned i=0;i<4;++i)copy[i]=states[i];
    changed=snapshot;changed.states=copy;
    assert(!immutable_orbit_matches(context,&changed));
    double times[6]={2,3,4,5,6,7},measured[6]={0,20,40,60,80,100};
    uint8_t mask[6]={0,1,0,1,1,0};leo_location_track track{1,6,5,times,measured,mask};
    auto config=leo_score_default_config();config.tau_first_s=-2;config.tau_last_s=2;
    leo_location_site site{{6378,0,0},{1,0,0}};
    auto compare=[&](const leo_orbit_snapshot& s) {
        // Seed a finite bound threshold so the endpoint bank is exercised.
        leo_track_score a{1,INT32_MAX,0,800,1e30,0},b=a;
        auto sa=leo_score_partition(context,&s,&track,1,&site,&config,0,2,&a,nullptr);
        auto sb=leo_score_partition(control,&s,&track,1,&site,&config,0,2,&b,nullptr);
        assert(sa==sb);
        assert(a.matched==b.matched && a.candidate_id==b.candidate_id && a.tau_s==b.tau_s &&
               a.heldout_rms_hz==b.heldout_rms_hz && a.training_rms_hz==b.training_rms_hz &&
               a.frequency_offset_hz==b.frequency_offset_hz);
        return a;
    };
    compare(snapshot);site.ecef_km[1]=20;compare(snapshot);
    // A different authority uses normal validation until explicitly bound.
    compare(changed);assert(bind_immutable_orbit(context,&changed));compare(changed);
    assert(bind_immutable_orbit(context,nullptr));
    copy[0].position_km[0]+=10;compare(changed);
    assert(bind_immutable_orbit(context,&changed));compare(changed);
    assert(bind_immutable_orbit(context,nullptr));
    for(auto& state:copy){state={};state.position_km[0]=7000;}
    for(auto& value:measured)value=0;
    assert(bind_immutable_orbit(context,&changed));
    const auto perfect=compare(changed);
    assert(perfect.matched && perfect.candidate_id==1 && perfect.heldout_rms_hz==0);
    // Rebinding ends the previous lifetime, even at the same address/version.
    assert(bind_immutable_orbit(context,nullptr));copy[1].position_km[0]+=20;
    assert(bind_immutable_orbit(context,&changed));compare(changed);
    changed.states=nullptr;assert(!bind_immutable_orbit(context,&changed));
    assert(!immutable_orbit_matches(context,&snapshot));
    assert(!bind_immutable_orbit(nullptr,&snapshot));
    leo_score_context_destroy(context);leo_score_context_destroy(control);
}
