// Compile against the frozen control and research objects, then compare stdout.
#include "tracking.hpp"
#include <iomanip>
#include <iostream>
#include <sstream>
using namespace leo::adaptive::tracking;
static std::string identity(unsigned n) {
    std::ostringstream out;
    out << "sha256:" << std::hex << std::setfill('0') << std::setw(64) << n;
    return out.str();
}
int main() {
    std::cout << std::hexfloat;
    for(unsigned weighted=0;weighted<2;++weighted) {
        std::vector<Candidate> rows;
        for(unsigned time=0;time<8;++time) for(unsigned lane=0;lane<2;++lane) {
            const auto id=time*2+lane+1;
            const std::int64_t center=1800000000000000000LL+time*1000000000LL;
            const double weight=weighted ? .25*(id%5+1) : 1.0;
            rows.push_back({identity(id),identity(id+100),0,1,"upper",11.2e9,
                center-1000000,center,center+1000000,1000.0+lane*30000.0,
                weight+.1,.1,weight});
        }
        for(std::size_t bins:{1U,8U,32U}) for(std::size_t count:{1U,4U,16U,64U,1000U}) {
            Config config;
            config.minimum_slope_hz_per_s=-1;config.maximum_slope_hz_per_s=1;
            config.slope_bins=3;config.intercept_bins=bins;config.peak_candidates=count;
            config.alias_spacing_hz=100000;config.residual_gate_hz=20000;
            config.maximum_tracks_per_lane=2;
            const auto result=reconstruct(rows,config);
            std::cout << weighted << ' ' << bins << ' ' << count << ' '
                      << result.input_candidate_count << ' ' << result.used_candidate_count
                      << ' ' << result.tracks.size() << '\n';
            for(const auto& track:result.tracks) {
                std::cout << track.segment_id << ' ' << track.tracklet_id << ' '
                          << track.start_utc_ns << ' ' << track.end_utc_ns << ' '
                          << track.reference_utc_ns << ' ' << track.normalized_rate_hz_per_s
                          << ' ' << track.normalized_intercept_hz << ' '
                          << track.residual_rms_hz << ' ' << track.residual_max_hz << ' '
                          << track.weighted_support << '\n';
                for(const auto& point:track.points)
                    std::cout << point.candidate_id << ' ' << point.source_group_id << ' '
                              << point.relative_alias_index << ' ' << point.normalized_raw_cfo_hz
                              << ' ' << point.normalized_dealiased_cfo_hz << '\n';
            }
        }
    }
}
