#include "source/tracking.cpp"
#include <cassert>
#include <iostream>
#include <random>

namespace leo::adaptive::tracking {
namespace {
std::vector<std::size_t> control(const std::vector<std::size_t>& indexes,
    const std::vector<Point>& points, const std::vector<double>& residuals) {
    std::map<std::string, std::size_t> best;
    for (auto index : indexes) {
        const auto& p = points[index];
        std::string key = p.source->source_group_id;
        if (key.empty()) key = "time:" + std::to_string(p.source->support_center_utc_ns);
        auto found = best.find(key);
        if (found == best.end()) best.emplace(std::move(key), index);
        else {
            const auto previous = found->second;
            if (std::make_tuple(-p.weight, std::abs(residuals[index]),
                    p.source->candidate_id) <
                std::make_tuple(-points[previous].weight, std::abs(residuals[previous]),
                    points[previous].source->candidate_id)) found->second = index;
        }
    }
    std::vector<std::size_t> result;
    for (const auto& item : best) result.push_back(item.second);
    std::sort(result.begin(), result.end(), [&](auto a, auto b) {
        return std::tie(points[a].time_s, points[a].source->candidate_id) <
            std::tie(points[b].time_s, points[b].source->candidate_id);
    });
    return result;
}
void verify_deterministic_boundaries() {
    std::vector<Candidate> candidates(4);
    candidates[0].candidate_id = "explicit-a";
    candidates[0].source_group_id = "alpha";
    candidates[0].support_center_utc_ns = 1;
    candidates[1].candidate_id = "explicit-collision";
    candidates[1].source_group_id = "time:7";
    candidates[1].support_center_utc_ns = 2;
    candidates[2].candidate_id = "fallback-collision";
    candidates[2].support_center_utc_ns = 7;
    candidates[3].candidate_id = "fallback-b";
    candidates[3].support_center_utc_ns = 8;

    std::vector<Point> points;
    points.reserve(candidates.size());
    points.push_back(Point{&candidates[0],1.0,0.0,1.0});
    points.push_back(Point{&candidates[1],2.0,0.0,1.0});
    points.push_back(Point{&candidates[2],3.0,0.0,2.0});
    points.push_back(Point{&candidates[3],4.0,0.0,1.0});
    const std::vector<double> residuals{0.0,1.0,0.0,0.0};

    // Duplicate indexes must not change grouping or rank selection.
    const std::vector<std::size_t> duplicates{0,0,1,1,2,2,3,3};
    assert(one_per_source(duplicates,points,residuals) ==
        control(duplicates,points,residuals));

    // Explicit borrowed views are already retained when the first fallback
    // forces the owned fallback-vector reservation.  The fallback also
    // collides intentionally with an earlier explicit "time:" key.
    const std::vector<std::size_t> late_first_fallback{0,1,2,3};
    assert(one_per_source(late_first_fallback,points,residuals) ==
        control(late_first_fallback,points,residuals));
}
void verify() {
    verify_deterministic_boundaries();
    std::mt19937 random(20260930);
    for (unsigned trial = 0; trial < 10000; ++trial) {
        std::vector<Candidate> candidates(32);
        std::vector<Point> points;
        std::vector<double> residuals;
        std::vector<std::size_t> indexes;
        for (std::size_t i = 0; i < candidates.size(); ++i) {
            auto& c = candidates[i];
            c.candidate_id = "candidate-" + std::to_string(i);
            c.support_center_utc_ns = static_cast<std::int64_t>(random()%9)-4;
            switch (random()%5) {
                case 0: break;
                case 1: c.source_group_id = "time:" + std::to_string(c.support_center_utc_ns); break;
                case 2: c.source_group_id = std::string("nul\0key",7); break;
                default: c.source_group_id = std::string(80,'x') + std::to_string(random()%7);
            }
            points.push_back(Point{&c, double(random()%5), 0.0, double(random()%3)});
            residuals.push_back(double(int(random()%5)-2));
            if (random()%3) indexes.push_back(i);
        }
        std::shuffle(indexes.begin(), indexes.end(), random);
        assert(one_per_source(indexes,points,residuals) == control(indexes,points,residuals));
    }
}
}
}
int main() {
    leo::adaptive::tracking::verify();
    std::cout << "source-key view: deterministic boundaries and 10000 differential cases pass\n";
}
