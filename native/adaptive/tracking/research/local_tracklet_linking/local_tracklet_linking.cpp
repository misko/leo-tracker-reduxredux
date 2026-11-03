#include "local_tracklet_linking.hpp"
#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <stdexcept>
#include <tuple>

namespace leo::adaptive::tracking::research::local_tracklet_linking { namespace {
constexpr double ns=1e9;
struct Key { int r,c; std::string e; double rf; bool operator<(const Key&o)const{return std::tie(r,c,e,rf)<std::tie(o.r,o.c,o.e,o.rf);} };
struct P { const tracking::Candidate* c; double t,raw,w; };
struct G { std::string id; double t; std::vector<P> p; };
struct F { std::vector<P> p; double t0{},t1{},ref{},a{},b{},rms{},mx{},score{}; };
double weight(const tracking::Candidate& c){return std::min(16.0,std::max(0.0,c.margin)/std::max(.02,c.control_score));}
double alias(double raw,double predicted,double spacing){return raw+std::nearbyint((predicted-raw)/spacing)*spacing;}
void fit(F& f){
 double sw=0,st=0,sy=0; for(auto&p:f.p){sw+=p.w;st+=p.w*p.t;sy+=p.w*p.raw;} f.ref=st/sw; double xx=0,xy=0;
 for(auto&p:f.p){double x=p.t-f.ref;xx+=p.w*x*x;xy+=p.w*x*p.raw;} f.b=xx>0?xy/xx:0; f.a=sy/sw;
 double ss=0;f.mx=0;f.score=0;f.t0=f.p.front().t;f.t1=f.p.back().t; for(auto&p:f.p){double d=p.raw-(f.a+f.b*(p.t-f.ref));ss+=p.w*d*d;f.mx=std::max(f.mx,std::abs(d));f.score+=p.w;} f.rms=std::sqrt(ss/sw);
}
bool valid_digest(const std::string&s){if(s.size()!=71||s.substr(0,7)!="sha256:")return false;return std::all_of(s.begin()+7,s.end(),[](char c){return std::isxdigit(static_cast<unsigned char>(c));});}
void validate(const std::vector<tracking::Candidate>& in,const Config& c){
 if(in.empty()||in.size()>c.maximum_input_points||c.window_s<=0||c.window_step_s<=0||c.residual_gate_hz<=0||c.link_frequency_gate_hz<=0||c.maximum_gap_s<0||c.minimum_support<2)throw std::invalid_argument("invalid local-tracklet config/input");
 std::set<std::string> ids;std::map<std::string,std::tuple<int,int,std::string,double>> groups;std::map<std::string,std::size_t> counts;
 for(auto&x:in){if(!valid_digest(x.candidate_id)||!valid_digest(x.source_group_id)||!ids.insert(x.candidate_id).second||x.receiver_id<0||x.channel<1||(x.edge!="lower"&&x.edge!="upper")||!std::isfinite(x.actual_rf_hz)||!std::isfinite(x.measured_cfo_hz)||x.support_start_utc_ns<=0||x.support_start_utc_ns>x.support_center_utc_ns||x.support_center_utc_ns>=x.support_end_utc_ns||x.margin<=0)throw std::invalid_argument("invalid local-tracklet candidate");auto auth=std::make_tuple(x.receiver_id,x.channel,x.edge,x.actual_rf_hz);auto q=groups.emplace(x.source_group_id,auth);if(!q.second&&q.first->second!=auth)throw std::invalid_argument("source group changes lane");if(++counts[x.source_group_id]>c.maximum_candidates_per_group)throw std::invalid_argument("source group candidate bound");}
}
F grow(const std::vector<G>& gs,std::size_t lo,std::size_t hi,const P& p0,const P& p1,const Config& c){
 F f; f.p={p0,p1};fit(f);std::set<std::string> used{p0.c->source_group_id,p1.c->source_group_id};
 for(std::size_t i=lo;i<hi;++i){if(used.count(gs[i].id))continue;const P*best=nullptr;double bf=0,bd=c.residual_gate_hz;for(auto&p:gs[i].p){double pred=f.a+f.b*(p.t-f.ref);double y=alias(p.raw,pred,c.alias_spacing_hz),d=std::abs(y-pred);if(d<bd){bd=d;best=&p;bf=y;}}if(best){P q=*best;q.raw=bf;f.p.push_back(q);used.insert(gs[i].id);std::sort(f.p.begin(),f.p.end(),[](auto&a,auto&b){return a.t<b.t;});fit(f);}}
 return f;
}
F local_end(const F&f,bool tail,double span){F z;const double edge=tail?f.t1:f.t0;for(auto&p:f.p)if(tail?p.t>=edge-span:p.t<=edge+span)z.p.push_back(p);if(z.p.size()<2)z=f;else fit(z);return z;}
bool compatible(const F&a,const F&b,const Config&c){double gap=b.t0-a.t1;if(gap>c.maximum_gap_s||gap<-c.window_s)return false;F x=local_end(a,true,c.window_s),y=local_end(b,false,c.window_s);double t=std::max(a.t1,b.t0);double fa=x.a+x.b*(t-x.ref),fb=y.a+y.b*(t-y.ref);return std::abs(fa-fb)<=c.link_frequency_gate_hz&&std::abs(x.b-y.b)<=c.link_rate_gate_hz_per_s;}
F merge(const F&a,const F&b,const Config&c){F z=a,x=local_end(a,true,c.window_s);std::set<std::string> used;for(auto&p:z.p)used.insert(p.c->source_group_id);for(auto p:b.p)if(used.insert(p.c->source_group_id).second){double pred=x.a+x.b*(p.t-x.ref);p.raw=alias(p.raw,pred,c.alias_spacing_hz);z.p.push_back(p);}std::sort(z.p.begin(),z.p.end(),[](auto&u,auto&v){return u.t<v.t;});fit(z);return z;}
tracking::Track output(const F&f,const Key&k,std::size_t n,const Config&c){tracking::Track t;t.segment_id="local-tracklet-linking";t.tracklet_id="linked-"+std::to_string(n);t.lane={k.c,k.e,k.r,k.rf};t.start_utc_ns=f.p.front().c->support_start_utc_ns;t.end_utc_ns=f.p.front().c->support_end_utc_ns;for(auto&p:f.p){t.start_utc_ns=std::min(t.start_utc_ns,p.c->support_start_utc_ns);t.end_utc_ns=std::max(t.end_utc_ns,p.c->support_end_utc_ns);}t.reference_utc_ns=static_cast<std::int64_t>(std::llround(f.ref*ns));t.normalized_rate_hz_per_s=f.b;t.normalized_intercept_hz=f.a;t.residual_rms_hz=f.rms;t.residual_max_hz=f.mx;t.weighted_support=f.score;const double scale=c.canonical_rf_hz/k.rf,spacing=c.alias_spacing_hz*scale;for(auto&p:f.p){double raw=p.c->measured_cfo_hz*scale;int ai=static_cast<int>(std::llround((raw-p.raw)/spacing));t.points.push_back({p.c->candidate_id,p.c->source_group_id,ai,raw,p.raw});}return t;}
}
Result reconstruct(const std::vector<tracking::Candidate>& in,const Config& c){validate(in,c);Result out;out.input_candidate_count=in.size();std::map<Key,std::map<std::string,std::vector<const tracking::Candidate*>>> lanes;for(auto&x:in)if(weight(x)>=.1)lanes[{x.receiver_id,x.channel,x.edge,x.actual_rf_hz}][x.source_group_id].push_back(&x);out.stats.lanes=lanes.size();
 for(auto&lv:lanes){Config lc=c;const double scale=c.canonical_rf_hz/lv.first.rf;lc.alias_spacing_hz*=scale;std::vector<G> gs;for(auto&sv:lv.second){G g;g.id=sv.first;double sum=0;for(auto*x:sv.second)sum+=x->support_center_utc_ns/ns;g.t=sum/sv.second.size();for(auto*x:sv.second)g.p.push_back({x,x->support_center_utc_ns/ns,x->measured_cfo_hz*scale,weight(*x)});gs.push_back(std::move(g));}std::sort(gs.begin(),gs.end(),[](auto&a,auto&b){return a.t<b.t;});if(gs.size()<2)continue;std::vector<F> fs;double first=gs.front().t,last=gs.back().t;for(double ws=first;ws<=last;ws+=c.window_step_s){++out.stats.windows;auto l=std::lower_bound(gs.begin(),gs.end(),ws,[](auto&g,double t){return g.t<t;});auto h=std::upper_bound(gs.begin(),gs.end(),ws+c.window_s,[](double t,auto&g){return t<g.t;});std::size_t lo=l-gs.begin(),hi=h-gs.begin();if(hi-lo<3)continue;std::size_t seeds=0;for(auto&p0:gs[lo].p)for(std::size_t j=hi;j-->lo+1;)for(auto&p1:gs[j].p){double dt=p1.t-p0.t;if(dt<=0)continue;double y1=alias(p1.raw,p0.raw,lc.alias_spacing_hz),rate=(y1-p0.raw)/dt;if(rate<c.minimum_rate_hz_per_s||rate>c.maximum_rate_hz_per_s)continue;++out.stats.local_seeds;F f=grow(gs,lo,hi,p0,P{p1.c,p1.t,y1,p1.w},lc);if(f.p.size()>=3&&f.mx<=c.residual_gate_hz&&fs.size()<c.maximum_fragments_per_lane)fs.push_back(std::move(f));if(++seeds>=c.maximum_local_seeds_per_window)break;if(seeds>=c.maximum_local_seeds_per_window)break;} }
 out.stats.fragments+=fs.size();std::sort(fs.begin(),fs.end(),[](auto&a,auto&b){return a.t0<b.t0||(a.t0==b.t0&&a.score>b.score);});std::vector<F> chains;for(auto&f:fs){std::size_t bi=chains.size();double bs=-1e300;for(std::size_t i=0;i<chains.size();++i){++out.stats.link_tests;if(compatible(chains[i],f,lc)&&chains[i].score>bs){bs=chains[i].score;bi=i;}}if(bi==chains.size())chains.push_back(f);else chains[bi]=merge(chains[bi],f,lc);}
 std::sort(chains.begin(),chains.end(),[](auto&a,auto&b){return a.score>b.score;});std::size_t kept=0;for(auto&f:chains){if(f.p.size()<c.minimum_support||f.t1-f.t0<c.minimum_span_s||std::abs(f.b)>c.maximum_rate_hz_per_s)continue;out.tracks.push_back(output(f,lv.first,out.tracks.size(),c));if(++kept>=c.maximum_tracks_per_lane)break;}}
 std::set<std::string> used;for(auto&t:out.tracks)for(auto&p:t.points)used.insert(p.candidate_id);out.used_candidate_count=used.size();return out;}
} // namespace
