#pragma once
#include "projection.hpp"
// The caller's build must select the same detector header as its linked archive.
extern "C" {
#include "native_glrt.h"
}
#include <array>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace leo::adaptive {
struct RankedObservation {
    uint32_t candidate_rank;
    Observation observation;
};

// Narrow port for a complete dual-RX, one-probe, integer-epoch result. Source
// authority is supplied by acquisition; neither storage nor TLE enters here.
// All output is owned. A rejected result cannot expose a partially built vector.
inline std::vector<RankedObservation> project_integer_detector_result(
    const ProjectionSource& authority,const leo_native_glrt_result& result) {
    if(authority.probe_ms!=20||authority.probe_index!=0||authority.rate!=2500000||
       authority.window_counter<authority.anchor_counter||result.row_count!=2)
        throw std::invalid_argument("unsupported integer detector geometry");
    // Source validation must also run for a valid empty detection.
    (void)classify_projection_input(authority,FractionalCandidate{});
    std::array<const leo_native_glrt_row*,2> rows{};
    for(size_t i=0;i<result.row_count;++i){const auto& row=result.rows[i];
        if(row.receiver_id<0||row.receiver_id>1||rows[row.receiver_id]||row.probe_index!=0||row.probe_start_ms!=0||
           row.candidate_count<0||row.candidate_count>LEO_NATIVE_GLRT_MAX_CANDIDATES)
            throw std::invalid_argument("invalid detector receiver/probe inventory");
        rows[row.receiver_id]=&row;
    }
    std::vector<RankedObservation> output;output.reserve(16);
    ProjectionBatch projection;
    for(uint32_t rx=0;rx<2;++rx){
        auto source=authority;source.receiver=rx;
        for(int rank=0;rank<rows[rx]->candidate_count;++rank){
            const auto& raw=rows[rx]->candidates[rank];
            if(!std::isfinite(raw.margin)||!std::isfinite(raw.tracking_cfo_hz)||
               !std::isfinite(raw.exact_score)||!std::isfinite(raw.control_score)||
               (raw.margin>=.025&&raw.glrt_complete!=1))
                throw std::invalid_argument("invalid integer detector evidence");
            FractionalCandidate candidate{static_cast<uint32_t>(rank),raw.epoch,0.0,
                raw.tracking_cfo_hz,raw.exact_score,raw.control_score,raw.margin,raw.glrt_complete==1};
            Observation observation;
            if(projection.project(source,candidate,observation))
                output.push_back({static_cast<uint32_t>(rank),std::move(observation)});
        }
    }
    return output;
}
}
