#include "research/float_pair_bound.hpp"
#include "research/heldout_bound.hpp"
#include <cassert>
#include <random>

double oracle(const leo_orbit_state& s,const leo_location_site& site,double scale) {
    double d[3];for(unsigned c=0;c<3;++c)d[c]=s.position_km[c]-site.ecef_km[c];
    return scale*(d[0]*s.velocity_km_s[0]+d[1]*s.velocity_km_s[1]+d[2]*s.velocity_km_s[2])/
        std::sqrt(d[0]*d[0]+d[1]*d[1]+d[2]*d[2]);
}
int main() {
    using namespace leo::location::research;
    std::mt19937_64 generator(20261001);
    std::uniform_real_distribution<double> unit(-1,1),exponent(-3,9);
    unsigned accepted=0,rejected=0;
    for(unsigned trial=0;trial<100000;++trial) {
        leo_location_site site{{6378,20,-50},{1,0,0}};
        leo_orbit_state states[2]{};
        const double magnitude=std::pow(10.0,exponent(generator));
        const double scale=trial%3 ? -11200000000.0/299792.458 : -std::pow(10.0,exponent(generator));
        DopplerInterval intervals[2];double exact[2],residual[2],measured[2];
        for(unsigned endpoint=0;endpoint<2;++endpoint) {
            auto& state=states[endpoint];
            for(unsigned c=0;c<3;++c) {
                state.position_km[c]=site.ecef_km[c]+magnitude*unit(generator);
                state.velocity_km_s[c]=unit(generator)*(trial%2 ? 8 : 1e6);
            }
            intervals[endpoint]=float_doppler(state,site,scale);
            exact[endpoint]=oracle(state,site,scale);
            measured[endpoint]=unit(generator)*1e6;
            residual[endpoint]=measured[endpoint]-exact[endpoint];
            if(intervals[endpoint].valid) {
                ++accepted;
                assert(std::abs(intervals[endpoint].value-exact[endpoint])<=intervals[endpoint].error);
            }
        }
        if(!intervals[0].valid || !intervals[1].valid)continue;
        const unsigned count=2+trial%1000;
        const double denominator=std::sqrt(2.0*count);
        const double boundary=std::abs(residual[0]-residual[1])/denominator;
        for(double fraction : {0.0,.5,.99999,1.0,1.00001}) {
            const double threshold=boundary*fraction;
            if(interval_pair_cannot_win(measured[0]-intervals[0].value,intervals[0].error,
                                       measured[1]-intervals[1].value,intervals[1].error,
                                       denominator,threshold)) {
                ++rejected;
                assert(pair_cannot_win(residual[0],residual[1],count,threshold));
            }
        }
    }
    assert(accepted>100000 && rejected>100000);
    leo_location_site site{};leo_orbit_state zero{};
    assert(!float_doppler(zero,site,1).valid);
    zero.position_km[0]=1e30;
    assert(!float_doppler(zero,site,1).valid);
    zero.position_km[0]=7000;zero.velocity_km_s[0]=std::numeric_limits<double>::quiet_NaN();
    assert(!float_doppler(zero,site,1).valid);
    assert(!interval_pair_cannot_win(1,1,1,1,1,0));
    assert(!interval_pair_cannot_win(1,-1,2,1,1,0));
}
