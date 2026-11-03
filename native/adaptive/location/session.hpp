#pragma once
#include "location.h"
#include <vector>

namespace leo::adaptive::location {
// Synchronous immutable borrow: snapshot, IDs, states and all track arrays must
// remain alive and unchanged until search_location returns (including workers).
struct LocationInputView {
    const leo_orbit_snapshot* orbit=nullptr;
    const leo_location_track* tracks=nullptr;
    uint32_t track_count=0;
};
struct SearchOptions {
    double latitude_deg=0, longitude_deg=0, radius_km=250;
    unsigned workers=1;
    bool full_associations=true;
};
struct SearchProgress {
    bool associations=false;
    unsigned sequence=0;
    double east_km=0, north_km=0, score_hz=0, wall_s=0;
};
using ProgressCallback=void (*)(void*,const SearchProgress&);
struct SearchOutput {
    leo_search_policy policy{};
    leo_search_result result{};
    std::vector<leo_search_evaluation> evaluations;
    leo_point_score selected_score{};
    std::vector<leo_track_score> associations;
};
// No filesystem, CLI, storage or network dependency. Progress runs on the
// calling thread. Output is replaced only on success; budget exhaustion is
// represented in result.complete/stop state, not silently called convergence.
leo_location_status search_location(LocationInputView input,const SearchOptions& options,
    SearchOutput& output,ProgressCallback progress=nullptr,void* user=nullptr);
}
