#include "online.hpp"
#include "pipeline.hpp"
#include "tracking.hpp"
#include "location.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <charconv>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <vector>

using leo::adaptive::Observation;
using leo::adaptive::pipeline::GraphAuthority;
using leo::adaptive::pipeline::LocationTrackBatch;
using leo::adaptive::pipeline::SupportAuthority;
using leo::adaptive::tracking::Candidate;

static std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> out; std::size_t p=0;
    for (;;) { auto q=line.find('\t',p); out.push_back(line.substr(p,q-p));
        if(q==std::string::npos)return out;
        p=q+1; }
}
template<class T> static T integer(const std::string& s) {
    errno=0; char* e=nullptr; long long v=std::strtoll(s.c_str(),&e,10);
    if(errno||e!=s.c_str()+s.size()||v<std::numeric_limits<T>::min()||v>std::numeric_limits<T>::max())
        throw std::runtime_error("integer");
    return static_cast<T>(v);
}
static double number(const std::string& s) { char* e=nullptr; double v=std::strtod(s.c_str(),&e);
    if(e!=s.c_str()+s.size())throw std::runtime_error("number");
    return v; }
static std::string shortest(double value) {
    char text[64];
    const auto result=std::to_chars(text,text+sizeof(text),value,std::chars_format::general);
    if(result.ec!=std::errc{}) throw std::runtime_error("shortest formatting");
    return std::string(text,result.ptr);
}
static std::vector<leo_tle_record> read_tles(const std::string& path,std::size_t limit) {
    std::ifstream f(path); std::size_t n=0; if(!(f>>n))throw std::runtime_error("tles"); f.ignore(1024,'\n');
    n=std::min(n,limit); std::vector<leo_tle_record> out(n);
    for(std::size_t i=0;i<n;++i){std::string a,b;std::getline(f,a);std::getline(f,b);
        out[i].satellite_id=integer<int32_t>(a.substr(2,5));std::memcpy(out[i].line1,a.data(),69);
        std::memcpy(out[i].line2,b.data(),69);out[i].line1[69]=out[i].line2[69]='\0';} return out;
}
static leo_location_site site(double latd,double lond){constexpr double pi=3.14159265358979323846,a=6378.137,f=1/298.257223563,e=f*(2-f);
    double lat=latd*pi/180,lon=lond*pi/180,n=a/std::sqrt(1-e*std::sin(lat)*std::sin(lat)); leo_location_site s{};
    s.ecef_km[0]=n*std::cos(lat)*std::cos(lon);s.ecef_km[1]=n*std::cos(lat)*std::sin(lon);s.ecef_km[2]=n*(1-e)*std::sin(lat);
    s.up[0]=std::cos(lat)*std::cos(lon);s.up[1]=std::cos(lat)*std::sin(lon);s.up[2]=std::sin(lat);return s;}
struct Score { double rms{}; double mse{}; uint32_t matched{},unmatched{}; leo_score_stats stats{}; };
static Score score(const LocationTrackBatch& b,const leo_orbit_snapshot& orbit){uint32_t maxn=0;for(auto&r:b.records)maxn=std::max(maxn,r.observation_count);
    std::unique_ptr<leo_score_context,decltype(&leo_score_context_destroy)> c(leo_score_context_create(maxn,11),&leo_score_context_destroy);
    std::vector<leo_track_score> t(b.records.size());leo_track_scores_clear(t.data(),t.size());auto cfg=leo_score_default_config();auto s=site(38.5,-121.5);Score o;leo_point_score p{};
    if(!c||leo_score_partition(c.get(),&orbit,b.records.data(),b.records.size(),&s,&cfg,0,orbit.satellite_count,t.data(),&o.stats)!=LEO_LOCATION_OK||
       leo_point_score_finish(b.records.data(),b.records.size(),t.data(),&cfg,&p)!=LEO_LOCATION_OK)throw std::runtime_error("score");
    o.rms=p.residual_rmse_hz;o.mse=p.weighted_mse_hz2;o.matched=p.matched_track_count;o.unmatched=p.unmatched_track_count;return o;}
