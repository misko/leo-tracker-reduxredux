#include "seed_expand.hpp"

// This isolated research translation unit reuses the maintained tracker's
// private numerical fit and source-selection rules. It is never linked into
// the production tracking archive.
#include "../../tracking.cpp"

#include <algorithm>
#include <cmath>
#include <map>
#include <set>
#include <stdexcept>
#include <tuple>

namespace leo::adaptive::tracking {
namespace research::seed_expand {
namespace {

bool same_lane(const Lane& left,const LaneKey& right) {
    return left.channel==right.channel && left.edge==right.edge &&
        left.receiver_id==right.receiver_id && left.actual_rf_hz==right.actual_rf_hz;
}

bool near_geometry(const Segment& left,const Segment& right,double spacing,
                   double gate) {
    const double begin=std::max(left.start_s,right.start_s);
    const double end=std::min(left.end_s,right.end_s);
    if(begin>=end || end-begin<.8*std::min(left.end_s-left.start_s,
                                           right.end_s-right.start_s) ||
       std::abs(left.slope-right.slope)>250.0)
        return false;
    const double middle=begin+(end-begin)/2;
    return std::abs(circular_residual(left.slope*middle+left.intercept,
        right.slope*middle+right.intercept,spacing))<=gate;
}

Track make_track(const LaneKey& lane,const Segment& segment,
                 const std::vector<Point>& points,const tracking::Config& config,
                 std::int64_t reference,double spacing) {
    Track track;
    track.segment_id=segment.segment_id;
    track.tracklet_id=tracklet_identity(lane,segment,points,config);
    track.lane={lane.channel,lane.edge,lane.receiver_id,lane.actual_rf_hz};
    track.reference_utc_ns=reference;
    track.normalized_rate_hz_per_s=segment.slope;
    track.normalized_intercept_hz=segment.intercept;
    track.residual_rms_hz=segment.residual_rms;
    track.residual_max_hz=segment.residual_max;
    track.weighted_support=segment.weighted_support;
    track.start_utc_ns=std::numeric_limits<std::int64_t>::max();
    track.end_utc_ns=std::numeric_limits<std::int64_t>::min();
    for(std::size_t index:segment.indexes) {
        const auto& point=points[index];
        const int alias=static_cast<int>(std::nearbyint((point.frequency_hz-
            (segment.slope*point.time_s+segment.intercept))/spacing));
        track.points.push_back({point.source->candidate_id,point.source->source_group_id,
            alias,point.frequency_hz,point.frequency_hz-alias*spacing});
        track.start_utc_ns=std::min(track.start_utc_ns,point.source->support_start_utc_ns);
        track.end_utc_ns=std::max(track.end_utc_ns,point.source->support_end_utc_ns);
    }
    return track;
}

}  // namespace

Result expand(const std::vector<Candidate>& candidates,const std::vector<Seed>& seeds,
              const Config& config) {
    validate(candidates,config.tracking);
    if(seeds.empty() || seeds.size()>config.maximum_seeds ||
       !config.maximum_hypotheses_per_lane ||
       config.maximum_hypotheses_per_lane>64)
        throw std::invalid_argument("invalid seed expansion bounds");
    for(const Seed& seed:seeds)
        if(seed.lane.receiver_id<0 || seed.lane.channel<1 ||
           (seed.lane.edge!="lower" && seed.lane.edge!="upper") ||
           !std::isfinite(seed.lane.actual_rf_hz) || seed.lane.actual_rf_hz<=0 ||
           seed.start_utc_ns<=0 || seed.end_utc_ns<=seed.start_utc_ns ||
           seed.reference_utc_ns<=0 || !std::isfinite(seed.normalized_rate_hz_per_s) ||
           !std::isfinite(seed.normalized_intercept_hz) ||
           seed.normalized_rate_hz_per_s<config.tracking.minimum_slope_hz_per_s ||
           seed.normalized_rate_hz_per_s>config.tracking.maximum_slope_hz_per_s)
            throw std::invalid_argument("invalid source-only track seed");

    Result result;
    result.input_candidate_count=candidates.size();
    result.seed_count=seeds.size();
    const LaneRows lanes=ordered_lanes(candidates);
    std::set<std::string> used_candidates;
    for(const auto& [lane,rows]:lanes) {
        std::vector<const Seed*> lane_seeds;
        for(const Seed& seed:seeds) if(same_lane(seed.lane,lane)) lane_seeds.push_back(&seed);
        if(lane_seeds.empty()) continue;
        const std::int64_t reference=rows.front()->support_center_utc_ns;
        const double scale=config.tracking.canonical_rf_hz/lane.actual_rf_hz;
        const double spacing=config.tracking.alias_spacing_hz*scale;
        SourceGroups groups=bind_source_groups(rows);
        std::vector<Point> points;
        points.reserve(rows.size());
        for(const Candidate* candidate:rows)
            points.push_back({candidate,
                (candidate->support_center_utc_ns-reference)/kNsPerSecond,
                candidate->measured_cfo_hz*scale,evidence_weight(*candidate)});
        SourceWorkspace workspace(std::move(groups.point_group_indexes),groups.group_count);
        std::vector<bool> all_available(points.size());
        std::transform(points.begin(),points.end(),all_available.begin(),
            [&](const Point& point) {
                return point.weight>=config.tracking.minimum_point_weight;
            });
        ExactFitCache fit_cache;
        std::vector<Segment> expanded;
        for(const Seed* seed:lane_seeds) {
            const double intercept=seed->normalized_intercept_hz+
                seed->normalized_rate_hz_per_s*
                ((reference-seed->reference_utc_ns)/kNsPerSecond);
            auto segments=candidate_segments(points,all_available,
                seed->normalized_rate_hz_per_s,intercept,config.tracking,spacing,
                fit_cache,workspace);
            result.expanded_segment_count+=segments.size();
            expanded.insert(expanded.end(),std::make_move_iterator(segments.begin()),
                std::make_move_iterator(segments.end()));
        }
        std::map<std::string,Segment> exact;
        for(Segment& segment:expanded) {
            auto found=exact.find(segment.segment_id);
            if(found==exact.end()) exact.emplace(segment.segment_id,std::move(segment));
            else {
                ++result.exact_segments_consolidated;
                if(better_segment(segment,found->second)) found->second=std::move(segment);
            }
        }
        expanded.clear();
        for(auto& [identity,segment]:exact) {
            (void)identity;
            expanded.push_back(std::move(segment));
        }
        std::sort(expanded.begin(),expanded.end(),[](const Segment& left,const Segment& right) {
            return better_segment(left,right);
        });
        std::vector<Segment> retained;
        for(Segment& segment:expanded) {
            if(std::any_of(retained.begin(),retained.end(),[&](const Segment& previous) {
                return near_geometry(segment,previous,spacing,config.tracking.residual_gate_hz);
            })) {
                ++result.near_geometry_consolidated;
                continue;
            }
            for(std::size_t index:segment.indexes)
                if(!used_candidates.insert(points[index].source->candidate_id).second)
                    ++result.shared_candidate_overlaps;
            retained.push_back(std::move(segment));
            if(retained.size()==config.maximum_hypotheses_per_lane) break;
        }
        for(const Segment& segment:retained)
            result.tracks.push_back(make_track(lane,segment,points,config.tracking,
                reference,spacing));
    }
    result.used_candidate_count=used_candidates.size();
    return result;
}

}  // namespace research::seed_expand
}  // namespace leo::adaptive::tracking
