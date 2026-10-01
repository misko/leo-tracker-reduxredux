#include "streaming_rolling_backfill.hpp"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
using namespace leo::adaptive::tracking;
using namespace leo::adaptive::tracking::research::streaming_rolling_backfill;
using RollingConfig=leo::adaptive::tracking::research::streaming_rolling_backfill::Config;
using RollingResult=leo::adaptive::tracking::research::streaming_rolling_backfill::Result;
namespace {
std::string id(unsigned n){constexpr char h[]="0123456789abcdef";std::string s="sha256:"+std::string(64,'0');for(unsigned i=0;i<8;++i){s[s.size()-1-i]=h[n&15];n>>=4;}return s;}
Candidate p(unsigned n,unsigned source,double t,double f,int receiver=0,double jitter=0){constexpr std::int64_t epoch=1700000000000000000LL;auto center=epoch+static_cast<std::int64_t>((t+jitter)*1e9);double spacing=100;f-=std::nearbyint(f/spacing)*spacing;return{id(n),id(100000+source),receiver,2,"lower",1000,center-100,center,center+100,f,1,.1,.9};}
RollingConfig cfg(){RollingConfig c;c.canonical_rf_hz=1000;c.alias_spacing_hz=100;c.residual_gate_hz=5;c.maximum_uncertainty_hz=5;c.minimum_rate_hz_per_s=-50;c.maximum_rate_hz_per_s=50;c.maximum_gap_s=2.1;c.maximum_active_per_lane=24;return c;}
bool has(const RollingResult&r,const std::vector<std::string>&truth,std::size_t count){for(const auto&t:r.tracks){std::size_t n=0;for(const auto&q:t.points)n+=std::find(truth.begin(),truth.end(),q.candidate_id)!=truth.end();if(n>=count)return true;}return false;}
void curved_alias_clutter_jitter(){std::vector<Candidate>v;std::vector<std::string>a;for(unsigned i=0;i<14;++i){double t=.5*i,f=10+5*t+1.2*t*t;v.push_back(p(100+i,i,t,f,0,(static_cast<int>(i%3)-1)*.0002));a.push_back(id(100+i));v.push_back(p(500+i,i,t,-30+2*t));}auto r=reconstruct(v,cfg());assert(has(r,a,8));}
void crossing_and_late_birth(){std::vector<Candidate>v;std::vector<std::string>a,b;for(unsigned i=0;i<18;++i){double t=.5*i;v.push_back(p(1000+i,i,t,-25+7*t));a.push_back(id(1000+i));if(i>=5){v.push_back(p(2000+i,i,t,45-5*t));b.push_back(id(2000+i));}}auto r=reconstruct(v,cfg());assert(has(r,a,10));assert(has(r,b,8));}
void gap_and_lane(){std::vector<Candidate>v;for(unsigned i=0;i<4;++i)v.push_back(p(3000+i,i,.5*i,3*i));for(unsigned i=0;i<7;++i)v.push_back(p(3100+i,10+i,6+.5*i,18+3*i));auto r=reconstruct(v,cfg());assert(r.tracks.empty());}
void interleaved_source_group_is_atomic(){std::vector<Candidate>v;std::vector<std::string>truth;for(unsigned i=0;i<10;++i){auto main=p(4000+i,i,i,4*i);truth.push_back(main.candidate_id);v.push_back(main);if(i==4){auto alternate=p(4500,i,i,30,0,.001);v.push_back(alternate);}}auto r=reconstruct(v,cfg());assert(has(r,truth,9));for(const auto&t:r.tracks){std::int64_t start=std::numeric_limits<std::int64_t>::max(),end=0;for(const auto&q:t.points){auto row=std::find_if(v.begin(),v.end(),[&](const Candidate&x){return x.candidate_id==q.candidate_id;});assert(row!=v.end());start=std::min(start,row->support_start_utc_ns);end=std::max(end,row->support_end_utc_ns);assert(std::abs(q.normalized_dealiased_cfo_hz-(q.normalized_raw_cfo_hz-q.relative_alias_index*100.0))<1e-8);}assert(t.start_utc_ns==start&&t.end_utc_ns==end);}}
void validation(){auto v=std::vector<Candidate>{p(1,1,0,0),p(2,2,1,1)};for(int which=0;which<5;++which){bool bad=false;try{auto c=cfg();if(which==0)c.window_s=7;if(which==1)c.history_buffer_s=33;if(which==2)c.maximum_backfill_s=17;if(which==3)c.maximum_fit_points=1;if(which==4)c.alias_spacing_hz=0;(void)reconstruct(v,c);}catch(const std::invalid_argument&){bad=true;}assert(bad);}auto jitter=v;jitter.push_back(p(3,1,.021,2));bool rejected=false;try{(void)reconstruct(jitter,cfg());}catch(const std::invalid_argument&){rejected=true;}assert(rejected);}
void bounded_backfill_trigger_and_history(){std::vector<Candidate>v;for(unsigned i=0;i<24;++i){auto truth=p(8000+i,i,.5*i,8+3*i);if(i<7){truth.control_score=.1;truth.margin=.02;}v.push_back(truth);for(unsigned j=0;j<6;++j)v.push_back(p(9000+i*10+j,i,.5*i,-45+9*j+2*i));}auto r=reconstruct(v,cfg());assert(r.stats.backfill_triggers>0);assert(r.stats.backfill_points>0);for(const auto&t:r.tracks){std::set<std::string> sources;for(const auto&q:t.points)assert(sources.insert(q.source_group_id).second);for(std::size_t i=1;i<t.points.size();++i){auto a=std::find_if(v.begin(),v.end(),[&](const Candidate&x){return x.candidate_id==t.points[i-1].candidate_id;});auto b=std::find_if(v.begin(),v.end(),[&](const Candidate&x){return x.candidate_id==t.points[i].candidate_id;});assert(a->support_center_utc_ns<=b->support_center_utc_ns);}}}
void noncanonical_rf_normalizes_aliases(){std::vector<Candidate>v;std::vector<std::string>truth;for(unsigned i=0;i<12;++i){auto q=p(12000+i,i,.5*i,2*i);q.actual_rf_hz=2000;v.push_back(q);truth.push_back(q.candidate_id);}auto r=reconstruct(v,cfg());assert(has(r,truth,8));for(const auto&t:r.tracks)for(const auto&q:t.points)assert(std::abs(q.normalized_dealiased_cfo_hz-(q.normalized_raw_cfo_hz-q.relative_alias_index*50.0))<1e-8);}
}
int main(){curved_alias_clutter_jitter();crossing_and_late_birth();gap_and_lane();interleaved_source_group_is_atomic();bounded_backfill_trigger_and_history();noncanonical_rf_normalizes_aliases();validation();}
