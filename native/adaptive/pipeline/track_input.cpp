#include "track_input.hpp"
#include "sha256.hpp"
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <limits>
#include <set>
#include <stdexcept>
#include <unordered_map>

namespace leo::adaptive::pipeline {
namespace {
std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> result;
    std::size_t begin=0;
    while(true) {
        auto end=line.find('\t',begin);
        result.push_back(line.substr(begin,end-begin));
        if(end==std::string::npos)return result;
        begin=end+1;
    }
}
long long integer(const std::string& text) {
    if(text.empty() || text.find_first_not_of("-0123456789")!=std::string::npos)
        throw std::invalid_argument("invalid checkpoint integer");
    char* end=nullptr;errno=0;auto value=std::strtoll(text.c_str(),&end,10);
    if(errno || end!=text.c_str()+text.size())throw std::invalid_argument("invalid checkpoint integer");
    return value;
}
int small_integer(const std::string& text) {
    auto value=integer(text);
    if(value<std::numeric_limits<int>::min() || value>std::numeric_limits<int>::max())
        throw std::invalid_argument("checkpoint integer overflow");
    return static_cast<int>(value);
}
double real(const std::string& text) {
    if(text.empty())throw std::invalid_argument("empty checkpoint number");
    char* end=nullptr;errno=0;auto value=std::strtod(text.c_str(),&end);
    if(errno || end!=text.c_str()+text.size() || !std::isfinite(value))
        throw std::invalid_argument("invalid checkpoint number");
    return value;
}
void require(bool valid,const char* message) {if(!valid)throw std::invalid_argument(message);}
bool close(double a,double b) {return std::abs(a-b)<=1e-7+2e-15*std::max(std::abs(a),std::abs(b));}
std::string hash(const std::string& text) {return "sha256:"+leo::adaptive::sha256(text);}
}

tracking::Result read_track_checkpoint(std::istream& input,
    const std::vector<tracking::Candidate>& observations) {
    require(observations.size()<=40000,"too many checkpoint observations");
    std::unordered_map<std::string,const tracking::Candidate*> by_id;
    for(const auto& c:observations)require(by_id.emplace(c.candidate_id,&c).second,"duplicate observation");
    std::string line;
    require(bool(std::getline(input,line)),"missing checkpoint summary");
    auto summary=fields(line);
    require(summary.size()==4 && summary[0]=="SUMMARY","invalid checkpoint summary");
    auto count=integer(summary[1]),used=integer(summary[2]),tracks=integer(summary[3]);
    require(count==static_cast<long long>(observations.size()) && used>=0 && used<=count &&
            tracks>=0 && tracks<=40000,"invalid checkpoint counts");
    require(bool(std::getline(input,line)),"missing checkpoint config");
    auto config=fields(line);
    require(config.size()==2 && config[0]=="CONFIG" && !config[1].empty(),"invalid checkpoint config");
    tracking::Result result;
    result.input_candidate_count=observations.size();result.used_candidate_count=used;
    result.config_digest=hash("native-track-checkpoint-config-v1\n"+config[1]);
    std::size_t expected_points=0;
    std::set<std::string> groups,all_used;
    std::int64_t first=0,last=0;
    std::string material;
    auto finish=[&]() {
        if(result.tracks.empty())return;
        auto& t=result.tracks.back();
        require(!t.points.empty() && t.points.size()==expected_points,"checkpoint point count mismatch");
        require(t.start_utc_ns==first && t.end_utc_ns==last,"checkpoint support mismatch");
        t.tracklet_id=hash("native-track-checkpoint-track-v1\n"+result.config_digest+material);
        t.segment_id=t.tracklet_id;
    };
    while(std::getline(input,line)) {
        require(line.size()<=1024*1024,"checkpoint line too large");
        auto f=fields(line);
        if(f[0]=="TRACK") {
            finish();
            require(f.size()==17 && integer(f[1])==static_cast<long long>(result.tracks.size()),"invalid checkpoint track");
            tracking::Track t;
            t.lane={small_integer(f[5]),f[6],small_integer(f[4]),real(f[7])};
            require(t.lane.actual_rf_hz>0 && (t.lane.edge=="lower" || t.lane.edge=="upper"),"invalid checkpoint lane");
            t.start_utc_ns=integer(f[8]);t.end_utc_ns=integer(f[9]);t.reference_utc_ns=integer(f[10]);
            require(t.start_utc_ns<t.end_utc_ns,"invalid checkpoint time range");
            t.normalized_rate_hz_per_s=real(f[11]);t.normalized_intercept_hz=real(f[12]);
            t.residual_rms_hz=real(f[13]);t.residual_max_hz=real(f[14]);t.weighted_support=real(f[15]);
            auto n=integer(f[16]);require(n>0 && n<=count,"invalid checkpoint point count");
            expected_points=static_cast<std::size_t>(n);groups.clear();material=line+'\n';
            first=std::numeric_limits<std::int64_t>::max();last=std::numeric_limits<std::int64_t>::min();
            result.tracks.push_back(std::move(t));
        } else if(f[0]=="POINT") {
            require(f.size()==7 && !result.tracks.empty() && integer(f[1])==static_cast<long long>(result.tracks.size()-1),"invalid checkpoint point");
            const auto found=by_id.find(f[2]);require(found!=by_id.end(),"unknown checkpoint candidate");
            const auto& c=*found->second;auto& t=result.tracks.back();
            require(c.source_group_id==f[3] && groups.insert(f[3]).second,"duplicate or mismatched checkpoint source");
            require(c.receiver_id==t.lane.receiver_id && c.channel==t.lane.channel && c.edge==t.lane.edge && c.actual_rf_hz==t.lane.actual_rf_hz,"checkpoint lane mismatch");
            auto alias=small_integer(f[4]);auto raw=real(f[5]),dealiased=real(f[6]);
            double scale=11.2e9/t.lane.actual_rf_hz;
            require(close(raw,c.measured_cfo_hz*scale),"checkpoint changed measured CFO");
            require(close(dealiased,raw-alias*scale/4.4e-6),"checkpoint alias mismatch");
            t.points.push_back({f[2],f[3],alias,raw,dealiased});all_used.insert(f[2]);material+=line+'\n';
            first=std::min(first,c.support_start_utc_ns);last=std::max(last,c.support_end_utc_ns);
        } else throw std::invalid_argument("unknown checkpoint row");
    }
    finish();
    require(result.tracks.size()==static_cast<std::size_t>(tracks) && all_used.size()==static_cast<std::size_t>(used),"checkpoint summary mismatch");
    return result;
}
}
