#pragma once
#include "location.h"
#include <cmath>
#include <limits>

namespace leo::location::research {
struct DopplerInterval { double value=0,error=0;bool valid=false; };

// Research prefilter, never a final score. Form delta with the same double
// subtraction as the oracle before rounding it to float. Thus cancellation of
// absolute Earth coordinates does not enter the float error allowance.
// For normal intermediates, the allowance exceeds the accumulated rounding
// from conversions, the 3-term dot/norm, sqrt and division by a wide margin.
// Unsupported magnitudes and nonfinite intermediates fall back to the oracle.
inline DopplerInterval float_doppler(const leo_orbit_state& state,
                                    const leo_location_site& site,double scale) {
    if(!std::isfinite(scale) || std::abs(scale)<1e-12 || std::abs(scale)>1e12)return {};
    float delta[3],velocity[3];double speed_l1=0;
    for(unsigned c=0;c<3;++c) {
        delta[c]=static_cast<float>(state.position_km[c]-site.ecef_km[c]);
        velocity[c]=static_cast<float>(state.velocity_km_s[c]);
        speed_l1+=std::abs(state.velocity_km_s[c]);
    }
    const float range2=delta[0]*delta[0]+delta[1]*delta[1]+delta[2]*delta[2];
    if(!(range2>=1e-6f && range2<=1e20f) || !(speed_l1<=1e8))return {};
    const float radial=delta[0]*velocity[0]+delta[1]*velocity[1]+delta[2]*velocity[2];
    const float predicted=static_cast<float>(scale)*radial/std::sqrt(range2);
    const double error=1e-6+128.0*std::numeric_limits<float>::epsilon()*std::abs(scale)*speed_l1;
    if(!std::isfinite(predicted) || !std::isfinite(error))return {};
    return {predicted,error,true};
}

inline bool interval_pair_cannot_win(double a,double error_a,double b,double error_b,
                                    double denominator,double incumbent) {
    const double separation=std::abs(a-b)-error_a-error_b;
    const double guard=1e-6*(1+std::abs(a)+error_a+std::abs(b)+error_b+incumbent);
    return error_a>=0 && error_b>=0 && denominator>0 && incumbent>=0 &&
        std::isfinite(separation) && std::isfinite(guard) &&
        separation/denominator>incumbent+guard;
}
}
