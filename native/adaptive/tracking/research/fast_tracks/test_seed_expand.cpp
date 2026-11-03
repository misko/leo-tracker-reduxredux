#include "seed_expand.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using leo::adaptive::tracking::Candidate;
using leo::adaptive::tracking::research::seed_expand::Config;
using leo::adaptive::tracking::research::seed_expand::Seed;

std::string digest(unsigned value) {
    constexpr char hex[]="0123456789abcdef";
    std::string result="sha256:"+std::string(64,'0');
    for (unsigned i=0;i<8;++i) {
        result[result.size()-1-i]=hex[value&15U];
        value>>=4U;
    }
    return result;
}

Candidate point(unsigned id,unsigned source,double time_s,double cfo) {
    constexpr std::int64_t origin=1'700'000'000'000'000'000LL;
    const auto center=origin+static_cast<std::int64_t>(time_s*1e9);
    return {digest(id),digest(10'000U+source),0,3,"lower",1'000.0,
        center-100,center,center+100,cfo,1.0,0.1,0.9};
}

Config config() {
    Config value;
    value.tracking.canonical_rf_hz=1'000.0;
    value.tracking.alias_spacing_hz=1'000'000.0;
    value.tracking.minimum_slope_hz_per_s=-100.0;
    value.tracking.maximum_slope_hz_per_s=100.0;
    value.tracking.residual_gate_hz=2.0;
    value.tracking.maximum_gap_s=2.0;
    value.tracking.minimum_span_s=4.0;
    value.tracking.minimum_support=5;
    value.tracking.minimum_point_weight=0.1;
    return value;
}

Seed seed(double slope,double intercept) {
    constexpr std::int64_t origin=1'700'000'000'000'000'000LL;
    return {{3,"lower",0,1'000.0},origin,origin+6'000'000'000LL,origin,
        slope,intercept};
}

void expands_crossing_tracks_from_all_candidates() {
    std::vector<Candidate> candidates;
    for (unsigned t=0;t<7;++t) {
        candidates.push_back(point(100U+t,t,static_cast<double>(t),10.0*t+10.0));
        candidates.push_back(point(200U+t,t,static_cast<double>(t),-10.0*t+72.0));
    }
    const auto result=leo::adaptive::tracking::research::seed_expand::expand(
        candidates,{seed(9.5,10.5),seed(-9.5,71.5)},config());
    assert(result.tracks.size()==2);
    assert(result.used_candidate_count>=10);
    assert(result.expanded_segment_count>=2);
    assert(result.tracks[0].points.size()>=5);
    assert(result.tracks[1].points.size()>=5);
    std::vector<Candidate> reversed=candidates;
    std::reverse(reversed.begin(),reversed.end());
    const auto repeat=leo::adaptive::tracking::research::seed_expand::expand(
        reversed,{seed(9.5,10.5),seed(-9.5,71.5)},config());
    assert(repeat.tracks.size()==result.tracks.size());
    for (std::size_t i=0;i<result.tracks.size();++i) {
        assert(repeat.tracks[i].segment_id==result.tracks[i].segment_id);
        assert(repeat.tracks[i].tracklet_id==result.tracks[i].tracklet_id);
    }
}

void validates_bounds() {
    std::vector<Candidate> candidates;
    for (unsigned t=0;t<7;++t)
        candidates.push_back(point(300U+t,t,static_cast<double>(t),5.0*t));
    bool rejected=false;
    try {
        auto bad=seed(5.0,0.0);
        bad.end_utc_ns=bad.start_utc_ns;
        (void)leo::adaptive::tracking::research::seed_expand::expand(
            candidates,{bad},config());
    } catch (const std::invalid_argument&) { rejected=true; }
    assert(rejected);
    rejected=false;
    try {
        Config bad=config();
        bad.maximum_seeds=1;
        (void)leo::adaptive::tracking::research::seed_expand::expand(
            candidates,{seed(5.0,0.0),seed(6.0,0.0)},bad);
    } catch (const std::invalid_argument&) { rejected=true; }
    assert(rejected);
}

}  // namespace

int main() {
    expands_crossing_tracks_from_all_candidates();
    validates_bounds();
}