int main(int argc,char**argv){try{if(argc!=5)throw std::runtime_error("usage LABEL CAND GRAPH TLES");
    std::ifstream g(argv[3]);std::string line;std::getline(g,line);auto m=fields(line);GraphAuthority supplied{m[1],m[2],integer<int64_t>(m[3]),{}};std::getline(g,line);
    while(std::getline(g,line)){auto r=fields(line);supplied.candidates.emplace(r[0],SupportAuthority{integer<int64_t>(r[1]),integer<int64_t>(r[2]),integer<int64_t>(r[3]),r[4],r[5],r[6],r[7]});}
    std::ifstream c(argv[2]);std::getline(c,line);std::vector<Candidate> all;while(std::getline(c,line)){auto r=fields(line);all.push_back({r[0],r[1],integer<int>(r[2]),integer<int>(r[3]),r[4],number(r[5]),integer<int64_t>(r[6]),integer<int64_t>(r[7]),integer<int64_t>(r[8]),number(r[9]),number(r[10]),number(r[11]),number(r[12])});}
    auto first=std::min_element(all.begin(),all.end(),[](auto&a,auto&b){return a.support_end_utc_ns<b.support_end_utc_ns;})->support_end_utc_ns;
    std::vector<Candidate> prefix;for(auto&x:all)if(x.support_end_utc_ns<=first+10000000000LL)prefix.push_back(x);
    std::sort(prefix.begin(),prefix.end(),[](auto&a,auto&b){return std::tie(a.support_end_utc_ns,a.candidate_id)<std::tie(b.support_end_utc_ns,b.candidate_id);});
    GraphAuthority derived{supplied.session_id,supplied.input_manifest_digest,supplied.session_start_utc_ns,{}};
    GraphAuthority roundtrip{supplied.session_id,supplied.input_manifest_digest,supplied.session_start_utc_ns,{}};
    size_t m2lex=0,m3lex=0,m2num=0,m3num=0,short_m2lex=0,short_m3lex=0;
    for(auto&x:prefix){auto f=supplied.candidates.at(x.candidate_id);Observation o{};o.candidate_id=x.candidate_id;o.source_group_id=x.source_group_id;o.generation=1;o.receiver=x.receiver_id;o.channel=x.channel;o.upper_edge=x.edge=="upper";o.actual_rf_hz=x.actual_rf_hz;o.measured_cfo_hz=x.measured_cfo_hz;o.exact_score=x.exact_score;o.control_score=x.control_score;o.margin=x.margin;o.support_start_utc_ns=x.support_start_utc_ns;o.support_center_utc_ns=x.support_center_utc_ns;o.support_end_utc_ns=x.support_end_utc_ns;o.standard_uncertainty_hz=400;o.moment2=number(f.moment2);o.moment3=number(f.moment3);auto d=leo::adaptive::online::derive_support_authority(o);m2lex+=d.moment2!=f.moment2;m3lex+=d.moment3!=f.moment3;m2num+=number(d.moment2)!=number(f.moment2);m3num+=number(d.moment3)!=number(f.moment3);derived.candidates.emplace(x.candidate_id,std::move(d));auto s=f;s.moment2=shortest(o.moment2);s.moment3=shortest(o.moment3);short_m2lex+=s.moment2!=f.moment2;short_m3lex+=s.moment3!=f.moment3;roundtrip.candidates.emplace(x.candidate_id,std::move(s));}
    auto tr=leo::adaptive::tracking::reconstruct(prefix);auto a=leo::adaptive::pipeline::make_location_tracks(tr,supplied);auto b=leo::adaptive::pipeline::make_location_tracks(tr,derived);auto q=leo::adaptive::pipeline::make_location_tracks(tr,roundtrip);
    auto compare=[](const LocationTrackBatch& left,const LocationTrackBatch& right){std::array<size_t,4> out{};for(size_t i=0;i<left.owned.size();++i){out[0]+=left.owned[i].support_digest!=right.owned[i].support_digest;out[1]+=left.owned[i].partition_seed!=right.owned[i].partition_seed;bool any=false;for(size_t k=0;k<left.owned[i].training_mask.size();++k){bool d=left.owned[i].training_mask[k]!=right.owned[i].training_mask[k];out[3]+=d;any|=d;}out[2]+=any;}return out;};
    auto differences=compare(a,b),short_differences=compare(a,q);
    auto tle=read_tles(argv[4],4096);std::unique_ptr<leo_orbit_context,decltype(&leo_orbit_context_destroy)> oc(leo_orbit_context_create(4096,64),&leo_orbit_context_destroy);leo_orbit_snapshot os{};
    if(!oc||leo_orbit_build_tle(oc.get(),2,supplied.session_start_utc_ns,-10,1,32,tle.data(),tle.size(),&os)!=LEO_LOCATION_OK)throw std::runtime_error("orbit");
    auto sa=score(a,os),sb=score(b,os),sq=score(q,os);
    std::cout<<std::setprecision(17)<<"{\"scope\":\""<<argv[1]<<"\",\"prefix\":"<<prefix.size()<<",\"tracks\":"<<tr.tracks.size()<<",\"derived17\":{\"moment2_lexeme_mismatches\":"<<m2lex<<",\"moment3_lexeme_mismatches\":"<<m3lex<<",\"moment2_numeric_mismatches\":"<<m2num<<",\"moment3_numeric_mismatches\":"<<m3num<<",\"support_digest_mismatches\":"<<differences[0]<<",\"partition_seed_mismatches\":"<<differences[1]<<",\"mask_track_mismatches\":"<<differences[2]<<",\"mask_bit_mismatches\":"<<differences[3]<<",\"score_hz\":"<<sb.rms<<",\"score_delta_hz\":"<<(sb.rms-sa.rms)<<"},\"shortest_roundtrip\":{\"moment2_lexeme_mismatches\":"<<short_m2lex<<",\"moment3_lexeme_mismatches\":"<<short_m3lex<<",\"support_digest_mismatches\":"<<short_differences[0]<<",\"partition_seed_mismatches\":"<<short_differences[1]<<",\"mask_track_mismatches\":"<<short_differences[2]<<",\"mask_bit_mismatches\":"<<short_differences[3]<<",\"score_hz\":"<<sq.rms<<",\"score_delta_hz\":"<<(sq.rms-sa.rms)<<"},\"supplied_score_hz\":"<<sa.rms<<",\"supplied_matched\":"<<sa.matched<<",\"derived17_matched\":"<<sb.matched<<",\"shortest_matched\":"<<sq.matched<<"}\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
