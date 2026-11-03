#include "streaming_match.hpp"
#include <iostream>

using namespace leo::location::streaming;
static void check(bool ok,const char* message) {if(!ok)throw std::runtime_error(message);}

int main() {
    try {
        constexpr uint32_t n=101;constexpr double start=-100,step=5,omega=.001;
        std::vector<leo_orbit_state> states(n);
        int32_t id=1;
        for(uint32_t k=0;k<n;++k) {
            double t=start+k*step;
            states[k]={{7000*std::cos(omega*t),7000*std::sin(omega*t),500*std::sin(2*omega*t)},
                       {-7000*omega*std::sin(omega*t),7000*omega*std::cos(omega*t),1000*omega*std::cos(2*omega*t)}};
        }
        leo_orbit_snapshot orbit{1,1700000000000000000LL,start,step,1,n,&id,states.data()};
        for(double t:{-100.,-99.7,0.,37.125,399.9,400.}) {
            leo_orbit_state a{},b{};
            check(state_at(orbit,t,a),"private interpolation failed");
            check(leo_orbit_interpolate(&orbit,0,t,&b)==LEO_LOCATION_OK,"public interpolation failed");
            for(int j=0;j<3;++j) {
                check(std::abs(a.position_km[j]-b.position_km[j])<1e-10,"interpolation position differs");
                check(std::abs(a.velocity_km_s[j]-b.velocity_km_s[j])<1e-11,"interpolation velocity differs");
            }
        }
        leo_orbit_state out{};
        check(!state_at(orbit,-101,out)&&!state_at(orbit,401,out),"out-of-range interpolation accepted");
        check(!state_at(orbit,std::numeric_limits<double>::quiet_NaN(),out),"NaN accepted");
        const Region region{0,0,250};
        check(regional_visible(orbit,region),"visible regional pass rejected");
        check(!regional_visible(orbit,{0,180,250}),"antipodal pass retained");
        // Endpoints below the horizon must not hide a visible interior control.
        std::array<leo_orbit_state,2> hump={leo_orbit_state{{6300,1000,0},{40,0,0}},
                                           leo_orbit_state{{6300,1000,0},{-40,0,0}}};
        leo_orbit_snapshot crossing{1,1,0,10,1,2,&id,hump.data()};
        check(regional_visible(crossing,{0,0,1},0),"interior horizon crossing lost");
        // A site near the regional edge can see a pass hidden at its centre.
        const auto edge=site_at(region,{250,0,0});
        std::array<leo_orbit_state,2> boundary={leo_orbit_state{{6340,1800,0},{0,0,0}},
                                               leo_orbit_state{{6340,1800,0},{0,0,0}}};
        leo_orbit_snapshot edge_orbit{1,1,0,10,1,2,&id,boundary.data()};
        double value;
        check(!doppler(edge_orbit,5,site_at(region,{}),1,value),"centre unexpectedly visible");
        check(doppler(edge_orbit,5,edge,1,value),"regional edge not visible");
        check(regional_visible(edge_orbit,region,0),"regional edge excluded");
        Track track;const Point truth{12,17,7};const double scale=11200000000./299792.458;
        for(int i=0;i<13;++i) {
            const double t=10+i*3.;double f;
            check(doppler(orbit,t+truth.tau,site_at(region,truth),scale,f),"synthetic propagation failed");
            track.nodes.push_back(t);track.values.push_back(f+12345);
            track.times.push_back(t);track.measured.push_back(f+12345);track.training.push_back(i%3!=2);
        }
        const Fit exact=raw_fit(orbit,track,region,truth,scale);
        check(exact.train_rms<1e-8&&exact.validation_rms<1e-8&&std::abs(exact.offset-12345)<1e-8,
              "frequency offset not eliminated");
        const Point initial{35,-25,5};
        const double before=evaluate(orbit,track,region,initial,scale,false);
        const Point fitted=refine(orbit,track,region,initial,scale,60);
        const double after=evaluate(orbit,track,region,fitted,scale,false);
        check(after<before*.01,"continuous refinement did not recover curve");
        check(std::hypot(fitted.east,fitted.north)<=region.radius+1e-9&&std::abs(fitted.tau)<=60,
              "refinement escaped bounds");
        for(size_t i=0;i<track.measured.size();++i)if(!track.training[i])track.measured[i]+=100000;
        const Fit changed=raw_fit(orbit,track,region,truth,scale);
        check(changed.train_rms<1e-8&&std::abs(changed.offset-exact.offset)<1e-8&&changed.validation_rms>99999,
              "held-out values contaminated nuisance fit");
        std::cout<<"streaming matcher numerical tests passed\n";
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
