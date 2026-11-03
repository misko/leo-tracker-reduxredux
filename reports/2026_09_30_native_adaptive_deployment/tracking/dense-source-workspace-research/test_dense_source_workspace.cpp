#include "source/candidate.cpp"

#include <cassert>
#include <iostream>
#include <random>
#include <thread>

namespace leo::adaptive::tracking {
namespace {

std::vector<std::size_t> control(const std::vector<std::size_t>& indexes,
    const std::vector<Point>& points,const std::vector<double>& residuals) {
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
    std::sort(result.begin(),result.end(),[&](std::size_t a,std::size_t b) {
        return std::tie(points[a].time_s,points[a].source->candidate_id)<
            std::tie(points[b].time_s,points[b].source->candidate_id);
    });
    return result;
}

struct Prepared {
    std::vector<Point> points;
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
    result.points.reserve(candidates.size());
    for (std::size_t index=0;index<candidates.size();++index)
        result.points.push_back(Point{&candidates[index],times[index],0.0,
            weights[index],groups.point_group_indexes[index]});
    return result;
}

void require_equal(const std::vector<std::size_t>& indexes,
                   const Prepared& prepared,
                   const std::vector<double>& residuals,
                   SourceWorkspace& workspace) {
    const auto expected=control(indexes,prepared.points,residuals);
    const auto& actual=one_per_source(indexes,prepared.points,residuals,workspace);
    assert(actual==expected);
    assert(std::all_of(workspace.best_indexes.begin(),workspace.best_indexes.end(),
        [](std::size_t index) {
            return index==std::numeric_limits<std::size_t>::max();
        }));
}

void deterministic_boundaries() {
    std::vector<Candidate> candidates(7);
    for (std::size_t index=0;index<candidates.size();++index)
        candidates[index].candidate_id="candidate-"+std::to_string(index);
    candidates[0].source_group_id="alpha";
    candidates[1].source_group_id="time:7";
    candidates[2].support_center_utc_ns=7; // Deliberate fallback/explicit collision.
    candidates[3].support_center_utc_ns=8;
    candidates[4].source_group_id=std::string("nul\0key",7);
    candidates[5].source_group_id=std::string(80,'x');
    candidates[6].source_group_id="alpha";
    const std::vector<double> times{5,4,3,2,1,0,5};
    const std::vector<double> weights{1,1,2,1,1,1,1};
    const std::vector<double> residuals{0,1,0,0,0,0,-1};
    const Prepared prepared=prepare(candidates,times,weights);
    assert(prepared.points[1].source_group_index==
        prepared.points[2].source_group_index);
    assert(prepared.points[0].source_group_index==
        prepared.points[6].source_group_index);
    SourceWorkspace workspace(prepared.group_count);
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
        one_per_source(all,prepared.points,residuals,workspace),prepared.points,100.0);
    const auto saved=owned;
    (void)one_per_source(subset,prepared.points,residuals,workspace);
    assert(owned==saved);
}

void randomized_differential() {
    std::mt19937 random(20260930);
    for (unsigned trial=0;trial<10'000;++trial) {
        std::vector<Candidate> candidates(32);
        std::vector<double> times,weights,residuals;
        std::vector<std::size_t> indexes;
        for (std::size_t index=0;index<candidates.size();++index) {
            Candidate& candidate=candidates[index];
            candidate.candidate_id="candidate-"+std::to_string(index);
            candidate.support_center_utc_ns=static_cast<std::int64_t>(random()%9)-4;
            switch (random()%5) {
                case 0: break;
                case 1: candidate.source_group_id="time:"+
                    std::to_string(candidate.support_center_utc_ns);break;
                case 2: candidate.source_group_id=std::string("nul\0key",7);break;
                default: candidate.source_group_id=std::string(80,'x')+
                    std::to_string(random()%7);break;
            }
            times.push_back(static_cast<double>(random()%5));
            weights.push_back(static_cast<double>(random()%3));
            residuals.push_back(static_cast<double>(static_cast<int>(random()%5)-2));
            if (random()%3) indexes.push_back(index);
        }
        std::shuffle(indexes.begin(),indexes.end(),random);
        const Prepared prepared=prepare(candidates,times,weights);
        SourceWorkspace workspace(prepared.group_count);
        require_equal(indexes,prepared,residuals,workspace);
        std::reverse(indexes.begin(),indexes.end());
        require_equal(indexes,prepared,residuals,workspace);
    }
}

void independent_lane(unsigned seed) {
    std::mt19937 random(seed);
    std::vector<Candidate> candidates(128);
    std::vector<double> times,weights,residuals;
    std::vector<std::size_t> indexes;
    for (std::size_t index=0;index<candidates.size();++index) {
        Candidate& candidate=candidates[index];
        candidate.candidate_id="lane-"+std::to_string(seed)+"-"+std::to_string(index);
        candidate.source_group_id="group-"+std::to_string(index%17);
        times.push_back(static_cast<double>(index));
        weights.push_back(static_cast<double>(1+index%3));
        residuals.push_back(static_cast<double>(static_cast<int>(index%5)-2));
        indexes.push_back(index);
    }
    const Prepared prepared=prepare(candidates,times,weights);
    SourceWorkspace workspace(prepared.group_count);
    for (unsigned repetition=0;repetition<1'000;++repetition) {
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
    leo::adaptive::tracking::deterministic_boundaries();
    leo::adaptive::tracking::randomized_differential();
    leo::adaptive::tracking::lane_isolation();
    std::cout<<"dense source workspace: boundaries, 20000 differential calls, repeated reset and lane isolation pass\n";
}
