#include "doppler_match/matcher.hpp"
#include "doppler_match/detail.hpp"
#include <cstring>
#include <memory>
#include <iostream>

using namespace leo::adaptive::location::doppler_match;
using namespace leo::adaptive::location::doppler_match::detail;
static void check(bool ok,const char* message) {if(!ok)throw std::runtime_error(message);}

struct Reader {
    std::vector<leo_tle_record> records;
    size_t index=0;
    static bool read(void* user,leo_tle_record& out) {
        auto& self=*static_cast<Reader*>(user);
        if(self.index==self.records.size())return false;
        out=self.records[self.index++];return true;
    }
    Catalogue port() {index=0;return {records.size(),read,this};}
};

static void test_port() {
    leo_tle_record tle{};tle.satellite_id=44714;
    std::strcpy(tle.line1,"1 44714U 19074B   26270.09087237  .00034246  00000-0  33881-3 0  9999");
    std::strcpy(tle.line2,"2 44714  53.1459 294.7156 0002678  78.6558 281.4759 15.65554847380103");
    Options o;o.epoch_utc_ns=1790557997299661326LL;o.carrier_hz=11200000000.;
    std::unique_ptr<leo_orbit_context,decltype(&leo_orbit_context_destroy)> context(
        leo_orbit_context_create(1,49),&leo_orbit_context_destroy);
    leo_orbit_snapshot orbit{};
    check(leo_orbit_build_tle(context.get(),1,o.epoch_utc_ns,-90,5,49,&tle,1,&orbit)==LEO_LOCATION_OK,
        "synthetic TLE propagation failed");
    leo_orbit_state mid{};
    check(leo_orbit_interpolate(&orbit,0,25,&mid)==LEO_LOCATION_OK,"synthetic state missing");
    o.region={std::atan2(mid.position_km[2],std::hypot(mid.position_km[0],mid.position_km[1]))*180/pi,
              std::atan2(mid.position_km[1],mid.position_km[0])*180/pi,250};
    // Independent range-rate calculation via the public orbit interpolator.
    const auto site=site_at(o.region,{});
    Track tr;
    for(int i=0;i<13;++i) {
        const double t=10+3*i;
        leo_orbit_state state{};
        check(leo_orbit_interpolate(&orbit,0,t,&state)==LEO_LOCATION_OK,"synthetic sample missing");
        double range2=0,product=0;
        for(int j=0;j<3;++j) {
            const double q=state.position_km[j]-site.position[j];
            range2+=q*q;product+=q*state.velocity_km_s[j];
        }
        const double f=-o.carrier_hz/299792.458*product/std::sqrt(range2)+12345;
        tr.times.push_back(t);tr.measured.push_back(f);tr.training.push_back(i%3!=2);
        tr.nodes.push_back(t);tr.values.push_back(f);
    }
    // Identical elements with distinct IDs deliberately exercise tie ordering.
    auto twin=tle;twin.satellite_id=44715;
    std::memcpy(twin.line1+2,"44715",5);std::memcpy(twin.line2+2,"44715",5);
    auto invalid=tle;invalid.satellite_id=99999;invalid.line1[0]='x';
    Reader reader{{twin,invalid,tle}};
    std::vector<Track> tracks{tr};
    const auto result=match(tracks,o,reader.port());
    check(reader.index==3&&result.tracks.size()==1&&result.tracks[0].size()==2,"streamed result shape changed");
    check(result.statistics.invalid_catalogue_ids==std::vector<int32_t>{99999},"invalid TLE was hidden");
    const auto& best=result.tracks[0][0];
    check(best.satellite_id==44714&&result.tracks[0][1].satellite_id==44715,"tie ordering changed");
    check(best.training_rms_hz<1e-7&&best.validation_rms_hz<1e-7
        &&std::abs(best.frequency_offset_hz-12345)<1e-7,"public matcher lost exact synthetic fit");
    check(std::hypot(best.east_km,best.north_km)<=250&&std::abs(best.time_offset_s)<=60,"public fit escaped bounds");
    check(result.statistics.orbit_state_capacity_bytes<20000,"orbit workspace grew unexpectedly");
    check(tracks[0].measured==tr.measured&&tracks[0].nodes==tr.nodes,"matcher mutated borrowed input");
    for(size_t i=0;i<tr.times.size();++i)if(!tr.training[i])tracks[0].measured[i]+=100000;
    const auto poisoned=match(tracks,o,reader.port());
    for(size_t i=0;i<2;++i) {
        const auto& a=result.tracks[0][i];const auto& b=poisoned.tracks[0][i];
        check(a.satellite_id==b.satellite_id&&a.training_rms_hz==b.training_rms_hz
            &&a.frequency_offset_hz==b.frequency_offset_hz&&a.time_offset_s==b.time_offset_s
            &&a.east_km==b.east_km&&a.north_km==b.north_km&&b.validation_rms_hz>99999,
            "held-out data changed candidate ranking or fit");
    }
    tracks={tr};o.keep_per_track=1;
    const auto limited=match(tracks,o,reader.port());
    check(limited.tracks[0].size()==1&&limited.tracks[0][0].satellite_id==44714,"shortlist limit changed");
    o.disable_gate=true;
    const auto ungated=match(tracks,o,reader.port());
    check(ungated.tracks[0][0].training_rms_hz==best.training_rms_hz,"gate changed visible synthetic fit");
    o.disable_gate=false;o.audit_gate=true;
    o.region.latitude=-o.region.latitude;o.region.longitude+=o.region.longitude<0 ? 180 : -180;
    const auto absent=match(tracks,o,reader.port());
    check(absent.tracks[0].empty()&&absent.statistics.gate_fine_envelope_misses==0,
        "no-visible-candidate result was not empty");
    o.region={site.latitude,site.longitude,250};o.audit_gate=false;
    auto rejects=[&](const std::vector<Track>& input,const Options& options) {
        auto catalogue=reader.port();bool caught=false;
        try {(void)match(input,options,catalogue);}catch(const std::invalid_argument&){caught=true;}
        check(caught&&reader.index==0,"invalid input reached catalogue or was accepted");
    };
    auto bad=tracks;bad[0].training.pop_back();rejects(bad,o);
    bad=tracks;bad[0].training.assign(tr.times.size(),1);rejects(bad,o);
    bad=tracks;bad[0].times[1]=bad[0].times[0];rejects(bad,o);
    bad=tracks;bad[0].values[0]=std::numeric_limits<double>::quiet_NaN();rejects(bad,o);
    auto bad_options=o;bad_options.fine_step_s=1e-20;rejects(tracks,bad_options);
    bad_options=o;bad_options.time_step_s=1e-20;rejects(tracks,bad_options);
    bad_options=o;bad_options.region.radius=501;rejects(tracks,bad_options);
    bad_options=o;bad_options.carrier_hz=0;rejects(tracks,bad_options);
    bad_options=o;bad_options.epoch_utc_ns=std::numeric_limits<int64_t>::max();rejects(tracks,bad_options);
    Catalogue short_source=reader.port();++short_source.count;bool failed=false;
    try {(void)match(tracks,o,short_source);}catch(const std::runtime_error&){failed=true;}
    check(failed,"short source silently returned partial results");
    Catalogue throwing{1,[](void*,leo_tle_record&)->bool {throw std::runtime_error("source failure");},nullptr};
    failed=false;
    try {(void)match(tracks,o,throwing);}catch(const std::runtime_error& e){failed=std::string(e.what())=="source failure";}
    check(failed,"source exception was swallowed");
    check(match(tracks,o,reader.port()).tracks[0][0].satellite_id==44714,"failure leaked state into next call");
    o.time_bound_s=1e-20;o.time_step_s=1e-20;
    const auto narrow=match(tracks,o,reader.port());
    check(narrow.statistics.seed_evaluations==2*9*3,"tiny clock interval escaped seed work bound");
}

static void test_numerics() {
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
}

int main() {
    try {
        test_numerics();test_port();
        std::cout<<"Doppler matcher numerical and public port tests passed\n";
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
