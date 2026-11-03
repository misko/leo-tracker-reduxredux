#include "research/heldout_bound.hpp"
#include <cassert>
#include <limits>
#include <random>
int main() {
    using leo::location::research::pair_cannot_win;
    assert(!pair_cannot_win(0,100,1,1));
    assert(!pair_cannot_win(0,100,2,50)); // A tie must survive.
    assert(pair_cannot_win(0,100,2,49));
    assert(!pair_cannot_win(0,100,2,std::numeric_limits<double>::infinity()));
    assert(!pair_cannot_win(0,std::numeric_limits<double>::quiet_NaN(),2,1));
    // The reciprocal prefilter may retain extra near-ties, but must never
    // reject a case retained by the original guarded division check.
    std::mt19937_64 rng(18479);
    for(unsigned i=0;i<200000;++i) {
        const double scale=std::ldexp(1.0,static_cast<int>(rng()%2000)-1000);
        const double a=(static_cast<int>(rng()%2001)-1000)*scale;
        const double b=(static_cast<int>(rng()%2001)-1000)*scale;
        const unsigned count=2+rng()%10000;
        const double divisor=std::sqrt(2.0*count);
        const double inverse=(1.0/divisor)*(1.0-0x1p-48);
        const double bound=std::abs(a-b)/divisor;
        const double incumbent=bound*(static_cast<double>(rng()%10001)/10000);
        const double guard=1e-6*(1+std::abs(a)+std::abs(b)+incumbent);
        const bool original=std::isfinite(a) && std::isfinite(b) &&
            std::isfinite(incumbent) && std::isfinite(bound) && bound>incumbent+guard;
        if(pair_cannot_win(a,b,count,incumbent,divisor,inverse))assert(original);
        if(std::isfinite(bound)) {
            assert(!pair_cannot_win(a,b,count,bound,divisor,inverse));
            assert(!pair_cannot_win(a,b,count,std::nextafter(bound,INFINITY),divisor,inverse));
        }
    }
    using leo::location::research::subset_cannot_win;
    double residuals[4]={0,100,30,80};
    assert(subset_cannot_win(residuals,4,4,1));
    assert(!subset_cannot_win(residuals,4,3,1));
    for(int c=-100;c<=100;++c) {
        double s=0;for(auto r:residuals)s+=(r-c)*(r-c);
        assert(!subset_cannot_win(residuals,4,4,std::sqrt(s/4)));
        assert(!subset_cannot_win(residuals,2,4,std::sqrt(s/4)));
    }
    for(int a=-50;a<=50;a+=5) for(int b=-50;b<=50;b+=5)
        for(int offset=-100;offset<=100;offset+=5) {
            double actual=std::sqrt(((a-offset)*(a-offset)+(b-offset)*(b-offset))/2.0);
            assert(!pair_cannot_win(a,b,2,actual));
            for(unsigned count : {2u,3u,101u})
                assert(pair_cannot_win(a,b,count,actual)==
                    pair_cannot_win(a,b,count,actual,std::sqrt(2.0*count)));
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
    const auto subset=leo::location::research::select_subset(track,2);
    assert(subset.size==2 && subset.indexes[0]==0 && subset.indexes[1]==5);
    leo::location::internal::InterpolationStencil stencils[6];
    for(unsigned i=0;i<6;++i)
        assert(leo::location::internal::build_interpolation_stencil(&snapshot,times[i],&stencils[i])==LEO_LOCATION_OK);
    for(unsigned rms=0;rms<=100;++rms) {
        incumbent.heldout_rms_hz=rms;
        assert(cannot_win(snapshot,0,track,site,config,2,incumbent)==
            cannot_win(snapshot,0,track,site,config,2,incumbent,&subset,stencils));
    }
    snapshot.knot_start_s=-10;snapshot.knot_step_s=30;
    config.tau_first_s=-2;config.tau_last_s=2;config.tau_step_s=2;
    leo::location::internal::InterpolationStencil shifted[18];
    for(unsigned tau_index=0;tau_index<3;++tau_index) for(unsigned i=0;i<6;++i)
        assert(leo::location::internal::build_interpolation_stencil(&snapshot,
            times[i]+static_cast<int>(2*tau_index)-2,&shifted[tau_index*6+i])==LEO_LOCATION_OK);
    for(unsigned rms=0;rms<=100;++rms) {
        incumbent.heldout_rms_hz=rms;
        assert(cannot_win(snapshot,0,track,site,config,2,incumbent)==
            cannot_win(snapshot,0,track,site,config,2,incumbent,&subset,shifted));
    }
    // Moving states make the different tau stencils observably different.
    // Also exercise the int32 endpoints: the increment must remain int64.
    states[0].position_km[1]=-100;states[1].position_km[1]=100;
    states[0].velocity_km_s[1]=states[1].velocity_km_s[1]=7;
    for(int first : {-2,INT32_MIN,INT32_MAX-4}) {
        config.tau_first_s=first;config.tau_last_s=first+4;
        snapshot.knot_start_s=static_cast<double>(first)-10;
        for(unsigned t=0;t<3;++t) for(unsigned i=0;i<6;++i)
            assert(leo::location::internal::build_interpolation_stencil(&snapshot,
                times[i]+static_cast<double>(static_cast<int64_t>(first)+2*t),
                &shifted[t*6+i])==LEO_LOCATION_OK);
        bool rejected=false,survived=false;
        for(unsigned rms=0;rms<=200000;rms+=100) {
            incumbent.heldout_rms_hz=rms;
            const bool generic=cannot_win(snapshot,0,track,site,config,2,incumbent);
            assert(generic==cannot_win(snapshot,0,track,site,config,2,incumbent,&subset,shifted));
            rejected|=generic;survived|=!generic;
        }
        assert(rejected && survived);
    }
    states[0].position_km[1]=states[1].position_km[1]=0;
    states[0].velocity_km_s[1]=states[1].velocity_km_s[1]=0;
    snapshot.knot_start_s=-10;
    config.tau_first_s=-2;config.tau_last_s=2;
    incumbent.heldout_rms_hz=80;
    assert(!cannot_win(snapshot,0,track,site,config,2,incumbent));
    incumbent.matched=0;
    assert(!cannot_win(snapshot,0,track,site,config,2,incumbent));
    states[1].position_km[0]=std::numeric_limits<double>::quiet_NaN();
    assert(!bounded_snapshot(snapshot,site,config));
}
