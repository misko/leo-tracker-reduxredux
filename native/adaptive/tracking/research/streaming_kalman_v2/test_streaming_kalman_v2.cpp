#include "streaming_kalman_v2.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using leo::adaptive::tracking::Candidate;
using leo::adaptive::tracking::research::streaming_kalman_v2::Config;
using leo::adaptive::tracking::research::streaming_kalman_v2::Result;
std::string id(unsigned x){constexpr char h[]="0123456789abcdef";std::string s="sha256:"+std::string(64,'0');
    for(unsigned i=0;i<8;++i){s[s.size()-1-i]=h[x&15U];x>>=4U;}return s;}
double wrap(double x,double spacing){return x-std::nearbyint(x/spacing)*spacing;}
Candidate point(unsigned n,unsigned source,double time,double frequency,int receiver=0,
                int channel=3,const char* edge="lower",double rf=1000,double spacing=100) {
    constexpr std::int64_t origin=1'700'000'000'000'000'000LL;auto center=origin+static_cast<std::int64_t>(time*1e9);
    return {id(n),id(100000+source),receiver,channel,edge,rf,center-100,center,center+100,
        wrap(frequency,spacing),.6,.05,.55};}
Config config(){Config c;c.canonical_rf_hz=1000;c.alias_spacing_hz=100;c.measurement_sigma_hz=.5;
    c.acceleration_sigma_hz_per_s2=2;c.innovation_gate_hz=8;c.minimum_rate_hz_per_s=-50;
    c.maximum_rate_hz_per_s=50;c.maximum_gap_s=2.1;c.minimum_span_s=4;c.minimum_support=8;
    c.maximum_hypotheses_per_lane=96;c.maximum_output_tracks_per_lane=16;return c;}
bool contains(const Result& r,const std::vector<std::string>& ids,std::size_t n){for(const auto& t:r.tracks){
    std::size_t matches=0;for(const auto& p:t.points)matches+=std::find(ids.begin(),ids.end(),p.candidate_id)!=ids.end();
    if(matches>=n)return true;}return false;}
bool contains_sources(const Result& r,const std::vector<std::string>& ids,std::size_t n){for(const auto& t:r.tracks){
    std::size_t matches=0;for(const auto& p:t.points)matches+=std::find(ids.begin(),ids.end(),p.source_group_id)!=ids.end();
    if(matches>=n)return true;}return false;}
void curved_alias_clutter(){std::vector<Candidate> v;std::vector<std::string> truth;
    for(unsigned t=0;t<12;++t){double f=8+4*t+.35*t*t+(t%2?.15:-.1);v.push_back(point(100+t,t,t,f));
        truth.push_back(id(100+t));v.push_back(point(500+t,t,t,-43+13*t));}
    auto r=leo::adaptive::tracking::research::streaming_kalman_v2::reconstruct(v,config());assert(contains(r,truth,10));}
void crossing_alternatives(){std::vector<Candidate> v;std::vector<std::string> up,down;
    for(unsigned t=0;t<12;++t){v.push_back(point(1000+t,t,t,-35+7.5*t));up.push_back(id(1000+t));
        v.push_back(point(2000+t,t,t,48-7.5*t));down.push_back(id(2000+t));}
    auto r=leo::adaptive::tracking::research::streaming_kalman_v2::reconstruct(v,config());
    assert(contains(r,up,9));assert(contains(r,down,9));}
void gap_and_rolling_birth(){std::vector<Candidate> v;std::vector<std::string> late;
    for(unsigned t=0;t<4;++t)v.push_back(point(3000+t,t,t,4*t));
    for(unsigned t=0;t<10;++t){v.push_back(point(3100+t,10+t,10+t,20+3*t));late.push_back(id(3100+t));}
    auto r=leo::adaptive::tracking::research::streaming_kalman_v2::reconstruct(v,config());assert(contains(r,late,9));
    for(const auto& track:r.tracks)assert(track.end_utc_ns-track.start_utc_ns<5'000'000'000LL||
        track.points.size()>=8);}
