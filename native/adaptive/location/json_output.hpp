#pragma once
#include "session.hpp"
#include <cstdio>
#include <cmath>

namespace leo::adaptive::location::json {
inline void write_track_point(FILE *output, const leo_point_score &point,
                       const std::vector<leo_track_score> &tracks) {
    std::fprintf(output,"{\"score_hz\":%.17g,\"matched_tracks\":%u,\"tracks\":[",
                 point.residual_rmse_hz,point.matched_track_count);
    for(size_t i=0;i<tracks.size();++i) {
        const auto& s=tracks[i];
        std::fprintf(output,"%s{\"candidate_id\":%d,\"tau_s\":%d,\"held_hz\":%.17g,"
                     "\"fit_hz\":%.17g,\"offset_hz\":%.17g}",i?",":"",
                     s.candidate_id,s.tau_s,s.heldout_rms_hz,s.training_rms_hz,s.frequency_offset_hz);
    }
    std::fprintf(output,"]}");
}

inline bool write_search(FILE* output,const SearchOutput& completed) {
    const auto& result=completed.result;
    const auto& policy=completed.policy;
    const auto& inventory=completed.evaluations;
    std::fprintf(output,
        "{\"schema\":\"org.leo.native-adaptive-location-search/v2\","
        "\"evaluated_points\":%u,\"budget_points\":%u,\"deferred_cells\":%u,"
        "\"complete\":%s,\"stop_reason\":\"%s\",\"selected\":{\"east_km\":%.17g,"
        "\"north_km\":%.17g,\"score_hz\":%.17g},\"evaluations\":[",
        result.evaluated_points,
        policy.budget_points,
        result.deferred_cells,
        result.complete ? "true" : "false",
        result.complete ? "frontier-exhausted" : "point-budget-reached",
        result.incumbent.east_km,
        result.incumbent.north_km,
        std::sqrt(result.incumbent.weighted_mse_hz2));
    for (size_t index = 0; index < inventory.size(); ++index) {
        std::fprintf(output,
            "%s[%.17g,%.17g,%.17g]",
            index == 0 ? "" : ",",
            inventory[index].east_km,
            inventory[index].north_km,
            std::sqrt(inventory[index].weighted_mse_hz2));
    }
    std::fprintf(output,"]}\n");
    return std::fflush(output)==0 && !std::ferror(output);
}
inline bool write_associations(FILE* output,const SearchOutput& completed) {
    std::fprintf(output,"{\"points\":[");
    write_track_point(output,completed.selected_score,completed.associations);
    std::fprintf(output,"]}\n");
    return std::fflush(output)==0 && !std::ferror(output);
}
}

