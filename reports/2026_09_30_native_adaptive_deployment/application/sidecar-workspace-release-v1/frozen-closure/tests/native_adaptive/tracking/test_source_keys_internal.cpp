#include "../../../native/adaptive/tracking/tracking.cpp"

#include <cassert>
#include <iostream>
#include <random>
#include <thread>

namespace leo::adaptive::tracking {
namespace {

std::vector<std::size_t> owning_control(
    const std::vector<std::size_t>& indexes,const std::vector<Point>& points,
    const std::vector<double>& residuals) {
    std::map<std::string,std::size_t> best;
    for (std::size_t index:indexes) {
        const Point& point=points[index];
        std::string key=point.source->source_group_id;
        if (key.empty()) key="time:"+
            std::to_string(point.source->support_center_utc_ns);
        const auto found=best.find(key);
        const auto rank=std::make_tuple(-point.weight,std::abs(residuals[index]),
            std::cref(point.source->candidate_id));
        if (found==best.end()) best.emplace(std::move(key),index);
        else {
            const std::size_t previous=found->second;
            const auto previous_rank=std::make_tuple(-points[previous].weight,
                std::abs(residuals[previous]),
                std::cref(points[previous].source->candidate_id));
            if (rank<previous_rank) found->second=index;
        }
    }
    std::vector<std::size_t> result;
    result.reserve(best.size());
    for (const auto& [key,index]:best) {
        (void)key;
        result.push_back(index);
    }
    std::sort(result.begin(),result.end(),[&](std::size_t left,
                                               std::size_t right) {
        return std::tie(points[left].time_s,points[left].source->candidate_id)<
            std::tie(points[right].time_s,points[right].source->candidate_id);
    });
    return result;
}

struct Prepared {
    std::vector<Point> points;
    std::vector<std::size_t> point_group_indexes;
    std::size_t group_count{};
};

Prepared prepare(std::vector<Candidate>& candidates,
                 const std::vector<double>& times,
                 const std::vector<double>& weights) {
    assert(candidates.size()==times.size() && times.size()==weights.size());
    std::vector<const Candidate*> pointers;
    pointers.reserve(candidates.size());
    for (Candidate& candidate:candidates) pointers.push_back(&candidate);
    const SourceGroups groups=bind_source_groups(pointers);
    Prepared result;
    result.group_count=groups.group_count;
    result.point_group_indexes=groups.point_group_indexes;
    result.points.reserve(candidates.size());
    for (std::size_t index=0;index<candidates.size();++index)
        result.points.push_back(Point{&candidates[index],times[index],0.0,
            weights[index]});
    return result;
}

void require_equal(const std::vector<std::size_t>& indexes,
                   const Prepared& prepared,
                   const std::vector<double>& residuals,
                   SourceWorkspace& workspace) {
    const auto expected=owning_control(indexes,prepared.points,residuals);
    const auto& actual=one_per_source(indexes,prepared.points,residuals,workspace);
    assert(actual==expected);
    assert(std::all_of(workspace.best_indexes.begin(),workspace.best_indexes.end(),
        [](std::size_t index) {
            return index==std::numeric_limits<std::size_t>::max();
        }));
}

void deterministic_boundaries() {
    std::vector<Candidate> candidates(7U);
    for (std::size_t index=0;index<candidates.size();++index)
        candidates[index].candidate_id="candidate-"+std::to_string(index);
    candidates[0].source_group_id="alpha";
    candidates[1].source_group_id="time:7";
    candidates[2].support_center_utc_ns=7; // Fallback/explicit collision.
    candidates[3].support_center_utc_ns=8;
    candidates[4].source_group_id=std::string("nul\0key",7U);
    candidates[5].source_group_id=std::string(80U,'x');
    candidates[6].source_group_id="alpha";
    const std::vector<double> times{5,4,3,2,1,0,5};
    const std::vector<double> weights{1,1,2,1,1,1,1};
    const std::vector<double> residuals{0,1,0,0,0,0,-1};
    const Prepared prepared=prepare(candidates,times,weights);
    assert(prepared.point_group_indexes[1]==prepared.point_group_indexes[2]);
    assert(prepared.point_group_indexes[0]==prepared.point_group_indexes[6]);
    SourceWorkspace workspace(prepared.point_group_indexes,prepared.group_count);
    const std::vector<std::size_t> all{0,0,1,1,2,2,3,4,5,6};
    const std::vector<std::size_t> subset{6,4,2};
    const std::vector<std::size_t> disjoint{0,3,5};
    require_equal(all,prepared,residuals,workspace);
    require_equal({},prepared,residuals,workspace);
    require_equal(subset,prepared,residuals,workspace);
    require_equal(disjoint,prepared,residuals,workspace);
    require_equal(all,prepared,residuals,workspace);

    // split_contiguous owns its result before the shared workspace is reused.
    const auto owned=split_contiguous(
        one_per_source(all,prepared.points,residuals,workspace),
        prepared.points,100.0);
    const auto saved=owned;
    (void)one_per_source(subset,prepared.points,residuals,workspace);
    assert(owned==saved);
}

void randomized_differential() {
    std::mt19937 random(20260930U);
    for (unsigned trial=0;trial<10000U;++trial) {
        std::vector<Candidate> candidates(32U);
        std::vector<double> times,weights,residuals;
        std::vector<std::size_t> indexes;
        for (std::size_t index=0;index<candidates.size();++index) {
            Candidate& candidate=candidates[index];
            candidate.candidate_id="candidate-"+std::to_string(index);
            candidate.support_center_utc_ns=
                static_cast<std::int64_t>(random()%9U)-4;
            switch (random()%5U) {
                case 0U: break;
                case 1U: candidate.source_group_id="time:"+
                    std::to_string(candidate.support_center_utc_ns);break;
                case 2U: candidate.source_group_id=std::string("nul\0key",7U);break;
                default: candidate.source_group_id=std::string(80U,'x')+
                    std::to_string(random()%7U);break;
            }
            times.push_back(static_cast<double>(random()%5U));
            weights.push_back(static_cast<double>(random()%3U));
            residuals.push_back(static_cast<double>(
                static_cast<int>(random()%5U)-2));
            if (random()%3U) indexes.push_back(index);
        }
        std::shuffle(indexes.begin(),indexes.end(),random);
        const Prepared prepared=prepare(candidates,times,weights);
        SourceWorkspace workspace(prepared.point_group_indexes,
                                  prepared.group_count);
        require_equal(indexes,prepared,residuals,workspace);
        std::reverse(indexes.begin(),indexes.end());
        require_equal(indexes,prepared,residuals,workspace);
    }
}

void independent_lane(unsigned seed) {
    std::mt19937 random(seed);
    std::vector<Candidate> candidates(128U);
    std::vector<double> times,weights,residuals;
    std::vector<std::size_t> indexes;
    for (std::size_t index=0;index<candidates.size();++index) {
        Candidate& candidate=candidates[index];
        candidate.candidate_id="lane-"+std::to_string(seed)+"-"+
            std::to_string(index);
        candidate.source_group_id="group-"+std::to_string(index%17U);
        times.push_back(static_cast<double>(index));
        weights.push_back(static_cast<double>(1U+index%3U));
        residuals.push_back(static_cast<double>(static_cast<int>(index%5U)-2));
        indexes.push_back(index);
    }
    const Prepared prepared=prepare(candidates,times,weights);
    SourceWorkspace workspace(prepared.point_group_indexes,prepared.group_count);
    for (unsigned repetition=0;repetition<1000U;++repetition) {
        std::shuffle(indexes.begin(),indexes.end(),random);
        require_equal(indexes,prepared,residuals,workspace);
    }
}

void lane_isolation() {
    std::thread first(independent_lane,1U);
    std::thread second(independent_lane,2U);
    first.join();
    second.join();
}

}  // namespace
}  // namespace leo::adaptive::tracking

int main() {
    static_assert(sizeof(leo::adaptive::tracking::Point)==32U);
    leo::adaptive::tracking::deterministic_boundaries();
    leo::adaptive::tracking::randomized_differential();
    leo::adaptive::tracking::lane_isolation();
    std::cout << "dense source workspace internal tests passed\n";
}