void lane_and_rf_are_exact(){std::vector<Candidate> v;
    for(unsigned t=0;t<10;++t){v.push_back(point(4000+t,t,t,3*t,0,3,"lower",1000));
        v.push_back(point(4100+t,100+t,t,3*t,1,3,"lower",1000));
        v.push_back(point(4200+t,200+t,t,3*t,0,3,"upper",1000));}
    auto r=leo::adaptive::tracking::research::streaming_kalman_v2::reconstruct(v,config());
    assert(r.stats.lanes==3);for(const auto& track:r.tracks)for(const auto& p:track.points){
        unsigned matches=0;for(const auto& c:v)if(c.candidate_id==p.candidate_id)
            matches+=(c.receiver_id==track.lane.receiver_id&&c.edge==track.lane.edge&&c.actual_rf_hz==track.lane.actual_rf_hz);
        assert(matches==1);}}
void timestamp_jitter_within_source(){std::vector<Candidate> v;std::vector<std::string> truth;
    for(unsigned t=0;t<10;++t){auto p=point(5000+t,t,t+.001*(t%3),5*t);truth.push_back(p.candidate_id);v.push_back(p);
        if(t==4){auto q=point(5100+t,t,t+.006,38);v.push_back(q);}}
    auto r=leo::adaptive::tracking::research::streaming_kalman_v2::reconstruct(v,config());assert(contains(r,truth,9));}
void alias_rate_and_validation(){std::vector<Candidate> v;std::vector<std::string> truth;
    for(unsigned t=0;t<10;++t){v.push_back(point(6000+t,t,.5*t,(12+20*t)/1.25,0,3,
        "lower",800,100));truth.push_back(id(6000+t));}
    auto r=leo::adaptive::tracking::research::streaming_kalman_v2::reconstruct(v,config());assert(contains(r,truth,8));
    bool rejected=false;try{auto bad=config();bad.association_branches=0;(void)
        leo::adaptive::tracking::research::streaming_kalman_v2::reconstruct(v,bad);}catch(const std::invalid_argument&){rejected=true;}
    assert(rejected);}
void duplicate_alternatives_do_not_monopolize_late_births(){
    std::vector<Candidate> v;std::vector<std::string> early,late;
    for(unsigned t=0;t<10;++t){
        for(unsigned alternative=0;alternative<8;++ alternative)
            v.push_back(point(7000+100*t+alternative,t,t,10+3*t+.05*alternative));
        early.push_back(id(100000+t));
    }
    for(unsigned t=0;t<10;++t){
        for(unsigned alternative=0;alternative<8;++alternative)
            v.push_back(point(9000+100*t+alternative,100+t,12+t,-35+5*t+.05*alternative));
        late.push_back(id(100100+t));
    }
    auto c=config();c.maximum_output_tracks_per_lane=16;
    auto r=leo::adaptive::tracking::research::streaming_kalman_v2::reconstruct(v,c);
    assert(contains_sources(r,early,8));assert(contains_sources(r,late,8));
    std::size_t early_copies=0,late_copies=0;
    for(const auto& track:r.tracks){std::size_t em=0,lm=0;for(const auto& p:track.points){
        em+=std::find(early.begin(),early.end(),p.source_group_id)!=early.end();
        lm+=std::find(late.begin(),late.end(),p.source_group_id)!=late.end();}
        early_copies+=em>=8;late_copies+=lm>=8;}
    assert(early_copies<=2);assert(late_copies<=4);assert(r.tracks.size()<=6);
    assert(r.stats.near_duplicate_hypotheses_removed>0);
}
}
int main(){curved_alias_clutter();crossing_alternatives();gap_and_rolling_birth();lane_and_rf_are_exact();
    timestamp_jitter_within_source();alias_rate_and_validation();
    duplicate_alternatives_do_not_monopolize_late_births();}
