#include "research/doppler_interval4.hpp"
#include "research/float_pair_bound.hpp"
#include "research/heldout_bound.hpp"
#include <cassert>
#include <random>
#include <cstdio>

static double oracle(const leo_orbit_state& s,const leo_location_site& site,double scale) {
    double d[3];for(unsigned c=0;c<3;++c)d[c]=s.position_km[c]-site.ecef_km[c];
    return scale*(d[0]*s.velocity_km_s[0]+d[1]*s.velocity_km_s[1]+d[2]*s.velocity_km_s[2])/
        std::sqrt(d[0]*d[0]+d[1]*d[1]+d[2]*d[2]);
}
int main() {
    using namespace leo::location::research;
    std::mt19937_64 rng(184731);std::uniform_real_distribution<double> unit(-1,1),exponent(-4,8);
    unsigned valid=0,rejected=0,vector_rejected=0;double worst_fraction=0;
    for(unsigned trial=0;trial<100000;++trial) {
        leo_location_site site{{6378.137123,203.78912,-81.12345},{1,0,0}};
        const double scale=trial%3?-11200000000.0/299792.458:-std::pow(10.0,exponent(rng));
        PackedOrbit4 pack;leo_orbit_state states[4]{};double exact[4],measured[4];
        for(unsigned lane=0;lane<4;++lane) {
            const double distance=std::pow(10.0,exponent(rng));
            for(unsigned c=0;c<3;++c) {
                states[lane].position_km[c]=site.ecef_km[c]+distance*unit(rng);
                states[lane].velocity_km_s[c]=unit(rng)*(trial%2?8:1e6);
            }
            assert(pack_orbit_lane(pack,lane,states[lane]));
            exact[lane]=oracle(states[lane],site,scale);measured[lane]=unit(rng)*1e6;
        }
        auto intervals=doppler_intervals4(pack,pack_site(site,scale));
        PackedOrbit4 shifted;
        for(unsigned lane=0;lane<4;++lane)assert(pack_orbit_lane(shifted,lane,states[(lane+1)%4]));
        const unsigned pair_count=2+trial%1000;
        const double pair_denominator=std::sqrt(2.0*pair_count);
        const double pair_boundary=std::abs((measured[0]-exact[0])-(measured[1]-exact[1]))/pair_denominator;
        for(double fraction:{0.0,.5,.99999,1.0,1.00001}) {
            double threshold=pair_boundary*fraction;
            auto rejected_mask=pair_rejections4(pack,shifted,pack_site(site,scale),
                pack_pair_threshold(measured[0],measured[1],threshold,pair_denominator));
            for(unsigned lane=0;lane<4;++lane)if(rejected_mask&(1u<<lane)) {
                ++vector_rejected;
                assert(pair_cannot_win(measured[0]-exact[lane],measured[1]-exact[(lane+1)%4],pair_count,threshold));
            }
        }
        for(unsigned lane=0;lane<4;++lane)if(intervals.valid[lane]) {
            ++valid;double error=std::abs(exact[lane]-intervals.value[lane]);
            assert(error<=intervals.error[lane]);
            worst_fraction=std::fmax(worst_fraction,error/intervals.error[lane]);
        }
        for(unsigned lane=0;lane<4;lane+=2)if(intervals.valid[lane]&&intervals.valid[lane+1]) {
            unsigned n=2+trial%1000;double denominator=std::sqrt(2.0*n);
            double a=measured[lane]-exact[lane],b=measured[lane+1]-exact[lane+1];
            for(double fraction:{0.0,.5,.99999,1.0,1.00001}) {
                double threshold=std::abs(a-b)/denominator*fraction;
                if(interval_pair_cannot_win(measured[lane]-intervals.value[lane],intervals.error[lane],
                    measured[lane+1]-intervals.value[lane+1],intervals.error[lane+1],denominator,threshold)) {
                    ++rejected;assert(pair_cannot_win(a,b,n,threshold));
                }
            }
        }
    }
    assert(valid>200000 && rejected>100000 && vector_rejected>100000);
    PackedOrbit4 pack;leo_orbit_state state{};leo_location_site site{};
    assert(pack_orbit_lane(pack,0,state));
    assert(!doppler_intervals4(pack,pack_site(site,1)).valid[0]);
    state.position_km[0]=7000;state.velocity_km_s[0]=7;assert(pack_orbit_lane(pack,0,state));
    assert(doppler_intervals4(pack,pack_site(site,1)).valid[0]);
    state.position_km[0]=std::numeric_limits<double>::quiet_NaN();
    assert(!pack_orbit_lane(pack,0,state));
    assert(!doppler_intervals4(pack,pack_site(site,1)).valid[0]);
    assert(!pack_site(site,INFINITY).valid);assert(!pack_orbit_lane(pack,4,state));
    std::printf("valid=%u rejected=%u vector_rejected=%u worst_error_fraction=%.9g\n",valid,rejected,vector_rejected,worst_fraction);
}
