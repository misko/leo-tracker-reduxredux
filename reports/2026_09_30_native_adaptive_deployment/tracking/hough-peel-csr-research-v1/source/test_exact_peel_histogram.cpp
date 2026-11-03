#include "tracking.cpp"

#include <cassert>
#include <cstring>
#include <queue>

namespace leo::adaptive::tracking {
namespace {

bool same_bits(double left,double right) {
    return std::memcmp(&left,&right,sizeof(double))==0;
}

std::vector<double> rebuild(const std::vector<Point>& points,
                            const std::vector<bool>& available,
                            std::size_t slope_bins,std::size_t intercept_bins,
                            const PersistentBinLookup& bins) {
    std::vector<double> result(slope_bins*intercept_bins,0.0);
    for (std::size_t slope=0;slope<slope_bins;++slope)
        for (std::size_t point=0;point<points.size();++point)
            if (available[point])
                result[slope*intercept_bins+bins.value(slope,point)]+=
                    points[point].weight;
    return result;
}

void require_exact(ExactPeelHistogram& histogram,
                   const std::vector<Point>& points,
                   const std::vector<bool>& available,
                   std::size_t slope_bins,std::size_t intercept_bins,
                   const PersistentBinLookup& bins) {
    const auto expected=rebuild(points,available,slope_bins,intercept_bins,bins);
    for (std::size_t cell=0;cell<expected.size();++cell)
        assert(same_bits(histogram.value(cell,points,available),expected[cell]));
}

void first_peel_retirement_duplicates_and_empty() {
    constexpr std::size_t slopes=2U;
    constexpr std::size_t intercepts=3U;
    std::vector<Candidate> candidates(6U);
    const std::vector<double> weights{1.0e16,1.0,1.0,2.0,3.0,4.0};
    std::vector<Point> points;
    for (std::size_t index=0;index<weights.size();++index)
        points.push_back(Point{&candidates[index],static_cast<double>(index),
            static_cast<double>(index),weights[index]});
    BinChunk chunk;
    chunk.first_point=0U;
    chunk.point_count=points.size();
    chunk.values={0,0,0,1,2,2, 2,1,0,1,2,0};
    std::vector<BinChunk> chunks;
    chunks.push_back(std::move(chunk));
    const BinView view{&chunks};
    const PersistentBinLookup lookup(view,points.size());
    std::vector<bool> available(points.size(),true);
    ExactPeelHistogram histogram(points,available,slopes,intercepts,lookup);

    // The first three points share one bin. Their deliberately ill-conditioned
    // positive weights make any contributor reordering observable in FP64.
    require_exact(histogram,points,available,slopes,intercepts,lookup);

    available[1]=false;
    available[4]=false;
    histogram.retire({1U,4U},lookup);
    require_exact(histogram,points,available,slopes,intercepts,lookup);

    std::vector<std::size_t> remaining;
    for (std::size_t point=0;point<available.size();++point) {
        if (available[point]) remaining.push_back(point);
        available[point]=false;
    }
    histogram.retire(remaining,lookup);
    require_exact(histogram,points,available,slopes,intercepts,lookup);

    const std::vector<Point> no_points;
    const std::vector<bool> no_available;
    const std::vector<BinChunk> no_chunks;
    const BinView empty_view{&no_chunks};
    const PersistentBinLookup empty_lookup(empty_view,0U);
    ExactPeelHistogram empty(no_points,no_available,slopes,intercepts,
        empty_lookup);
    require_exact(empty,no_points,no_available,slopes,intercepts,empty_lookup);
}

std::vector<std::size_t> top_cells(const std::vector<double>& values,
                                   std::size_t count) {
    struct Peak {double value;std::size_t index;};
    const auto better=[](const Peak& left,const Peak& right) {
        return left.value>right.value ||
            (left.value==right.value && left.index>right.index);
    };
    std::priority_queue<Peak,std::vector<Peak>,decltype(better)> peaks(better);
    for (std::size_t index=0;index<values.size();++index) {
        const Peak candidate{values[index],index};
        if (peaks.size()<count) peaks.push(candidate);
        else if (better(candidate,peaks.top())) {
            peaks.pop();
            peaks.push(candidate);
        }
    }
    std::vector<Peak> ordered;
    while (!peaks.empty()) {
        ordered.push_back(peaks.top());
        peaks.pop();
    }
    std::sort(ordered.begin(),ordered.end(),better);
    std::vector<std::size_t> result;
    for (const Peak& peak:ordered) result.push_back(peak.index);
    return result;
}

void peak_ties_remain_exact() {
    constexpr std::size_t slopes=2U;
    constexpr std::size_t intercepts=2U;
    std::vector<Candidate> candidates(4U);
    std::vector<Point> points;
    for (std::size_t index=0;index<candidates.size();++index)
        points.push_back(Point{&candidates[index],0.0,0.0,1.0});
    BinChunk chunk{0U,4U,{0,0,1,1, 0,1,0,1}};
    std::vector<BinChunk> chunks;
    chunks.push_back(std::move(chunk));
    const BinView view{&chunks};
    const PersistentBinLookup lookup(view,points.size());
    std::vector<bool> available(points.size(),true);
    ExactPeelHistogram histogram(points,available,slopes,intercepts,lookup);
    auto expected=rebuild(points,available,slopes,intercepts,lookup);
    std::vector<double> actual(expected.size());
    for (std::size_t cell=0;cell<actual.size();++cell)
        actual[cell]=histogram.value(cell,points,available);
    assert(top_cells(actual,3U)==top_cells(expected,3U));

    available[0]=false;
    available[3]=false;
    histogram.retire({0U,3U},lookup);
    expected=rebuild(points,available,slopes,intercepts,lookup);
    for (std::size_t cell=0;cell<actual.size();++cell)
        actual[cell]=histogram.value(cell,points,available);
    assert(top_cells(actual,3U)==top_cells(expected,3U));
}

} // namespace
} // namespace leo::adaptive::tracking

int main() {
    leo::adaptive::tracking::first_peel_retirement_duplicates_and_empty();
    leo::adaptive::tracking::peak_ties_remain_exact();
}
