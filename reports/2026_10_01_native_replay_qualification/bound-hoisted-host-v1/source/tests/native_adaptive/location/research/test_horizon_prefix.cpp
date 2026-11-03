#include "research/horizon_prefix.hpp"
#include <cassert>
#include <random>
#include <limits>

bool direct(const leo_orbit_snapshot& s,unsigned satellite,const leo_location_track& t,
            const leo_location_site& site,const leo_score_config& config) {
    auto dot=[](const double* a,const double* b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];};
    int lo=std::max(0,static_cast<int>(std::floor((t.times_s[0]+config.tau_first_s-s.knot_start_s)/s.knot_step_s)));
    int hi=std::min(static_cast<int>(s.knot_count)-2,static_cast<int>(std::floor((t.times_s[t.observation_count-1]+config.tau_last_s-s.knot_start_s)/s.knot_step_s)));
    double plane=dot(site.ecef_km,site.up);
    for(int k=lo;k<=hi;++k) {
        auto& a=s.states[satellite*s.knot_count+k];auto& b=s.states[satellite*s.knot_count+k+1];
        double x=dot(a.position_km,site.up)-plane,y=dot(b.position_km,site.up)-plane;
        if(x>=0 || y>=0 || x+s.knot_step_s*dot(a.velocity_km_s,site.up)/3.0>=0 ||
           y-s.knot_step_s*dot(b.velocity_km_s,site.up)/3.0>=0) return true;
    }
    return false;
}

int main() {
    int32_t ids[2]={1,2};leo_orbit_state states[8]{};
    for(unsigned i=0;i<8;++i) states[i].position_km[0]=6000;
    states[2].position_km[0]=7000;
    // Satellite 2 has both endpoints below the horizon but a cubic control
    // point above it: omitting the velocity test would be incorrect.
    states[5].velocity_km_s[0]=200;
    leo_orbit_snapshot snapshot{1,0,0,10,2,4,ids,states};
    leo_location_site site{{6378,0,0},{1,0,0}};
    auto config=leo_score_default_config();config.tau_first_s=config.tau_last_s=0;
    leo::location::research::HorizonPrefix prefix;
    assert(prefix.build(snapshot,site,0,2));
    double times[2]={0,5};leo_location_track track{1,2,1,times,nullptr,nullptr};
    assert(!prefix.possible(snapshot,0,track,config));
    assert(!prefix.possible(snapshot,1,track,config));
    times[0]=10;times[1]=15;
    assert(prefix.possible(snapshot,0,track,config));
    assert(prefix.possible(snapshot,1,track,config));
    assert(!prefix.build(snapshot,site,2,1));
    assert(prefix.build(snapshot,site,1,2));
    assert(!prefix.possible(snapshot,0,track,config));
    assert(prefix.possible(snapshot,1,track,config));
    site.up[0]=-1;
    assert(prefix.build(snapshot,site,0,2)); // New site replaces cached counts.
    times[0]=0;times[1]=5;
    assert(prefix.possible(snapshot,0,track,config));
    std::mt19937 generator(1729);
    std::uniform_real_distribution<double> position(-8000,8000),velocity(-300,300);
    for(unsigned trial=0;trial<200;++trial) {
        for(auto& state:states) for(unsigned c=0;c<3;++c) {
            state.position_km[c]=position(generator);state.velocity_km_s[c]=velocity(generator);
        }
        if(trial==0) states[0].position_km[0]=std::numeric_limits<double>::quiet_NaN();
        // Reused shared-knot values must preserve the original comparison and
        // short-circuit behavior even when a value is not finite.
        if(trial%17==0) states[2].velocity_km_s[1]=std::numeric_limits<double>::quiet_NaN();
        if(trial%19==0) states[5].position_km[2]=std::numeric_limits<double>::infinity();
        for(unsigned c=0;c<3;++c) {site.ecef_km[c]=position(generator);site.up[c]=position(generator)/8000;}
        assert(prefix.build(snapshot,site,0,2));
        for(int begin=-5;begin<=30;begin+=5) for(int end=begin;end<=35;end+=5) {
            times[0]=begin;times[1]=end;
            for(unsigned satellite=0;satellite<2;++satellite)
                assert(prefix.possible(snapshot,satellite,track,config)==direct(snapshot,satellite,track,site,config));
        }
    }
    auto oversized=snapshot;oversized.knot_count=65536;
    assert(!prefix.build(oversized,site,0,2));
}
