#include "../../../reports/2026_09_30_native_adaptive_deployment/tracking/research/tracking_fit_chosen_point.cpp"

#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>

namespace leo::adaptive::tracking {
namespace {

bool fit_same_bits(double left,double right) {
    return std::memcmp(&left,&right,sizeof(left))==0;
}

bool same_fit_segment(const Segment& left,const Segment& right) {
    return left.segment_id==right.segment_id && left.indexes==right.indexes &&
        fit_same_bits(left.start_s,right.start_s) &&
        fit_same_bits(left.end_s,right.end_s) &&
        fit_same_bits(left.weighted_support,right.weighted_support) &&
        fit_same_bits(left.slope,right.slope) &&
        fit_same_bits(left.intercept,right.intercept) &&
        fit_same_bits(left.residual_rms,right.residual_rms) &&
        fit_same_bits(left.residual_max,right.residual_max);
}

std::vector<Point> fit_fixture(std::vector<Candidate>& candidates) {
    candidates.resize(3U);
    std::vector<Point> points;
    for (std::size_t index=0;index<candidates.size();++index) {
        candidates[index].candidate_id="candidate-"+std::to_string(index);
        candidates[index].source_group_id="source-"+std::to_string(index);
        points.push_back(Point{&candidates[index],static_cast<double>(index),
            10.0+3.0*static_cast<double>(index),1.0});
    }
    return points;
}

void test_exact_key_collision_and_fields() {
    std::vector<Candidate> candidates;
    const auto points=fit_fixture(candidates);
    const std::vector<std::size_t> forward{0U,1U,2U};
    const std::vector<std::size_t> reverse{2U,1U,0U};
    double first=1.0,second=std::nextafter(first,2.0);
    const auto bucket=[&](double slope) {
        return fit_key_hash(forward,fit_double_bits(slope),
            fit_double_bits(2.0),fit_double_bits(100.0))%8U;
    };
    while (bucket(first)!=bucket(second))
        second=std::nextafter(second,std::numeric_limits<double>::infinity());

    ExactFitCache cache(1024U*1024U,8U);
    const Segment a=cache.get(forward,points,first,2.0,100.0);
    const Segment b=cache.get(forward,points,second,2.0,100.0);
    cache.get(reverse,points,first,2.0,100.0);
    cache.get(forward,points,first,-0.0,100.0);
    cache.get(forward,points,first,2.0,
        std::nextafter(100.0,101.0));
    assert(same_fit_segment(a,cache.get(forward,points,first,2.0,100.0)));
    assert(same_fit_segment(b,cache.get(forward,points,second,2.0,100.0)));
    assert(cache.stores()==5U && cache.hits()==2U && cache.fallbacks()==0U);
}

void test_full_table_and_capacity_fall_back_exactly() {
    std::vector<Candidate> candidates;
    const auto points=fit_fixture(candidates);
    const std::vector<std::size_t> indexes{0U,1U,2U};
    ExactFitCache full(1024U*1024U,1U);
    full.get(indexes,points,0.0,2.0,100.0);
    const Segment full_result=full.get(indexes,points,-0.0,2.0,100.0);
    assert(same_fit_segment(full_result,
        fit_segment(indexes,points,-0.0,2.0,100.0)));
    assert(full.stores()==1U && full.fallbacks()==1U);

    const std::size_t table_bytes=ExactFitCache::minimum_retained_bytes(1U);
    ExactFitCache capped(table_bytes,1U);
    const Segment capped_result=capped.get(indexes,points,1.0,2.0,100.0);
    assert(same_fit_segment(capped_result,
        fit_segment(indexes,points,1.0,2.0,100.0)));
    assert(capped.stores()==0U && capped.fallbacks()==1U);
    assert(capped.retained_bytes()==table_bytes);

    ExactFitCache undersized(table_bytes-1U,1U);
    assert(undersized.retained_bytes()==0U && undersized.fallbacks()==1U);
}

void test_optional_allocation_failures_fall_back_exactly() {
    std::vector<Candidate> candidates;
    const auto points=fit_fixture(candidates);
    const std::vector<std::size_t> indexes{0U,1U,2U};
    const Segment expected=fit_segment(indexes,points,1.0,2.0,100.0);

    ExactFitCache table_failure(1024U*1024U,8U,
        FitCacheFault::table_allocation);
    assert(same_fit_segment(table_failure.get(indexes,points,1.0,2.0,100.0),
        expected));
    assert(same_fit_segment(table_failure.get(indexes,points,1.0,2.0,100.0),
        expected));
    assert(table_failure.stores()==0U && table_failure.fallbacks()==1U);

    ExactFitCache store_failure(1024U*1024U,8U,
        FitCacheFault::entry_storage);
    assert(same_fit_segment(store_failure.get(indexes,points,1.0,2.0,100.0),
        expected));
    assert(same_fit_segment(store_failure.get(indexes,points,1.0,2.0,100.0),
        expected));
    assert(same_fit_segment(store_failure.get(indexes,points,1.0,2.0,100.0),
        expected));
    assert(store_failure.stores()==1U && store_failure.hits()==1U &&
        store_failure.fallbacks()==1U);
}

}  // namespace
}  // namespace leo::adaptive::tracking

int main() {
    leo::adaptive::tracking::test_exact_key_collision_and_fields();
    leo::adaptive::tracking::test_full_table_and_capacity_fall_back_exactly();
    leo::adaptive::tracking::test_optional_allocation_failures_fall_back_exactly();
    std::cout << "exact fit cache internal tests passed\n";
}
