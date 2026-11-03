#include "../../../native/adaptive/tracking/tracking.cpp"

#include <cassert>
#include <iostream>

namespace leo::adaptive::tracking {
namespace {

void test_rejected_points_and_inclusive_time_boundaries() {
    std::vector<Candidate> candidates(7U);
    std::vector<Point> points;
    points.reserve(candidates.size());
    for (std::size_t index=0;index<candidates.size();++index) {
        candidates[index].candidate_id="candidate-"+std::to_string(index);
        candidates[index].source_group_id="source-"+std::to_string(index);
    }
    points.push_back(Point{&candidates[0],0.0,50.0,1.0});  // Before window.
    points.push_back(Point{&candidates[1],1.0,0.0,1.0});   // Start boundary.
    points.push_back(Point{&candidates[2],2.0,0.0,1.0});
    points.push_back(Point{&candidates[3],3.0,0.0,1.0});   // End boundary.
    points.push_back(Point{&candidates[4],4.0,50.0,1.0});  // After window.
    points.push_back(Point{&candidates[5],2.0,0.0,0.05});  // Underweight.
    points.push_back(Point{&candidates[6],2.0,0.0,1.0});   // Unavailable.

    std::vector<bool> available(points.size(),true);
    available[6]=false;
    Config config;
    config.residual_gate_hz=1.0;
    config.minimum_span_s=2.0;
    config.minimum_support=3U;
    config.minimum_point_weight=0.1;
    ExactFitCache cache;
    const auto segments=candidate_segments(points,available,0.0,0.0,
        config,100.0,cache);

    assert(segments.size()==1U);
    assert((segments[0].indexes==std::vector<std::size_t>{1U,2U,3U}));
    assert(segments[0].start_s==1.0);
    assert(segments[0].end_s==3.0);
}

}  // namespace
}  // namespace leo::adaptive::tracking

int main() {
    leo::adaptive::tracking::test_rejected_points_and_inclusive_time_boundaries();
    std::cout << "residual predicate internal tests passed\n";
}
