#include "../../../native/adaptive/tracking/tracking.cpp"

#include <cassert>
#include <iostream>
#include <random>

namespace leo::adaptive::tracking {
namespace {

std::vector<std::size_t> owning_control(
    const std::vector<std::size_t>& indexes,
    const std::vector<Point>& points,
    const std::vector<double>& residuals) {
    std::map<std::string,std::size_t> best;
    for (std::size_t index:indexes) {
        const auto& point=points[index];
        std::string key=point.source->source_group_id;
        if (key.empty())
            key="time:"+std::to_string(point.source->support_center_utc_ns);
        const auto found=best.find(key);
        if (found==best.end()) best.emplace(std::move(key),index);
        else {
            const std::size_t previous=found->second;
            if (std::make_tuple(-point.weight,std::abs(residuals[index]),
                    point.source->candidate_id)<
                std::make_tuple(-points[previous].weight,
                    std::abs(residuals[previous]),
                    points[previous].source->candidate_id))
                found->second=index;
        }
    }
    std::vector<std::size_t> result;
    for (const auto& item:best) result.push_back(item.second);
    std::sort(result.begin(),result.end(),[&](std::size_t left,
                                               std::size_t right) {
        return std::tie(points[left].time_s,
                   points[left].source->candidate_id)<
            std::tie(points[right].time_s,
                   points[right].source->candidate_id);
    });
    return result;
}

void deterministic_boundaries() {
    std::vector<Candidate> candidates(4U);
    candidates[0].candidate_id="explicit-a";
    candidates[0].source_group_id="alpha";
    candidates[0].support_center_utc_ns=1;
    candidates[1].candidate_id="explicit-collision";
    candidates[1].source_group_id="time:7";
    candidates[1].support_center_utc_ns=2;
    candidates[2].candidate_id="fallback-collision";
    candidates[2].support_center_utc_ns=7;
    candidates[3].candidate_id="fallback-b";
    candidates[3].support_center_utc_ns=8;

    std::vector<Point> points;
    points.reserve(candidates.size());
    points.push_back(Point{&candidates[0],1.0,0.0,1.0});
    points.push_back(Point{&candidates[1],2.0,0.0,1.0});
    points.push_back(Point{&candidates[2],3.0,0.0,2.0});
    points.push_back(Point{&candidates[3],4.0,0.0,1.0});
    const std::vector<double> residuals{0.0,1.0,0.0,0.0};

    const std::vector<std::size_t> duplicates{0U,0U,1U,1U,2U,2U,3U,3U};
    assert(one_per_source(duplicates,points,residuals)==
        owning_control(duplicates,points,residuals));

    // Explicit borrowed views already exist when the first fallback reserves
    // its owned storage; that fallback also collides with an explicit key.
    const std::vector<std::size_t> late_first_fallback{0U,1U,2U,3U};
    assert(one_per_source(late_first_fallback,points,residuals)==
        owning_control(late_first_fallback,points,residuals));
}

void randomized_differential() {
    std::mt19937 random(20260930U);
    for (unsigned trial=0;trial<10000U;++trial) {
        std::vector<Candidate> candidates(32U);
        std::vector<Point> points;
        std::vector<double> residuals;
        std::vector<std::size_t> indexes;
        for (std::size_t index=0;index<candidates.size();++index) {
            auto& candidate=candidates[index];
            candidate.candidate_id="candidate-"+std::to_string(index);
            candidate.support_center_utc_ns=
                static_cast<std::int64_t>(random()%9U)-4;
            switch (random()%5U) {
                case 0U: break;
                case 1U:
                    candidate.source_group_id="time:"+
                        std::to_string(candidate.support_center_utc_ns);
                    break;
                case 2U:
                    candidate.source_group_id=std::string("nul\0key",7U);
                    break;
                default:
                    candidate.source_group_id=std::string(80U,'x')+
                        std::to_string(random()%7U);
            }
            points.push_back(Point{&candidate,static_cast<double>(random()%5U),
                0.0,static_cast<double>(random()%3U)});
            residuals.push_back(static_cast<double>(
                static_cast<int>(random()%5U)-2));
            if (random()%3U) indexes.push_back(index);
        }
        std::shuffle(indexes.begin(),indexes.end(),random);
        assert(one_per_source(indexes,points,residuals)==
            owning_control(indexes,points,residuals));
    }
}

}  // namespace
}  // namespace leo::adaptive::tracking

int main() {
    leo::adaptive::tracking::deterministic_boundaries();
    leo::adaptive::tracking::randomized_differential();
    std::cout << "source key view internal tests passed\n";
}
