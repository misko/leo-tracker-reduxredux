#include "../../../reports/2026_09_30_native_adaptive_deployment/tracking/research/tracking_exact_fit_cache_testable.cpp"

#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>

namespace leo::adaptive::tracking {
namespace {

bool same_bits(double left,double right) {
    return std::memcmp(&left,&right,sizeof(left))==0;
}

bool same_segment(const Segment& left,const Segment& right) {
    return left.segment_id==right.segment_id && left.indexes==right.indexes &&
        same_bits(left.start_s,right.start_s) &&
        same_bits(left.end_s,right.end_s) &&
        same_bits(left.weighted_support,right.weighted_support) &&
        same_bits(left.slope,right.slope) &&
        same_bits(left.intercept,right.intercept) &&
        same_bits(left.residual_rms,right.residual_rms) &&
        same_bits(left.residual_max,right.residual_max);
}

std::vector<Point> fixture_points(std::vector<Candidate>& candidates) {
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

void test_collision_and_exact_hit() {
    std::vector<Candidate> candidates;
    const auto points=fixture_points(candidates);
    const std::vector<std::size_t> indexes{0U,1U,2U};
    double first=1.0,second=std::nextafter(first,2.0);
    const auto bucket=[&](double slope) {
        return fit_key_hash(indexes,fit_double_bits(slope),
            fit_double_bits(2.0),fit_double_bits(100.0))%2U;
    };
    while (bucket(first)!=bucket(second))
        second=std::nextafter(second,std::numeric_limits<double>::infinity());

    FitCacheStats stats;
    ExactFitCache cache(stats,1024U*1024U,2U);
    const Segment first_result=cache.get(indexes,points,first,2.0,100.0);
    const Segment second_result=cache.get(indexes,points,second,2.0,100.0);
    assert(same_segment(first_result,cache.get(indexes,points,first,2.0,100.0)));
    assert(same_segment(second_result,cache.get(indexes,points,second,2.0,100.0)));
    assert(stats.misses==2U && stats.stores==2U && stats.hits==2U);
    assert(stats.capacity_fallbacks==0U);
}

void test_full_table_and_signed_zero_are_exact_fallbacks() {
    std::vector<Candidate> candidates;
    const auto points=fixture_points(candidates);
    const std::vector<std::size_t> indexes{0U,1U,2U};
    FitCacheStats stats;
    ExactFitCache cache(stats,1024U*1024U,1U);
    const Segment positive=cache.get(indexes,points,0.0,2.0,100.0);
    const Segment negative=cache.get(indexes,points,-0.0,2.0,100.0);
    const Segment reference=fit_segment(indexes,points,-0.0,2.0,100.0);
    assert(same_segment(negative,reference));
    assert(same_segment(positive,cache.get(indexes,points,0.0,2.0,100.0)));
    assert(stats.misses==2U && stats.stores==1U && stats.hits==1U);
    assert(stats.capacity_fallbacks==1U);
}

void test_capacity_and_numeric_key_fallbacks() {
    std::vector<Candidate> candidates;
    const auto points=fixture_points(candidates);
    const std::vector<std::size_t> indexes{0U,1U,2U};
    FitCacheStats capacity_stats;
    const std::size_t table_bytes=ExactFitCache::minimum_retained_bytes(1U);
    ExactFitCache capacity_cache(capacity_stats,table_bytes,1U);
    const Segment actual=capacity_cache.get(indexes,points,1.0,2.0,100.0);
    const Segment expected=fit_segment(indexes,points,1.0,2.0,100.0);
    assert(same_segment(actual,expected));
    assert(capacity_stats.misses==1U && capacity_stats.stores==0U);
    assert(capacity_stats.capacity_fallbacks==1U);
    assert(capacity_stats.maximum_retained_bytes==table_bytes);

    FitCacheStats numeric_stats;
    ExactFitCache numeric_cache(numeric_stats,1024U*1024U,4U);
    const double adjacent=std::nextafter(1.0,2.0);
    numeric_cache.get(indexes,points,1.0,2.0,100.0);
    numeric_cache.get(indexes,points,adjacent,2.0,100.0);
    assert(numeric_stats.misses==2U && numeric_stats.hits==0U);
}

void test_all_key_fields_and_order_are_distinct() {
    std::vector<Candidate> candidates;
    const auto points=fixture_points(candidates);
    const std::vector<std::size_t> forward{0U,1U,2U};
    const std::vector<std::size_t> reverse{2U,1U,0U};
    FitCacheStats stats;
    ExactFitCache cache(stats,1024U*1024U,16U);
    cache.get(forward,points,1.0,0.0,100.0);
    cache.get(reverse,points,1.0,0.0,100.0);
    cache.get(forward,points,1.0,-0.0,100.0);
    cache.get(forward,points,1.0,0.0,
        std::nextafter(100.0,101.0));
    assert(stats.misses==4U && stats.stores==4U && stats.hits==0U);
    cache.get(forward,points,1.0,0.0,100.0);
    assert(stats.hits==1U);
}

void test_table_allocation_must_fit_budget() {
    FitCacheStats stats;
    bool rejected=false;
    try {
        const std::size_t table_bytes=ExactFitCache::minimum_retained_bytes(2U);
        ExactFitCache invalid(stats,table_bytes-1U,2U);
        (void)invalid;
    } catch (const std::invalid_argument&) {
        rejected=true;
    }
    assert(rejected);
}

}  // namespace
}  // namespace leo::adaptive::tracking

int main() {
    leo::adaptive::tracking::test_collision_and_exact_hit();
    leo::adaptive::tracking::test_full_table_and_signed_zero_are_exact_fallbacks();
    leo::adaptive::tracking::test_capacity_and_numeric_key_fallbacks();
    leo::adaptive::tracking::test_all_key_fields_and_order_are_distinct();
    leo::adaptive::tracking::test_table_allocation_must_fit_budget();
    std::cout << "exact fit cache research tests passed\n";
}
