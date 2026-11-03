#include "curvature_tracks.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

using leo::adaptive::tracking::Candidate;
using leo::adaptive::tracking::research::curvature_tracks::Config;
using Result=leo::adaptive::tracking::research::curvature_tracks::Result;

std::string digest(unsigned value) {
    constexpr char hex[]="0123456789abcdef";
    std::string result="sha256:"+std::string(64,'0');
    for(unsigned i=0;i<8;++i) {
        result[result.size()-1-i]=hex[value&15U];
        value>>=4U;
    }
    return result;
}

double wrap(double value,double spacing) {
    return value-std::nearbyint(value/spacing)*spacing;
}

Candidate point(unsigned id,unsigned source,double time_s,double frequency,
                double spacing=100.0,int receiver=0) {
    constexpr std::int64_t origin=1'700'000'000'000'000'000LL;
    const auto center=origin+static_cast<std::int64_t>(time_s*1e9);
    return {digest(id),digest(10'000U+source),receiver,3,"lower",1'000.0,
        center-100,center,center+100,wrap(frequency,spacing),1.0,0.1,0.9};
}

Config config() {
    Config value;
    value.canonical_rf_hz=1'000.0;
    value.alias_spacing_hz=100.0;
    value.minimum_rate_hz_per_s=-50.0;
    value.maximum_rate_hz_per_s=50.0;
    value.maximum_acceleration_hz_per_s2=10.0;
    value.residual_gate_hz=5.0;
    value.measurement_uncertainty_hz=.5;
    value.maximum_gap_s=2.1;
    value.minimum_span_s=7.0;
    value.minimum_support=8;
    value.state_window=32;
    value.state_window_s=12.0;
    value.maximum_seeds_per_lane=128;
    value.maximum_hypotheses_per_lane=8;
    return value;
}

bool contains(const Result& result,const std::vector<std::string>& ids,std::size_t required) {
    for(const auto& track:result.tracks) {
        std::size_t matches=0;
        for(const auto& point:track.compatibility_linear_summary.points)
            matches+=std::find(ids.begin(),ids.end(),point.candidate_id)!=ids.end();
        if(matches>=required) return true;
    }
    return false;
}

void curved_alias_noise_and_miss() {
    std::vector<Candidate> candidates;
    std::vector<std::string> truth;
    for(unsigned t=0;t<12;++t) {
        if(t==5) continue;
        const double noise=(t%3==0 ? .3:(t%3==1 ? -.2:.1));
        candidates.push_back(point(100U+t,t,static_cast<double>(t),
            15.0+6.0*t+1.5*t*t+noise));
        truth.push_back(digest(100U+t));
        candidates.push_back(point(500U+t,t,static_cast<double>(t),-35.0+2.0*t));
    }
    const auto result=leo::adaptive::tracking::research::curvature_tracks::reconstruct(
        candidates,config());
    assert(contains(result,truth,8));
    for(const auto& track:result.tracks)
        for(std::size_t i=1;i<track.compatibility_linear_summary.points.size();++i)
            assert(std::abs(track.compatibility_linear_summary.points[i].
                normalized_dealiased_cfo_hz-
                track.compatibility_linear_summary.points[i-1].
                normalized_dealiased_cfo_hz)<100.0);
}

void preserves_short_crossing_ambiguity() {
    std::vector<Candidate> candidates;
    std::vector<std::string> rising,falling;
    for(unsigned t=0;t<11;++t) {
        const double time=static_cast<double>(t);
        candidates.push_back(point(1'000U+t,t,time,-30.0+8.0*time+.5*time*time));
        candidates.push_back(point(2'000U+t,t,time,65.0-7.0*time-.25*time*time));
        rising.push_back(digest(1'000U+t));
        falling.push_back(digest(2'000U+t));
    }
    const auto result=leo::adaptive::tracking::research::curvature_tracks::reconstruct(
        candidates,config());
    assert(contains(result,rising,9));
    assert(contains(result,falling,9));
}

void linear_ablation_and_validation() {
    std::vector<Candidate> candidates;
    std::vector<std::string> truth;
    for(unsigned t=0;t<10;++t) {
        candidates.push_back(point(3'000U+t,t,static_cast<double>(t),5.0+4.0*t));
        truth.push_back(digest(3'000U+t));
    }
    Config linear=config();
    linear.maximum_acceleration_hz_per_s2=0.0;
    const auto result=leo::adaptive::tracking::research::curvature_tracks::reconstruct(
        candidates,linear);
    assert(contains(result,truth,10));
    bool rejected=false;
    try {
        Config bad=linear;bad.ambiguity_beam=0;
        (void)leo::adaptive::tracking::research::curvature_tracks::reconstruct(candidates,bad);
    } catch(const std::invalid_argument&) { rejected=true; }
    assert(rejected);
}

void refuses_to_bridge_an_unattested_gap() {
    std::vector<Candidate> candidates;
    for(unsigned t=0;t<4;++t)
        candidates.push_back(point(4'000U+t,t,static_cast<double>(t),3.0*t));
    for(unsigned t=0;t<4;++t)
        candidates.push_back(point(4'100U+t,10U+t,10.0+static_cast<double>(t),
            30.0+3.0*t));
    Config value=config();
    value.minimum_support=6;
    value.minimum_span_s=5.0;
    const auto result=leo::adaptive::tracking::research::curvature_tracks::reconstruct(
        candidates,value);
    assert(result.tracks.empty());
}

void bounded_fit_does_not_run_away_on_excess_curvature() {
    std::vector<Candidate> candidates;
    std::vector<std::string> truth;
    for(unsigned t=0;t<12;++t) {
        candidates.push_back(point(5'000U+t,t,static_cast<double>(t),20.0*t*t,1'000.0));
        truth.push_back(digest(5'000U+t));
    }
    Config value=config();
    value.alias_spacing_hz=1'000.0;
    const auto result=leo::adaptive::tracking::research::curvature_tracks::reconstruct(
        candidates,value);
    assert(!contains(result,truth,8));
}

void permits_bounded_time_offsets_within_one_source() {
    std::vector<Candidate> candidates;
    std::vector<std::string> truth;
    for(unsigned t=0;t<10;++t) {
        candidates.push_back(point(6'000U+t,t,static_cast<double>(t),4.0*t));
        truth.push_back(digest(6'000U+t));
        if(t==3) {
            Candidate alternate=point(6'100U+t,t,static_cast<double>(t),30.0);
            alternate.support_start_utc_ns+=1'000'000;
            alternate.support_center_utc_ns+=1'000'000;
            alternate.support_end_utc_ns+=1'000'000;
            candidates.push_back(std::move(alternate));
        }
    }
    const auto result=leo::adaptive::tracking::research::curvature_tracks::reconstruct(
        candidates,config());
    assert(contains(result,truth,9));
}

}  // namespace

int main() {
    curved_alias_noise_and_miss();
    preserves_short_crossing_ambiguity();
    linear_ablation_and_validation();
    refuses_to_bridge_an_unattested_gap();
    bounded_fit_does_not_run_away_on_excess_curvature();
    permits_bounded_time_offsets_within_one_source();
}
