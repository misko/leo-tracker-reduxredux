#include "local_tracklet_linking_v2.hpp"
#include <cassert>
#include <cmath>
#include <string>
#include <vector>
using namespace leo::adaptive::tracking;
using namespace leo::adaptive::tracking::research::local_tracklet_linking_v2;
std::string id(unsigned n){const char*h="0123456789abcdef";std::string s="sha256:"+std::string(64,'0');for(int i=0;i<8;++i){s[s.size()-1-i]=h[n&15];n>>=4;}return s;}
Candidate p(unsigned n,unsigned g,double t,double y,int r=0){std::int64_t z=1700000000000000000LL+(std::int64_t)(t*1e9);double spacing=100;double raw=y-std::nearbyint(y/spacing)*spacing;return{id(n),id(100000+g),r,2,"lower",1000,z-100,z,z+100,raw,1,.1,.9};}
using LConfig=leo::adaptive::tracking::research::local_tracklet_linking_v2::Config;
using LResult=leo::adaptive::tracking::research::local_tracklet_linking_v2::Result;
LConfig cfg(){LConfig c;c.canonical_rf_hz=1120;c.alias_spacing_hz=100;c.residual_gate_hz=5;c.link_frequency_gate_hz=8;c.link_rate_gate_hz_per_s=8;c.minimum_rate_hz_per_s=-50;c.maximum_rate_hz_per_s=50;c.maximum_gap_s=4;c.minimum_support=8;c.minimum_span_s=4;c.maximum_local_seeds_per_window=128;return c;}
bool has(const LResult&r,unsigned base){for(auto&t:r.tracks){unsigned n=0;for(auto&q:t.points)for(unsigned i=0;i<12;++i)n+=q.candidate_id==id(base+i);if(n>=8)return true;}return false;}
int main(){
 {std::vector<Candidate>v;for(unsigned i=0;i<12;++i){if(i!=6)v.push_back(p(100+i,i,i,10+2*i+.12*i*i));v.push_back(p(900+i,i,i,-40+3*i));}auto r=reconstruct(v,cfg());assert(has(r,100));}
 {std::vector<Candidate>v;for(unsigned i=0;i<12;++i){double j=(i%2?.015:-.012);v.push_back(p(200+i,i,i+j,-25+6*i));v.push_back(p(300+i,i,i+j,42-5*i));v.push_back(p(800+i,50+i,i+j,45));}auto r=reconstruct(v,cfg());assert(has(r,200));assert(has(r,300));}
 {std::vector<Candidate>v;for(unsigned i=0;i<9;++i)v.push_back(p(400+i,i,i,45+13*i));auto r=reconstruct(v,cfg());assert(has(r,400));}
 {std::vector<Candidate>v;for(unsigned burst=0;burst<80;++burst)for(unsigned i=0;i<3;++i)for(unsigned k=0;k<4;++k)v.push_back(p(10000+12*burst+4*i+k,1000+3*burst+i,10*burst+.5*i,-45+27*k+3*(burst%7)));for(unsigned i=0;i<12;++i)v.push_back(p(500+i,5000+i,810+i,12+4*i));auto r=reconstruct(v,cfg());assert(has(r,500));}
 return 0;
}
