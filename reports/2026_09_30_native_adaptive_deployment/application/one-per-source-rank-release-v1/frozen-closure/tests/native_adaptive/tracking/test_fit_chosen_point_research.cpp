#include "../../../reports/2026_09_30_native_adaptive_deployment/tracking/research/tracking_fit_chosen_point.cpp"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <vector>

namespace {

using leo::adaptive::tracking::Candidate;
using leo::adaptive::tracking::Config;
using leo::adaptive::tracking::Result;
using leo::adaptive::tracking::Track;

void require(bool condition,const char* message) {
    if (!condition) throw std::runtime_error(message);
}

std::string identity(int value) {
    std::ostringstream out;
    out << "sha256:" << std::hex << std::setfill('0') << std::setw(64)
        << value;
    return out.str();
}

bool same_double(double left,double right) {
    std::uint64_t left_bits=0,right_bits=0;
    std::memcpy(&left_bits,&left,sizeof(left));
    std::memcpy(&right_bits,&right,sizeof(right));
    return left_bits==right_bits;
}

bool same_result(const Result& left,const Result& right) {
    if (left.input_candidate_count!=right.input_candidate_count ||
        left.used_candidate_count!=right.used_candidate_count ||
        left.config_digest!=right.config_digest ||
        left.tracks.size()!=right.tracks.size()) return false;
    for (std::size_t ti=0;ti<left.tracks.size();++ti) {
        const Track& a=left.tracks[ti];
        const Track& b=right.tracks[ti];
        if (a.segment_id!=b.segment_id || a.tracklet_id!=b.tracklet_id ||
            a.lane.channel!=b.lane.channel || a.lane.edge!=b.lane.edge ||
            a.lane.receiver_id!=b.lane.receiver_id ||
            !same_double(a.lane.actual_rf_hz,b.lane.actual_rf_hz) ||
            a.start_utc_ns!=b.start_utc_ns || a.end_utc_ns!=b.end_utc_ns ||
            a.reference_utc_ns!=b.reference_utc_ns ||
            !same_double(a.normalized_rate_hz_per_s,
                b.normalized_rate_hz_per_s) ||
            !same_double(a.normalized_intercept_hz,
                b.normalized_intercept_hz) ||
            !same_double(a.residual_rms_hz,b.residual_rms_hz) ||
            !same_double(a.residual_max_hz,b.residual_max_hz) ||
            !same_double(a.weighted_support,b.weighted_support) ||
            a.points.size()!=b.points.size()) return false;
        for (std::size_t pi=0;pi<a.points.size();++pi) {
            const auto& x=a.points[pi];
            const auto& y=b.points[pi];
            if (x.candidate_id!=y.candidate_id ||
                x.source_group_id!=y.source_group_id ||
                x.relative_alias_index!=y.relative_alias_index ||
                !same_double(x.normalized_raw_cfo_hz,
                    y.normalized_raw_cfo_hz) ||
                !same_double(x.normalized_dealiased_cfo_hz,
                    y.normalized_dealiased_cfo_hz)) return false;
        }
    }
    return true;
}

Config fixture_config() {
    Config config;
    config.alias_spacing_hz=100'000.0;
    config.minimum_slope_hz_per_s=-1.0;
    config.maximum_slope_hz_per_s=1.0;
    config.residual_gate_hz=100.0;
    config.maximum_gap_s=1.1;
    config.minimum_span_s=3.0;
    config.minimum_support=4U;
    config.minimum_point_weight=0.1;
    config.slope_bins=3U;
    config.intercept_bins=100U;
    config.peak_candidates=12U;
    config.maximum_tracks_per_lane=2U;
    config.maximum_trajectory_hypotheses=16U;
    return config;
}

std::vector<Candidate> fixture() {
    constexpr std::int64_t base=1'800'000'000'000'000'000LL;
    const double weights[2][5]={{1.0,2.0,3.0,4.0,5.0},
                                {0.5,0.75,1.25,1.5,1.75}};
    std::vector<Candidate> rows;
    for (int time=0;time<5;++time) {
        for (int line=0;line<2;++line) {
            const int ordinal=time*2+line;
            const std::int64_t center=base+
                static_cast<std::int64_t>(time)*1'000'000'000LL+
                static_cast<std::int64_t>(line)*1'000'000LL;
            const double weight=weights[line][time];
            rows.push_back(Candidate{
                identity(ordinal+1),identity(ordinal+101),0,1,"lower",
                11'200'000'000.0,center-20'000'000LL,center,
                center+20'000'000LL,line==0?10'500.0:50'500.0,
                1.0+weight,1.0,weight,
            });
        }
    }
    return rows;
}

std::vector<std::string> membership(const Track& track) {
    std::vector<std::string> ids;
    for (const auto& point:track.points) ids.push_back(point.candidate_id);
    return ids;
}

void test_unequal_weights_multiple_peels_direct_and_stateful() {
    const Config config=fixture_config();
    const std::vector<Candidate> rows=fixture();
    const Result direct=leo::adaptive::tracking::reconstruct(rows,config);
    require(direct.tracks.size()==2U,"fixture did not exercise two peels");
    require(direct.used_candidate_count==10U,
        "two peels did not consume every fixture point");

    const std::vector<std::string> first_expected{
        identity(1),identity(3),identity(5),identity(7),identity(9)};
    const std::vector<std::string> second_expected{
        identity(2),identity(4),identity(6),identity(8),identity(10)};
    bool first_seen=false,second_seen=false;
    for (const Track& track:direct.tracks) {
        const auto ids=membership(track);
        if (ids==first_expected) {
            first_seen=true;
            require(same_double(track.weighted_support,15.0),
                "first line lost its unequal weights");
        } else if (ids==second_expected) {
            second_seen=true;
            require(same_double(track.weighted_support,5.75),
                "second line lost its unequal weights");
        }
    }
    require(first_seen && second_seen,
        "peel membership does not preserve index/weight pairing");

    leo::adaptive::tracking::Reconstructor stateful;
    std::vector<Candidate> prefix(rows.begin(),rows.begin()+8);
    require(same_result(stateful.reconstruct(prefix,config),
        leo::adaptive::tracking::reconstruct(prefix,config)),
        "stateful cold prefix differs from direct reconstruction");
    require(stateful.stats().last_cold_fallback,
        "stateful fixture did not establish a cold cache");

    const Result extended=stateful.reconstruct(rows,config);
    require(!stateful.stats().last_cold_fallback &&
        stateful.stats().last_extended_lanes==1U,
        "stateful fixture did not exercise persistent bin extension");
    require(same_result(extended,direct),
        "persistent-bin unequal-weight result differs from direct result");
}

}  // namespace

int main() {
    try {
        test_unequal_weights_multiple_peels_direct_and_stateful();
        std::cout << "chosen-point research tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
