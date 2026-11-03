#include "fast_tracks.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <tuple>
#include <unordered_map>
#include <utility>

namespace leo::adaptive::tracking::research::fast_tracks {
namespace {

constexpr double ns_per_second=1'000'000'000.0;
constexpr std::size_t no_parent=std::numeric_limits<std::size_t>::max();

struct LaneKey {
    int channel{};
    std::string edge;
    int receiver{};
    double rf{};
    bool operator<(const LaneKey& other) const {
        return std::tie(channel,edge,receiver,rf)<
            std::tie(other.channel,other.edge,other.receiver,other.rf);
    }
};

struct WorkPoint {
    const Candidate* source{};
    double time_s{};
    double frequency_hz{};
    double weight{};
};

struct Group {
    std::string id;
    std::vector<std::size_t> points;
    double first_time_s{};
};

struct Node {
    std::size_t parent{no_parent};
    std::size_t point{};
    std::size_t count{};
    double sum_weight{},sum_time{},sum_frequency{},sum_time2{},sum_time_frequency{};
    double start_s{},last_s{},slope{},intercept{},weighted_support{};
};

bool tagged_digest(const std::string& value) {
    return value.size()==71 && value.compare(0,7,"sha256:")==0 &&
        value.find_first_not_of("0123456789abcdef",7)==std::string::npos;
}

bool same_double(double left,double right) {
    std::uint64_t a=0,b=0;
    std::memcpy(&a,&left,sizeof(a));
    std::memcpy(&b,&right,sizeof(b));
    return a==b;
}

bool same_scientific_point(const Candidate& left,const Candidate& right) {
    return left.receiver_id==right.receiver_id && left.channel==right.channel &&
        left.edge==right.edge && same_double(left.actual_rf_hz,right.actual_rf_hz) &&
        left.support_start_utc_ns==right.support_start_utc_ns &&
        left.support_center_utc_ns==right.support_center_utc_ns &&
        left.support_end_utc_ns==right.support_end_utc_ns &&
        same_double(left.measured_cfo_hz,right.measured_cfo_hz) &&
        same_double(left.exact_score,right.exact_score) &&
        same_double(left.control_score,right.control_score) &&
        same_double(left.margin,right.margin);
}

double positive_mod(double value,double modulus) {
    const double result=std::fmod(value,modulus);
    return result<0.0 ? result+modulus : result;
}

double circular_residual(double frequency,double prediction,double spacing) {
    return positive_mod(frequency-prediction+spacing/2.0,spacing)-spacing/2.0;
}

double evidence_weight(const Candidate& value) {
    return std::min(std::max(value.margin,0.0)/std::max(value.control_score,0.02),16.0);
}

void validate(const std::vector<Candidate>& candidates,const Config& config) {
    const std::array<double,8> values{config.canonical_rf_hz,config.alias_spacing_hz,
        config.minimum_slope_hz_per_s,config.maximum_slope_hz_per_s,
        config.residual_gate_hz,config.maximum_gap_s,config.minimum_span_s,
        config.minimum_point_weight};
    if(candidates.empty() || candidates.size()>config.maximum_input_points ||
       std::any_of(values.begin(),values.end(),[](double value) {
           return !std::isfinite(value);
       }) || config.canonical_rf_hz<=0 || config.alias_spacing_hz<=0 ||
       config.minimum_slope_hz_per_s>=config.maximum_slope_hz_per_s ||
       config.residual_gate_hz<=0 || config.maximum_gap_s<=0 ||
       config.minimum_span_s<=0 || !config.minimum_support ||
       config.minimum_point_weight<=0 || config.slope_seed_count<2 ||
       config.slope_seed_count>4096 || !config.beam_width || config.beam_width>4096 ||
       !config.branches_per_state || config.branches_per_state>16 ||
       !config.maximum_tracks_per_lane || config.maximum_tracks_per_lane>64 ||
       !config.maximum_candidates_per_source_group ||
       !config.maximum_nodes_per_peel)
        throw std::invalid_argument("invalid fast-track configuration");

    std::set<std::string> candidate_ids;
    std::map<std::string,std::tuple<int,int,std::string,double>> bindings;
    std::map<std::string,std::size_t> counts;
    for(const Candidate& candidate:candidates) {
        const std::array<double,5> numeric{candidate.actual_rf_hz,candidate.measured_cfo_hz,
            candidate.exact_score,candidate.control_score,candidate.margin};
        if(!tagged_digest(candidate.candidate_id) ||
           !tagged_digest(candidate.source_group_id) ||
           !candidate_ids.insert(candidate.candidate_id).second ||
           std::any_of(numeric.begin(),numeric.end(),[](double value) {
               return !std::isfinite(value);
           }) || candidate.receiver_id<0 || candidate.channel<1 ||
           (candidate.edge!="lower" && candidate.edge!="upper") ||
           candidate.actual_rf_hz<=0 || candidate.support_start_utc_ns<=0 ||
           candidate.support_start_utc_ns>candidate.support_center_utc_ns ||
           candidate.support_center_utc_ns>=candidate.support_end_utc_ns ||
           candidate.margin<=0 ||
           std::abs(candidate.margin-(candidate.exact_score-candidate.control_score))>
               std::max(1e-12,1e-12*std::max(std::abs(candidate.margin),
                   std::abs(candidate.exact_score-candidate.control_score))))
            throw std::invalid_argument("invalid fast-track candidate");
        const auto binding=std::make_tuple(candidate.receiver_id,candidate.channel,
            candidate.edge,candidate.actual_rf_hz);
        const auto inserted=bindings.emplace(candidate.source_group_id,binding);
        if((!inserted.second && inserted.first->second!=binding) ||
           ++counts[candidate.source_group_id]>config.maximum_candidates_per_source_group)
            throw std::invalid_argument("invalid fast-track source group");
    }
}

bool better_node(const Node& left,const Node& right,const std::vector<WorkPoint>& points) {
    return std::make_tuple(left.weighted_support,left.count,left.last_s-left.start_s,
               -std::abs(left.slope),points[left.point].source->candidate_id) >
        std::make_tuple(right.weighted_support,right.count,right.last_s-right.start_s,
               -std::abs(right.slope),points[right.point].source->candidate_id);
}

std::int64_t slope_bucket(double slope,const Config& config) {
    const double step=(config.maximum_slope_hz_per_s-config.minimum_slope_hz_per_s)/
        static_cast<double>(config.slope_seed_count-1);
    return static_cast<std::int64_t>(std::llround(
        (slope-config.minimum_slope_hz_per_s)/step));
}

void append_node(std::vector<Node>& arena,Node value,const Config& config,Stats& stats) {
    if(arena.size()>=config.maximum_nodes_per_peel)
        throw std::length_error("fast-track node work bound exceeded");
    arena.push_back(value);
    ++stats.nodes_created;
}

Node seed(std::size_t point,double slope,const std::vector<WorkPoint>& points) {
    const auto& value=points[point];
    return {no_parent,point,1,value.weight,value.weight*value.time_s,
        value.weight*value.frequency_hz,value.weight*value.time_s*value.time_s,
        value.weight*value.time_s*value.frequency_hz,value.time_s,value.time_s,
        slope,value.frequency_hz-slope*value.time_s,value.weight};
}

bool extend(const Node& previous,std::size_t previous_index,std::size_t point,
            int alias,double spacing,const std::vector<WorkPoint>& points,
            const Config& config,Node& output) {
    const auto& value=points[point];
    if(value.time_s<=previous.last_s || value.time_s-previous.last_s>config.maximum_gap_s)
        return false;
    const double frequency=value.frequency_hz-alias*spacing;
    const double weight=value.weight;
    Node next{previous_index,point,previous.count+1,
        previous.sum_weight+weight,
        previous.sum_time+weight*value.time_s,
        previous.sum_frequency+weight*frequency,
        previous.sum_time2+weight*value.time_s*value.time_s,
        previous.sum_time_frequency+weight*value.time_s*frequency,
        previous.start_s,value.time_s,0,0,previous.weighted_support+weight};
    const double denominator=next.sum_weight*next.sum_time2-
        next.sum_time*next.sum_time;
    if(!(denominator>0) || !std::isfinite(denominator)) return false;
    next.slope=(next.sum_weight*next.sum_time_frequency-
        next.sum_time*next.sum_frequency)/denominator;
    next.intercept=(next.sum_frequency-next.slope*next.sum_time)/next.sum_weight;
    if(!std::isfinite(next.slope) || !std::isfinite(next.intercept) ||
       next.slope<config.minimum_slope_hz_per_s ||
       next.slope>config.maximum_slope_hz_per_s)
        return false;
    output=next;
    return true;
}

std::vector<std::size_t> prune(const std::vector<std::size_t>& input,
                               const std::vector<Node>& arena,
                               const std::vector<WorkPoint>& points,
                               const Config& config,std::size_t maximum) {
    std::map<std::pair<std::size_t,std::int64_t>,std::size_t> unique;
    for(std::size_t index:input) {
        const Node& node=arena[index];
        const auto key=std::make_pair(node.point,slope_bucket(node.slope,config));
        const auto found=unique.find(key);
        if(found==unique.end() || better_node(node,arena[found->second],points))
            unique[key]=index;
    }
    std::vector<std::size_t> output;
    output.reserve(unique.size());
    for(const auto& [key,index]:unique) {
        (void)key;
        output.push_back(index);
    }
    std::sort(output.begin(),output.end(),[&](std::size_t left,std::size_t right) {
        return better_node(arena[left],arena[right],points);
    });
    if(output.size()>maximum) output.resize(maximum);
    return output;
}

std::vector<std::size_t> path(std::size_t node,const std::vector<Node>& arena) {
    std::vector<std::size_t> output;
    while(node!=no_parent) {
        output.push_back(arena[node].point);
        node=arena[node].parent;
    }
    std::reverse(output.begin(),output.end());
    return output;
}

bool make_track(std::size_t node,const std::vector<Node>& arena,
                const std::vector<WorkPoint>& points,const LaneKey& lane,
                std::int64_t reference,double spacing,const Config& config,
                Track& output) {
    const Node& state=arena[node];
    if(state.count<config.minimum_support ||
       state.last_s-state.start_s<config.minimum_span_s)
        return false;
    const auto indexes=path(node,arena);
    if(indexes.size()!=state.count) throw std::logic_error("fast-track parent chain corrupt");
    Track track;
    track.lane={lane.channel,lane.edge,lane.receiver,lane.rf};
    track.reference_utc_ns=reference;
    track.normalized_rate_hz_per_s=state.slope;
    track.normalized_intercept_hz=state.intercept;
    track.weighted_support=state.weighted_support;
    track.start_utc_ns=std::numeric_limits<std::int64_t>::max();
    track.end_utc_ns=std::numeric_limits<std::int64_t>::min();
    double squared=0;
    for(std::size_t index:indexes) {
        const WorkPoint& point=points[index];
        const double prediction=state.slope*point.time_s+state.intercept;
        const int alias=static_cast<int>(std::nearbyint(
            (point.frequency_hz-prediction)/spacing));
        const double dealiased=point.frequency_hz-alias*spacing;
        const double residual=dealiased-prediction;
        if(std::abs(residual)>config.residual_gate_hz) return false;
        squared+=residual*residual;
        track.residual_max_hz=std::max(track.residual_max_hz,std::abs(residual));
        track.start_utc_ns=std::min(track.start_utc_ns,point.source->support_start_utc_ns);
        track.end_utc_ns=std::max(track.end_utc_ns,point.source->support_end_utc_ns);
        track.points.push_back({point.source->candidate_id,point.source->source_group_id,
            alias,point.frequency_hz,dealiased});
    }
    track.residual_rms_hz=std::sqrt(squared/static_cast<double>(indexes.size()));
    output=std::move(track);
    return true;
}

bool same_trajectory(const Track& left,const Track& right,double spacing,
                     const Config& config) {
    const std::int64_t begin=std::max(left.start_utc_ns,right.start_utc_ns);
    const std::int64_t end=std::min(left.end_utc_ns,right.end_utc_ns);
    if(begin>=end) return false;
    const auto left_span=left.end_utc_ns-left.start_utc_ns;
    const auto right_span=right.end_utc_ns-right.start_utc_ns;
    if(static_cast<long double>(end-begin)<
            .8L*static_cast<long double>(std::min(left_span,right_span)) ||
       std::abs(left.normalized_rate_hz_per_s-right.normalized_rate_hz_per_s)>250.0)
        return false;
    const std::int64_t middle=begin+(end-begin)/2;
    const auto value=[&](const Track& track) {
        return track.normalized_intercept_hz+track.normalized_rate_hz_per_s*
            ((middle-track.reference_utc_ns)/ns_per_second);
    };
    return std::abs(circular_residual(value(left),value(right),spacing))<=
        config.residual_gate_hz;
}

std::vector<Track> find_tracks(const std::vector<WorkPoint>& points,
                const std::vector<Group>& groups,const std::vector<bool>& available,
                const LaneKey& lane,std::int64_t reference,double spacing,
                const Config& config,Stats& stats) {
    std::vector<Node> arena;
    arena.reserve(std::min(config.maximum_nodes_per_peel,
        groups.size()*(config.beam_width*config.branches_per_state+
            config.maximum_candidates_per_source_group*config.slope_seed_count)));
    std::vector<std::size_t> beam,best;
    const double slope_step=(config.maximum_slope_hz_per_s-
        config.minimum_slope_hz_per_s)/static_cast<double>(config.slope_seed_count-1);
    for(const Group& group:groups) {
        std::vector<std::size_t> next;
        next.reserve(beam.size()*(config.branches_per_state+1)+
            group.points.size()*config.slope_seed_count);
        for(std::size_t state_index:beam) {
            const Node& state=arena[state_index];
            if(group.first_time_s-state.last_s<=config.maximum_gap_s)
                next.push_back(state_index);
            struct Extension { double residual{};double negative_weight{};std::string id;std::size_t point{};int alias{}; };
            std::vector<Extension> candidates;
            for(std::size_t point_index:group.points) {
                if(!available[point_index]) continue;
                const WorkPoint& point=points[point_index];
                if(point.time_s<=state.last_s ||
                   point.time_s-state.last_s>config.maximum_gap_s) continue;
                const double prediction=state.slope*point.time_s+state.intercept;
                const int alias=static_cast<int>(std::nearbyint(
                    (point.frequency_hz-prediction)/spacing));
                const double residual=point.frequency_hz-alias*spacing-prediction;
                if(std::abs(residual)<=config.residual_gate_hz)
                    candidates.push_back({std::abs(residual),-point.weight,
                        point.source->candidate_id,point_index,alias});
            }
            std::sort(candidates.begin(),candidates.end(),[](const Extension& left,
                                                             const Extension& right) {
                return std::tie(left.residual,left.negative_weight,left.id)<
                    std::tie(right.residual,right.negative_weight,right.id);
            });
            if(candidates.size()>config.branches_per_state)
                candidates.resize(config.branches_per_state);
            for(const Extension& candidate:candidates) {
                Node extended;
                if(extend(state,state_index,candidate.point,candidate.alias,
                          spacing,points,config,extended)) {
                    append_node(arena,extended,config,stats);
                    next.push_back(arena.size()-1);
                }
            }
        }
        for(std::size_t point_index:group.points) {
            if(!available[point_index]) continue;
            for(std::size_t slope_index=0;slope_index<config.slope_seed_count;++slope_index) {
                append_node(arena,seed(point_index,config.minimum_slope_hz_per_s+
                    slope_step*slope_index,points),config,stats);
                next.push_back(arena.size()-1);
            }
        }
        beam=prune(next,arena,points,config,config.beam_width);
        stats.maximum_live_beam=std::max(stats.maximum_live_beam,beam.size());
        for(std::size_t index:beam)
            if(arena[index].count>=config.minimum_support &&
               arena[index].last_s-arena[index].start_s>=config.minimum_span_s)
                best.push_back(index);
        const std::size_t best_limit=config.maximum_tracks_per_lane>
            std::numeric_limits<std::size_t>::max()/config.beam_width ?
            std::numeric_limits<std::size_t>::max() :
            config.maximum_tracks_per_lane*config.beam_width;
        best=prune(best,arena,points,config,best_limit);
    }
    std::vector<Track> output;
    for(std::size_t node:best) {
        Track track;
        if(!make_track(node,arena,points,lane,reference,spacing,config,track)) continue;
        if(std::any_of(output.begin(),output.end(),[&](const Track& retained) {
            return same_trajectory(track,retained,spacing,config);
        })) continue;
        output.push_back(std::move(track));
        if(output.size()==config.maximum_tracks_per_lane) break;
    }
    return output;
}

std::vector<Track> reconstruct_lane(const LaneKey& lane,
                                    std::vector<const Candidate*> candidates,
                                    const Config& config,Stats& stats) {
    std::sort(candidates.begin(),candidates.end(),[](const Candidate* left,
                                                     const Candidate* right) {
        return std::tie(left->support_center_utc_ns,left->measured_cfo_hz,
                   left->candidate_id)<
            std::tie(right->support_center_utc_ns,right->measured_cfo_hz,
                   right->candidate_id);
    });
    const std::int64_t reference=candidates.front()->support_center_utc_ns;
    const double scale=config.canonical_rf_hz/lane.rf;
    const double spacing=config.alias_spacing_hz*scale;
    std::vector<WorkPoint> points;
    points.reserve(candidates.size());
    for(const Candidate* candidate:candidates)
        points.push_back({candidate,
            (candidate->support_center_utc_ns-reference)/ns_per_second,
            candidate->measured_cfo_hz*scale,evidence_weight(*candidate)});

    std::map<std::string,std::vector<std::size_t>> grouped;
    for(std::size_t index=0;index<points.size();++index) grouped[points[index].source->source_group_id].push_back(index);
    std::vector<Group> groups;
    groups.reserve(grouped.size());
    for(auto& [id,indexes]:grouped) {
        std::sort(indexes.begin(),indexes.end(),[&](std::size_t left,std::size_t right) {
            return std::tie(points[left].time_s,points[left].frequency_hz,
                       points[left].source->candidate_id)<
                std::tie(points[right].time_s,points[right].frequency_hz,
                       points[right].source->candidate_id);
        });
        const auto unique_end=std::unique(indexes.begin(),indexes.end(),
            [&](std::size_t left,std::size_t right) {
                return same_scientific_point(*points[left].source,*points[right].source);
            });
        stats.exact_duplicates_consolidated+=static_cast<std::size_t>(
            indexes.end()-unique_end);
        indexes.erase(unique_end,indexes.end());
        const double first_time=points[indexes.front()].time_s;
        groups.push_back({id,std::move(indexes),first_time});
    }
    std::sort(groups.begin(),groups.end(),[](const Group& left,const Group& right) {
        return std::tie(left.first_time_s,left.id)<std::tie(right.first_time_s,right.id);
    });
    stats.source_groups+=groups.size();

    std::vector<bool> available(points.size());
    std::transform(points.begin(),points.end(),available.begin(),[&](const WorkPoint& point) {
        return point.weight>=config.minimum_point_weight;
    });
    ++stats.peel_passes;
    return find_tracks(points,groups,available,lane,reference,spacing,config,stats);
}

}  // namespace

Result reconstruct(const std::vector<Candidate>& candidates,const Config& config) {
    validate(candidates,config);
    std::map<LaneKey,std::vector<const Candidate*>> lanes;
    for(const Candidate& candidate:candidates)
        lanes[{candidate.channel,candidate.edge,candidate.receiver_id,
            candidate.actual_rf_hz}].push_back(&candidate);
    Result result;
    result.input_candidate_count=candidates.size();
    result.stats.lanes=lanes.size();
    for(auto& [lane,rows]:lanes) {
        auto tracks=reconstruct_lane(lane,std::move(rows),config,result.stats);
        result.tracks.insert(result.tracks.end(),
            std::make_move_iterator(tracks.begin()),std::make_move_iterator(tracks.end()));
    }
    for(const Track& track:result.tracks) result.used_candidate_count+=track.points.size();
    return result;
}

}  // namespace leo::adaptive::tracking::research::fast_tracks
