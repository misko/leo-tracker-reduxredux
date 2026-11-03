#pragma once
#include "location.h"
#include <algorithm>
#include <cmath>
#include <vector>

namespace leo::location::research {
// Per-site prefix counts of the existing cubic-horizon control-point test.
// Queries preserve the original inclusive knot interval for each track.
class HorizonPrefix {
    unsigned begin_=0,end_=0,knots_=0;
    std::vector<unsigned short> prefix_;
    static double dot(const double* a,const double* b) {
        return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
    }
public:
    struct Range {int lo=0,hi=-1;};
    bool build(const leo_orbit_snapshot& s,const leo_location_site& site,unsigned begin,unsigned end) {
        if(s.knot_count>65535 || begin>end || end>s.satellite_count ||
           static_cast<size_t>(end-begin)*s.knot_count>2000000) return false;
        begin_=begin;end_=end;knots_=s.knot_count;
        try {prefix_.assign(static_cast<size_t>(end-begin)*knots_,0);} catch(...) {return false;}
        const double plane=dot(site.ecef_km,site.up);
        for(unsigned sat=begin;sat<end;++sat) {
            auto* p=prefix_.data()+static_cast<size_t>(sat-begin)*knots_;
            if(knots_<2)continue;
            const auto* states=s.states+static_cast<size_t>(sat)*knots_;
            double x=dot(states[0].position_km,site.up)-plane;
            double vx=0;bool vx_ready=false;
            for(unsigned k=0;k+1<knots_;++k) {
                const auto& a=states[k];
                const auto& b=states[k+1];
                const double y=dot(b.position_km,site.up)-plane;
                bool possible=x>=0 || y>=0;
                double vy=0;bool vy_ready=false;
                if(!possible) {
                    if(!vx_ready)vx=dot(a.velocity_km_s,site.up);
                    possible=x+s.knot_step_s*vx/3.0>=0;
                    if(!possible) {
                        vy=dot(b.velocity_km_s,site.up);vy_ready=true;
                        possible=y-s.knot_step_s*vy/3.0>=0;
                    }
                }
                p[k+1]=static_cast<unsigned short>(p[k]+possible);
                // Adjacent intervals share a knot. Reuse its identical dot
                // products; retain the original arithmetic and short circuit.
                x=y;vx=vy;vx_ready=vy_ready;
            }
        }
        return true;
    }
    Range range(const leo_orbit_snapshot& s,const leo_location_track& track,
                const leo_score_config& config) const {
        int lo=static_cast<int>(std::floor((track.times_s[0]+config.tau_first_s-s.knot_start_s)/s.knot_step_s));
        int hi=static_cast<int>(std::floor((track.times_s[track.observation_count-1]+config.tau_last_s-s.knot_start_s)/s.knot_step_s));
        lo=std::max(lo,0);hi=std::min(hi,static_cast<int>(knots_)-2);
        return {lo,hi};
    }
    bool possible(unsigned satellite,Range range) const {
        if(range.hi<range.lo || range.lo<0 || range.hi>=static_cast<int>(knots_)-1 ||
           satellite<begin_ || satellite>=end_) return false;
        const auto* p=prefix_.data()+static_cast<size_t>(satellite-begin_)*knots_;
        return p[range.hi+1]!=p[range.lo];
    }
    bool possible(const leo_orbit_snapshot& s,unsigned satellite,const leo_location_track& track,
                  const leo_score_config& config) const {
        return possible(satellite,range(s,track,config));
    }
};
}
