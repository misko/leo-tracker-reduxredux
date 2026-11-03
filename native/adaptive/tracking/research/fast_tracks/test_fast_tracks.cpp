#include "fast_tracks.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using leo::adaptive::tracking::Candidate;
namespace fast=leo::adaptive::tracking::research::fast_tracks;

void require(bool condition,const char* message) {
    if(!condition) throw std::runtime_error(message);
}

std::string id(unsigned value) {
    std::ostringstream output;
    output<<"sha256:"<<std::hex<<std::setfill('0')<<std::setw(64)<<value;
    return output.str();
}

Candidate point(unsigned identity,unsigned source,int visit,double slope,double intercept,
                int alias,int receiver=0,int channel=1,double rf=11'200'000'000.0) {
    constexpr std::int64_t base=1'800'000'000'000'000'000LL;
    constexpr double spacing=1.0/4.4e-6;
    const auto center=base+static_cast<std::int64_t>(visit)*600'000'000LL;
    const double time=.6*visit;
    return {id(identity),id(source),receiver,channel,"lower",rf,
        center-10'000'000LL,center,center+10'000'000LL,
        slope*time+intercept+alias*spacing,1.25,.25,1.0};
}

std::vector<Candidate> one_track() {
    std::vector<Candidate> rows;
    for(int visit=0;visit<10;++visit)
        rows.push_back(point(visit+1,visit+101,visit,1250,31000,visit%3-1));
    return rows;
}

std::vector<std::string> memberships(const fast::Result& result) {
    std::vector<std::string> output;
    for(const auto& track:result.tracks) {
        std::string value;
        for(const auto& point:track.points) value+=point.candidate_id;
        output.push_back(std::move(value));
    }
    std::sort(output.begin(),output.end());
    return output;
}

void alias_continuity_and_permutation() {
    auto rows=one_track();
    const auto result=fast::reconstruct(rows);
    require(result.tracks.size()==1,"one track was not recovered");
    require(result.tracks[0].points.size()==10,"track support differs");
    require(std::abs(result.tracks[0].normalized_rate_hz_per_s-1250)<1e-7,
        "track slope differs");
    require(result.stats.maximum_live_beam<=fast::Config{}.beam_width,
        "beam bound exceeded");
    const auto expected=memberships(result);
    std::reverse(rows.begin(),rows.end());
    require(memberships(fast::reconstruct(rows))==expected,
        "result depends on input order");
}

void exact_duplicates_do_not_consume_the_beam() {
    auto rows=one_track();
    std::vector<Candidate> duplicates;
    for(const Candidate& row:rows) {
        duplicates.push_back(row);
        Candidate copy=row;
        copy.candidate_id=id(static_cast<unsigned>(duplicates.size())+5000);
        duplicates.push_back(std::move(copy));
    }
    const auto result=fast::reconstruct(duplicates);
    require(result.tracks.size()==1 && result.tracks[0].points.size()==10,
        "exact duplicates changed recovery");
    require(result.stats.exact_duplicates_consolidated==10,
        "exact duplicate consolidation count differs");
}

void multiple_tracks_and_source_choice() {
    std::vector<Candidate> rows;
    for(int visit=0;visit<10;++visit) {
        rows.push_back(point(visit+1,visit+101,visit,900,22000,visit%2));
        rows.push_back(point(visit+1001,visit+101,visit,-1100,91000,visit%2-1));
        Candidate weak=rows.back();
        weak.candidate_id=id(visit+2001);weak.measured_cfo_hz+=200;
        weak.exact_score=.251;weak.control_score=.25;weak.margin=.001;
        rows.push_back(std::move(weak));
    }
    const auto result=fast::reconstruct(rows);
    require(result.tracks.size()==2,"two lane trajectories were not peeled");
    require(result.tracks[0].points.size()==10 && result.tracks[1].points.size()==10,
        "peeled support differs");
}

void lanes_and_gaps_do_not_join() {
    auto rows=one_track();
    for(std::size_t index=0;index<rows.size();++index) rows[index].receiver_id=index%2;
    require(fast::reconstruct(rows).tracks.empty(),"receiver lanes were merged");
    rows=one_track();
    for(std::size_t index=5;index<rows.size();++index) {
        rows[index].support_start_utc_ns+=10'000'000'000LL;
        rows[index].support_center_utc_ns+=10'000'000'000LL;
        rows[index].support_end_utc_ns+=10'000'000'000LL;
    }
    require(fast::reconstruct(rows).tracks.empty(),"disjoint short episodes were joined");
}

void invalid_and_bounded() {
    auto rows=one_track();
    rows[1].candidate_id=rows[0].candidate_id;
    bool rejected=false;
    try { (void)fast::reconstruct(rows); }
    catch(const std::invalid_argument&) { rejected=true; }
    require(rejected,"duplicate identity accepted");
    rows=one_track();
    fast::Config tiny;tiny.maximum_nodes_per_peel=4;
    rejected=false;
    try { (void)fast::reconstruct(rows,tiny); }
    catch(const std::length_error&) { rejected=true; }
    require(rejected,"node work bound ignored");
}
}

int main() {
    alias_continuity_and_permutation();
    exact_duplicates_do_not_consume_the_beam();
    multiple_tracks_and_source_choice();
    lanes_and_gaps_do_not_join();
    invalid_and_bounded();
}
