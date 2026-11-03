#include "curvature_tracks.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>

namespace leo::adaptive::tracking::research::curvature_tracks {
namespace {

constexpr double kNsPerSecond=1'000'000'000.0;

struct LaneKey {
    int channel{};
    std::string edge;
    int receiver_id{};
    double actual_rf_hz{};
    bool operator<(const LaneKey& other) const {
        return std::tie(channel,edge,receiver_id,actual_rf_hz)<
               std::tie(other.channel,other.edge,other.receiver_id,other.actual_rf_hz);
    }
};

struct Point {
    const tracking::Candidate* source{};
    double time_s{};
    double raw_hz{};
    double weight{};
};

struct Group {
    std::string source_id;
    double time_s{};
    double minimum_time_s{};
    double maximum_time_s{};
    std::vector<std::size_t> points;
};

struct State {
    double time_s{};
    double frequency_hz{};
    double rate_hz_per_s{};
    double acceleration_hz_per_s2{};
    double frequency_uncertainty_hz{};
    double rate_uncertainty_hz_per_s{};
    double rms_hz{};
};

struct Hypothesis {
    std::vector<std::size_t> indexes;
    std::vector<double> frequencies;
    std::vector<std::size_t> state_indexes;
    std::vector<double> state_frequencies;
    State state;
    double score{};
    double maximum_abs_acceleration{};
};

struct Seed {
    std::size_t first_group{};
    std::size_t second_group{};
    std::size_t first_point{};
    std::size_t second_point{};
    double first_frequency{};
    double second_frequency{};
    double rate{};
    double score{};
};

double evidence_weight(const tracking::Candidate& value) {
    return std::min(std::max(value.margin,0.0)/std::max(value.control_score,0.02),16.0);
}

double circular_residual(double value,double prediction,double spacing) {
    double result=std::fmod(value-prediction+spacing/2.0,spacing);
    if(result<0.0) result+=spacing;
    return result-spacing/2.0;
}

bool tagged_digest(const std::string& value) {
    if(value.size()!=71 || value.compare(0,7,"sha256:")!=0) return false;
    return std::all_of(value.begin()+7,value.end(),[](char c) {
        return (c>='0'&&c<='9')||(c>='a'&&c<='f');
    });
}

void validate(const std::vector<tracking::Candidate>& candidates,const Config& config) {
    const std::array<double,12> numbers{config.canonical_rf_hz,config.alias_spacing_hz,
        config.minimum_rate_hz_per_s,config.maximum_rate_hz_per_s,
        config.maximum_acceleration_hz_per_s2,config.residual_gate_hz,
        config.measurement_uncertainty_hz,config.maximum_gap_s,
        config.maximum_source_group_span_s,
        config.minimum_span_s,config.minimum_point_weight,config.state_window_s};
    if(candidates.empty() || candidates.size()>config.maximum_input_points ||
       std::any_of(numbers.begin(),numbers.end(),[](double v){return !std::isfinite(v);}) ||
       config.canonical_rf_hz<=0 || config.alias_spacing_hz<=0 ||
       config.minimum_rate_hz_per_s>=config.maximum_rate_hz_per_s ||
       config.maximum_acceleration_hz_per_s2<0 || config.residual_gate_hz<=0 ||
       config.measurement_uncertainty_hz<=0 || config.maximum_gap_s<=0 ||
       config.maximum_source_group_span_s<=0 ||
       config.minimum_span_s<=0 || config.minimum_point_weight<=0 ||
       config.minimum_support<2 || config.state_window_s<=0 || config.state_window<2 ||
       !config.maximum_seeds_per_lane || !config.ambiguity_branches ||
       config.ambiguity_branches>4 || !config.ambiguity_beam ||
       config.ambiguity_beam>16 || !config.maximum_hypotheses_per_lane ||
       config.maximum_hypotheses_per_lane>64 ||
       !config.maximum_candidates_per_source_group)
        throw std::invalid_argument("invalid curvature tracking config");
    std::set<std::string> ids;
    std::map<std::string,std::tuple<int,int,std::string,double>> sources;
    std::map<std::string,std::pair<std::int64_t,std::int64_t>> source_times;
    std::map<std::string,std::size_t> source_counts;
    for(const auto& candidate:candidates) {
        const std::array<double,5> values{candidate.actual_rf_hz,candidate.measured_cfo_hz,
            candidate.exact_score,candidate.control_score,candidate.margin};
        if(!tagged_digest(candidate.candidate_id)||!tagged_digest(candidate.source_group_id)||
           !ids.insert(candidate.candidate_id).second ||
           std::any_of(values.begin(),values.end(),[](double v){return !std::isfinite(v);}) ||
           candidate.receiver_id<0 || candidate.channel<1 ||
           (candidate.edge!="lower"&&candidate.edge!="upper") || candidate.actual_rf_hz<=0 ||
           candidate.support_start_utc_ns<=0 ||
           candidate.support_start_utc_ns>candidate.support_center_utc_ns ||
           candidate.support_center_utc_ns>=candidate.support_end_utc_ns || candidate.margin<=0)
            throw std::invalid_argument("invalid curvature tracking candidate");
        const auto authority=std::make_tuple(candidate.receiver_id,candidate.channel,
            candidate.edge,candidate.actual_rf_hz);
        auto [position,inserted]=sources.emplace(candidate.source_group_id,authority);
        if(!inserted && position->second!=authority)
            throw std::invalid_argument("source group changes lane or time");
        if(++source_counts[candidate.source_group_id]>
           config.maximum_candidates_per_source_group)
            throw std::invalid_argument("source group exceeds candidate bound");
        auto [times,time_inserted]=source_times.emplace(candidate.source_group_id,
            std::make_pair(candidate.support_center_utc_ns,candidate.support_center_utc_ns));
        if(!time_inserted) {
            times->second.first=std::min(times->second.first,candidate.support_center_utc_ns);
            times->second.second=std::max(times->second.second,candidate.support_center_utc_ns);
        }
    }
    for(const auto& [source,times]:source_times) {
        (void)source;
        if((times.second-times.first)/kNsPerSecond>config.maximum_source_group_span_s)
            throw std::invalid_argument("source group time span exceeds bound");
    }
}

bool solve3(double matrix[3][4],double output[3]) {
    for(unsigned column=0;column<3;++column) {
        unsigned pivot=column;
        for(unsigned row=column+1;row<3;++row)
            if(std::abs(matrix[row][column])>std::abs(matrix[pivot][column])) pivot=row;
        if(std::abs(matrix[pivot][column])<1e-12) return false;
        if(pivot!=column) for(unsigned j=column;j<4;++j)
            std::swap(matrix[pivot][j],matrix[column][j]);
        const double divisor=matrix[column][column];
        for(unsigned j=column;j<4;++j) matrix[column][j]/=divisor;
        for(unsigned row=0;row<3;++row) if(row!=column) {
            const double factor=matrix[row][column];
            for(unsigned j=column;j<4;++j)
                matrix[row][j]-=factor*matrix[column][j];
        }
    }
    for(unsigned i=0;i<3;++i) output[i]=matrix[i][3];
    return true;
}

State fit_local(const Hypothesis& hypothesis,const std::vector<Point>& points,
                const Config& config) {
    const auto& indexes=hypothesis.state_indexes.empty()
        ? hypothesis.indexes:hypothesis.state_indexes;
    const auto& frequencies=hypothesis.state_frequencies.empty()
        ? hypothesis.frequencies:hypothesis.state_frequencies;
    const double origin=points[indexes.back()].time_s;
    std::size_t begin=indexes.size();
    while(begin>0 && indexes.size()-begin<config.state_window &&
          std::abs(points[indexes[begin-1]].time_s-origin)<=
              config.state_window_s) --begin;
    const std::size_t count=indexes.size()-begin;
    double s0=0,s1=0,s2=0,s3=0,s4=0,y0=0,y1=0,y2=0;
    for(std::size_t i=begin;i<indexes.size();++i) {
        const double x=points[indexes[i]].time_s-origin;
        const double y=frequencies[i];
        const double w=points[indexes[i]].weight;
        const double x2=x*x;
        s0+=w;s1+=w*x;s2+=w*x2;s3+=w*x2*x;s4+=w*x2*x2;
        y0+=w*y;y1+=w*x*y;y2+=w*x2*y;
    }
    double coefficients[3]{};
    double matrix[3][4]{{s0,s1,s2,y0},{s1,s2,s3,y1},{s2,s3,s4,y2}};
    const double local_span=std::abs(points[indexes[begin]].time_s-origin);
    bool quadratic=count>=6 && local_span>=4.0 &&
        config.maximum_acceleration_hz_per_s2>0 &&
        solve3(matrix,coefficients);
    if(quadratic) {
        const double acceleration=2.0*coefficients[2];
        if(std::abs(acceleration)>config.maximum_acceleration_hz_per_s2) {
            // Treat excess curvature as measurement noise and solve the
            // remaining frequency/rate terms at the nearest admissible
            // physical acceleration.
            coefficients[2]=std::copysign(
                config.maximum_acceleration_hz_per_s2/2.0,acceleration);
            double adjusted_y0=0,adjusted_y1=0;
            for(std::size_t i=begin;i<indexes.size();++i) {
                const double x=points[indexes[i]].time_s-origin;
                const double w=points[indexes[i]].weight;
                const double adjusted=frequencies[i]-coefficients[2]*x*x;
                adjusted_y0+=w*adjusted;
                adjusted_y1+=w*x*adjusted;
            }
            const double denominator=s0*s2-s1*s1;
            if(std::abs(denominator)<1e-12) quadratic=false;
            else {
                coefficients[0]=(adjusted_y0*s2-adjusted_y1*s1)/denominator;
                coefficients[1]=(adjusted_y1*s0-adjusted_y0*s1)/denominator;
            }
        }
    }
    if(!quadratic) {
        const double denominator=s0*s2-s1*s1;
        if(std::abs(denominator)<1e-12) throw std::runtime_error("singular local state");
        coefficients[0]=(y0*s2-y1*s1)/denominator;
        coefficients[1]=(y1*s0-y0*s1)/denominator;
        coefficients[2]=0.0;
    }
    double weighted_squared=0;
    for(std::size_t i=begin;i<indexes.size();++i) {
        const double x=points[indexes[i]].time_s-origin;
        const double predicted=coefficients[0]+coefficients[1]*x+coefficients[2]*x*x;
        const double residual=frequencies[i]-predicted;
        weighted_squared+=points[indexes[i]].weight*residual*residual;
    }
    const double rms=std::sqrt(weighted_squared/std::max(s0,1e-12));
    const double span=local_span;
    return {origin,coefficients[0],coefficients[1],2.0*coefficients[2],
        std::max(config.measurement_uncertainty_hz,rms),
        std::max(config.measurement_uncertainty_hz/std::max(span,1.0),
                 rms/std::max(span,1.0)),rms};
}

bool better_hypothesis(const Hypothesis& left,const Hypothesis& right,
                       const std::vector<Point>& points) {
    const double left_span=std::abs(points[left.indexes.back()].time_s-
                                    points[left.indexes.front()].time_s);
    const double right_span=std::abs(points[right.indexes.back()].time_s-
                                     points[right.indexes.front()].time_s);
    return std::make_tuple(left.indexes.size(),left_span,left.score,-left.state.rms_hz)>
           std::make_tuple(right.indexes.size(),right_span,right.score,-right.state.rms_hz);
}

std::vector<Hypothesis> trace(Hypothesis seed,const std::vector<Group>& groups,
                              const std::vector<Point>& points,std::ptrdiff_t first_group,
                              int direction,double spacing,const Config& config,
                              Stats& stats) {
    std::vector<Hypothesis> beam{std::move(seed)};
    for(std::ptrdiff_t group_index=first_group;
        group_index>=0 && group_index<static_cast<std::ptrdiff_t>(groups.size());
        group_index+=direction) {
        std::vector<Hypothesis> next;
        for(const Hypothesis& hypothesis:beam) {
            const Group& group=groups[static_cast<std::size_t>(group_index)];
            if((direction>0 && group.minimum_time_s-hypothesis.state.time_s>
                                   config.maximum_gap_s) ||
               (direction<0 && hypothesis.state.time_s-group.maximum_time_s>
                                   config.maximum_gap_s)) continue;
            struct Association { std::size_t index;double frequency;double residual;double merit; };
            std::vector<Association> associations;
            for(std::size_t index:group.points) {
                ++stats.states_evaluated;
                const double dt=points[index].time_s-hypothesis.state.time_s;
                if(std::abs(dt)>config.maximum_gap_s || dt*direction<=0.0) continue;
                const double predicted=hypothesis.state.frequency_hz+
                    hypothesis.state.rate_hz_per_s*dt+
                    .5*hypothesis.state.acceleration_hz_per_s2*dt*dt;
                const double uncertainty=hypothesis.state.frequency_uncertainty_hz+
                    std::abs(dt)*hypothesis.state.rate_uncertainty_hz_per_s+
                    .5*config.maximum_acceleration_hz_per_s2*dt*dt;
                const double frequency=points[index].raw_hz+
                    std::nearbyint((predicted-points[index].raw_hz)/spacing)*spacing;
                const double residual=frequency-predicted;
                const double gate=std::min(config.residual_gate_hz+uncertainty,
                                           2.0*config.residual_gate_hz);
                if(std::abs(residual)>gate) continue;
                associations.push_back({index,frequency,residual,
                    points[index].weight-residual*residual/(gate*gate)});
            }
            std::sort(associations.begin(),associations.end(),[&](const Association& a,
                                                                   const Association& b) {
                if(a.merit!=b.merit) return a.merit>b.merit;
                if(std::abs(a.residual)!=std::abs(b.residual))
                    return std::abs(a.residual)<std::abs(b.residual);
                return points[a.index].source->candidate_id<
                       points[b.index].source->candidate_id;
            });
            const std::size_t branches=std::min(config.ambiguity_branches,associations.size());
            for(std::size_t branch=0;branch<branches;++branch) {
                Hypothesis candidate=hypothesis;
                candidate.indexes.push_back(associations[branch].index);
                candidate.frequencies.push_back(associations[branch].frequency);
                candidate.state_indexes.push_back(associations[branch].index);
                candidate.state_frequencies.push_back(associations[branch].frequency);
                candidate.score+=associations[branch].merit;
                try { candidate.state=fit_local(candidate,points,config); }
                catch(const std::runtime_error&) { continue; }
                if(candidate.state.rate_hz_per_s<config.minimum_rate_hz_per_s ||
                   candidate.state.rate_hz_per_s>config.maximum_rate_hz_per_s ||
                   candidate.state.rms_hz>config.residual_gate_hz ||
                   std::abs(candidate.state.acceleration_hz_per_s2)>
                       config.maximum_acceleration_hz_per_s2) continue;
                candidate.maximum_abs_acceleration=std::max(candidate.maximum_abs_acceleration,
                    std::abs(candidate.state.acceleration_hz_per_s2));
                next.push_back(std::move(candidate));
            }
            // A miss remains possible even when a crossing offers a tempting
            // association; the hard time gap bounds how long it can survive.
            next.push_back(hypothesis);
        }
        if(next.empty()) break;
        std::sort(next.begin(),next.end(),[&](const Hypothesis& a,const Hypothesis& b) {
            return better_hypothesis(a,b,points);
        });
        if(next.size()>config.ambiguity_beam) next.resize(config.ambiguity_beam);
        beam=std::move(next);
    }
    return beam;
}

std::string membership_key(const Hypothesis& hypothesis,const std::vector<Point>& points) {
    std::vector<std::string> ids;
    ids.reserve(hypothesis.indexes.size());
    for(std::size_t index:hypothesis.indexes) ids.push_back(points[index].source->candidate_id);
    std::sort(ids.begin(),ids.end());
    std::string result;
    for(const auto& id:ids) {result+=id;result.push_back('\n');}
    return result;
}

bool near_membership(const Hypothesis& left,const Hypothesis& right,
                     const std::vector<Point>& points,double gate,double spacing) {
    std::map<std::string,double> frequencies;
    for(std::size_t i=0;i<left.indexes.size();++i)
        frequencies.emplace(points[left.indexes[i]].source->source_group_id,left.frequencies[i]);
    std::size_t shared=0;
    for(std::size_t i=0;i<right.indexes.size();++i) {
        auto found=frequencies.find(points[right.indexes[i]].source->source_group_id);
        if(found!=frequencies.end() && std::abs(circular_residual(
           found->second,right.frequencies[i],spacing))<=gate) ++shared;
    }
    return shared*5>=4*std::min(left.indexes.size(),right.indexes.size());
}

Track finish(const LaneKey& lane,Hypothesis hypothesis,const std::vector<Point>& points,
             std::int64_t reference,double spacing,std::size_t ordinal) {
    std::vector<std::size_t> order(hypothesis.indexes.size());
    for(std::size_t i=0;i<order.size();++i) order[i]=i;
    std::sort(order.begin(),order.end(),[&](std::size_t a,std::size_t b) {
        return std::tie(points[hypothesis.indexes[a]].time_s,
                        points[hypothesis.indexes[a]].source->candidate_id)<
               std::tie(points[hypothesis.indexes[b]].time_s,
                        points[hypothesis.indexes[b]].source->candidate_id);
    });
    double sw=0,sx=0,sy=0,sxx=0,sxy=0;
    for(std::size_t position:order) {
        const Point& point=points[hypothesis.indexes[position]];
        const double y=hypothesis.frequencies[position];
        sw+=point.weight;sx+=point.weight*point.time_s;sy+=point.weight*y;
        sxx+=point.weight*point.time_s*point.time_s;sxy+=point.weight*point.time_s*y;
    }
    const double denominator=sw*sxx-sx*sx;
    const double slope=(sw*sxy-sx*sy)/denominator;
    const double intercept=(sy-slope*sx)/sw;
    double weighted_squared=0,maximum=0;
    tracking::Track summary;
    summary.segment_id="research-curvature-segment-"+std::to_string(ordinal);
    summary.tracklet_id="research-curvature-track-"+std::to_string(ordinal);
    summary.lane={lane.channel,lane.edge,lane.receiver_id,lane.actual_rf_hz};
    summary.reference_utc_ns=reference;
    summary.normalized_rate_hz_per_s=slope;
    summary.normalized_intercept_hz=intercept;
    summary.start_utc_ns=std::numeric_limits<std::int64_t>::max();
    summary.end_utc_ns=std::numeric_limits<std::int64_t>::min();
    for(std::size_t position:order) {
        const Point& point=points[hypothesis.indexes[position]];
        const double frequency=hypothesis.frequencies[position];
        const double residual=frequency-(slope*point.time_s+intercept);
        weighted_squared+=point.weight*residual*residual;
        maximum=std::max(maximum,std::abs(residual));
        const int alias=static_cast<int>(std::nearbyint((point.raw_hz-frequency)/spacing));
        summary.points.push_back({point.source->candidate_id,point.source->source_group_id,
            alias,point.raw_hz,frequency});
        summary.weighted_support+=point.weight;
        summary.start_utc_ns=std::min(summary.start_utc_ns,point.source->support_start_utc_ns);
        summary.end_utc_ns=std::max(summary.end_utc_ns,point.source->support_end_utc_ns);
    }
    summary.residual_rms_hz=std::sqrt(weighted_squared/std::max(sw,1e-12));
    summary.residual_max_hz=maximum;
    return {std::move(summary),hypothesis.maximum_abs_acceleration,hypothesis.score};
}

}  // namespace

Result reconstruct_impl(const std::vector<tracking::Candidate>& candidates,
                        const std::vector<SeedTrack>* external_seeds,
                        bool retain_original_alternatives,const Config& config) {
    validate(candidates,config);
    std::map<LaneKey,std::vector<const tracking::Candidate*>> lanes;
    for(const auto& candidate:candidates)
        lanes[{candidate.channel,candidate.edge,candidate.receiver_id,candidate.actual_rf_hz}]
            .push_back(&candidate);
    Result result;
    result.input_candidate_count=candidates.size();
    result.stats.lanes=lanes.size();
    std::set<std::string> used;
    for(const auto& [lane,rows]:lanes) {
        const std::int64_t reference=std::min_element(rows.begin(),rows.end(),
            [](const auto* a,const auto* b) {
                return a->support_center_utc_ns<b->support_center_utc_ns;
            })[0]->support_center_utc_ns;
        const double scale=config.canonical_rf_hz/lane.actual_rf_hz;
        const double spacing=config.alias_spacing_hz*scale;
        std::map<std::string,std::vector<const tracking::Candidate*>> source_rows;
        for(const auto* row:rows) source_rows[row->source_group_id].push_back(row);
        std::vector<Point> points;
        std::vector<Group> groups;
        for(auto& [source,items]:source_rows) {
            std::sort(items.begin(),items.end(),[](const auto* a,const auto* b) {
                return std::tie(a->measured_cfo_hz,a->candidate_id)<
                       std::tie(b->measured_cfo_hz,b->candidate_id);
            });
            const auto extrema=std::minmax_element(items.begin(),items.end(),
                [](const auto* a,const auto* b) {
                    return a->support_center_utc_ns<b->support_center_utc_ns;
                });
            const double minimum_time=((*extrema.first)->support_center_utc_ns-reference)/
                                      kNsPerSecond;
            const double maximum_time=((*extrema.second)->support_center_utc_ns-reference)/
                                      kNsPerSecond;
            Group group{source,(minimum_time+maximum_time)/2.0,
                        minimum_time,maximum_time,{}};
            // Exact scientific duplicates cannot create distinct associations.
            for(const auto* item:items) {
                const double raw=item->measured_cfo_hz*scale;
                if(external_seeds==nullptr && !group.points.empty() &&
                   points[group.points.back()].raw_hz==raw) {
                    const Point& prior=points[group.points.back()];
                    const double weight=evidence_weight(*item);
                    if(weight>prior.weight || (weight==prior.weight &&
                       item->candidate_id<prior.source->candidate_id))
                        points[group.points.back()]={item,
                            (item->support_center_utc_ns-reference)/kNsPerSecond,raw,weight};
                    continue;
                }
                group.points.push_back(points.size());
                points.push_back({item,(item->support_center_utc_ns-reference)/kNsPerSecond,
                                  raw,evidence_weight(*item)});
            }
            groups.push_back(std::move(group));
        }
        std::sort(groups.begin(),groups.end(),[](const Group& a,const Group& b) {
            return std::tie(a.time_s,a.source_id)<std::tie(b.time_s,b.source_id);
        });
        result.stats.source_groups+=groups.size();
        std::vector<Hypothesis> generated;
        std::vector<Hypothesis> originals;
        if(external_seeds==nullptr) {
        std::vector<Seed> seeds;
        for(std::size_t first=0;first+1<groups.size();++first) {
            std::size_t second=first+1;
            while(second<groups.size() && groups[second].time_s==groups[first].time_s) ++second;
            if(second==groups.size()) break;
            for(std::size_t left:groups[first].points)
                for(std::size_t right:groups[second].points) {
                    ++result.stats.seeds_considered;
                    const double dt=points[right].time_s-points[left].time_s;
                    if(dt<=0.0 || dt>config.maximum_gap_s) continue;
                    const double lifted=points[right].raw_hz+
                        std::nearbyint((points[left].raw_hz-points[right].raw_hz)/spacing)*spacing;
                    const double rate=(lifted-points[left].raw_hz)/dt;
                    if(rate<config.minimum_rate_hz_per_s || rate>config.maximum_rate_hz_per_s)
                        continue;
                    seeds.push_back({first,second,left,right,points[left].raw_hz,lifted,rate,
                        points[left].weight+points[right].weight});
                }
        }
        std::sort(seeds.begin(),seeds.end(),[](const Seed& a,const Seed& b) {
            return std::tie(a.score,a.first_group,a.first_point,a.second_point)>
                   std::tie(b.score,b.first_group,b.first_point,b.second_point);
        });
        if(seeds.size()>config.maximum_seeds_per_lane)
            seeds.resize(config.maximum_seeds_per_lane);
        result.stats.seeds_retained+=seeds.size();
        for(const Seed& seed:seeds) {
            Hypothesis forward;
            forward.indexes={seed.first_point,seed.second_point};
            forward.frequencies={seed.first_frequency,seed.second_frequency};
            forward.state_indexes=forward.indexes;
            forward.state_frequencies=forward.frequencies;
            forward.score=seed.score;
            forward.state=fit_local(forward,points,config);
            auto forwards=trace(forward,groups,points,
                static_cast<std::ptrdiff_t>(seed.second_group)+1,1,spacing,config,result.stats);
            Hypothesis backward;
            backward.indexes={seed.second_point,seed.first_point};
            backward.frequencies={seed.second_frequency,seed.first_frequency};
            backward.state_indexes=backward.indexes;
            backward.state_frequencies=backward.frequencies;
            backward.score=seed.score;
            backward.state=fit_local(backward,points,config);
            auto backwards=trace(backward,groups,points,
                static_cast<std::ptrdiff_t>(seed.first_group)-1,-1,spacing,config,result.stats);
            const std::size_t forward_count=std::min<std::size_t>(2,forwards.size());
            const std::size_t backward_count=std::min<std::size_t>(2,backwards.size());
            for(std::size_t fi=0;fi<forward_count;++fi)
                for(std::size_t bi=0;bi<backward_count;++bi) {
                    Hypothesis merged=backwards[bi];
                    std::reverse(merged.indexes.begin(),merged.indexes.end());
                    std::reverse(merged.frequencies.begin(),merged.frequencies.end());
                    for(std::size_t j=2;j<forwards[fi].indexes.size();++j) {
                        merged.indexes.push_back(forwards[fi].indexes[j]);
                        merged.frequencies.push_back(forwards[fi].frequencies[j]);
                    }
                    merged.score=forwards[fi].score+backwards[bi].score-seed.score;
                    merged.maximum_abs_acceleration=std::max(forwards[fi].maximum_abs_acceleration,
                        backwards[bi].maximum_abs_acceleration);
                    if(merged.indexes.size()<config.minimum_support) continue;
                    const double span=points[merged.indexes.back()].time_s-
                                      points[merged.indexes.front()].time_s;
                    if(span<config.minimum_span_s) continue;
                    merged.state_indexes=merged.indexes;
                    merged.state_frequencies=merged.frequencies;
                    merged.state=fit_local(merged,points,config);
                    generated.push_back(std::move(merged));
                }
        }
        } else {
            std::map<std::string,std::size_t> point_by_id;
            std::map<std::string,std::size_t> group_by_source;
            for(std::size_t index=0;index<points.size();++index)
                point_by_id.emplace(points[index].source->candidate_id,index);
            for(std::size_t index=0;index<groups.size();++index)
                group_by_source.emplace(groups[index].source_id,index);
            for(const SeedTrack& seed:*external_seeds) {
                if(seed.lane.channel!=lane.channel || seed.lane.edge!=lane.edge ||
                   seed.lane.receiver_id!=lane.receiver_id ||
                   seed.lane.actual_rf_hz!=lane.actual_rf_hz) continue;
                ++result.stats.external_seed_tracks;
                if(seed.points.size()<2 || seed.points.size()>config.state_window*4)
                    throw std::invalid_argument("external seed membership bound");
                Hypothesis original;
                std::set<std::string> source_membership;
                for(const SeedPoint& member:seed.points) {
                    auto found=point_by_id.find(member.candidate_id);
                    if(found==point_by_id.end())
                        throw std::invalid_argument("external seed candidate is absent");
                    const std::size_t index=found->second;
                    if(!std::isfinite(member.normalized_dealiased_cfo_hz) ||
                       std::abs(circular_residual(points[index].raw_hz,
                           member.normalized_dealiased_cfo_hz,spacing))>1e-6)
                        throw std::invalid_argument("external seed alias is inconsistent");
                    if(!source_membership.insert(
                       points[index].source->source_group_id).second)
                        throw std::invalid_argument("external seed repeats a source group");
                    original.indexes.push_back(index);
                    original.frequencies.push_back(member.normalized_dealiased_cfo_hz);
                    original.score+=points[index].weight;
                }
                std::vector<std::size_t> order(original.indexes.size());
                for(std::size_t i=0;i<order.size();++i) order[i]=i;
                std::sort(order.begin(),order.end(),[&](std::size_t a,std::size_t b) {
                    return std::tie(points[original.indexes[a]].time_s,
                                    points[original.indexes[a]].source->candidate_id)<
                           std::tie(points[original.indexes[b]].time_s,
                                    points[original.indexes[b]].source->candidate_id);
                });
                Hypothesis ordered;
                ordered.score=original.score;
                for(std::size_t position:order) {
                    ordered.indexes.push_back(original.indexes[position]);
                    ordered.frequencies.push_back(original.frequencies[position]);
                }
                original=std::move(ordered);
                const double seed_span=points[original.indexes.back()].time_s-
                                       points[original.indexes.front()].time_s;
                if(original.indexes.size()<config.minimum_support ||
                   seed_span<config.minimum_span_s)
                    throw std::invalid_argument("external seed does not meet support policy");
                original.state_indexes=original.indexes;
                original.state_frequencies=original.frequencies;
                original.state=fit_local(original,points,config);
                if(retain_original_alternatives) originals.push_back(original);

                const std::size_t middle=original.indexes.size()/2;
                const std::string& middle_source=
                    points[original.indexes[middle]].source->source_group_id;
                const std::size_t middle_group=group_by_source.at(middle_source);
                Hypothesis forward;
                forward.indexes={original.indexes[middle]};
                forward.frequencies={original.frequencies[middle]};
                forward.state_indexes.assign(original.indexes.begin(),
                    original.indexes.begin()+static_cast<std::ptrdiff_t>(middle)+1);
                forward.state_frequencies.assign(original.frequencies.begin(),
                    original.frequencies.begin()+static_cast<std::ptrdiff_t>(middle)+1);
                forward.score=points[original.indexes[middle]].weight;
                forward.state=fit_local(forward,points,config);
                auto forwards=trace(forward,groups,points,
                    static_cast<std::ptrdiff_t>(middle_group)+1,1,spacing,config,result.stats);

                Hypothesis backward;
                backward.indexes={original.indexes[middle]};
                backward.frequencies={original.frequencies[middle]};
                for(std::size_t i=original.indexes.size();i>middle;--i) {
                    backward.state_indexes.push_back(original.indexes[i-1]);
                    backward.state_frequencies.push_back(original.frequencies[i-1]);
                }
                backward.score=points[original.indexes[middle]].weight;
                backward.state=fit_local(backward,points,config);
                auto backwards=trace(backward,groups,points,
                    static_cast<std::ptrdiff_t>(middle_group)-1,-1,spacing,config,result.stats);
                const std::size_t forward_count=std::min<std::size_t>(2,forwards.size());
                const std::size_t backward_count=std::min<std::size_t>(2,backwards.size());
                for(std::size_t fi=0;fi<forward_count;++fi)
                    for(std::size_t bi=0;bi<backward_count;++bi) {
                        Hypothesis merged=backwards[bi];
                        std::reverse(merged.indexes.begin(),merged.indexes.end());
                        std::reverse(merged.frequencies.begin(),merged.frequencies.end());
                        for(std::size_t j=1;j<forwards[fi].indexes.size();++j) {
                            merged.indexes.push_back(forwards[fi].indexes[j]);
                            merged.frequencies.push_back(forwards[fi].frequencies[j]);
                        }
                        merged.score=forwards[fi].score+backwards[bi].score-
                                     points[original.indexes[middle]].weight;
                        merged.maximum_abs_acceleration=std::max(
                            forwards[fi].maximum_abs_acceleration,
                            backwards[bi].maximum_abs_acceleration);
                        if(merged.indexes.size()<config.minimum_support) continue;
                        const double span=points[merged.indexes.back()].time_s-
                                          points[merged.indexes.front()].time_s;
                        if(span<config.minimum_span_s) continue;
                        merged.state_indexes=merged.indexes;
                        merged.state_frequencies=merged.frequencies;
                        merged.state=fit_local(merged,points,config);
                        generated.push_back(std::move(merged));
                    }
            }
        }
        std::map<std::string,Hypothesis> exact;
        for(Hypothesis& hypothesis:generated) {
            const std::string key=membership_key(hypothesis,points);
            auto found=exact.find(key);
            if(found==exact.end()) exact.emplace(key,std::move(hypothesis));
            else {
                ++result.stats.exact_hypotheses_consolidated;
                if(better_hypothesis(hypothesis,found->second,points))
                    found->second=std::move(hypothesis);
            }
        }
        generated.clear();
        for(auto& entry:exact) generated.push_back(std::move(entry.second));
        std::sort(generated.begin(),generated.end(),[&](const Hypothesis& a,const Hypothesis& b) {
            return better_hypothesis(a,b,points);
        });
        std::vector<Hypothesis> retained;
        for(Hypothesis& hypothesis:generated) {
            if(std::any_of(retained.begin(),retained.end(),[&](const Hypothesis& prior) {
                return near_membership(hypothesis,prior,points,config.residual_gate_hz,spacing);
            })) {
                ++result.stats.near_hypotheses_consolidated;
                continue;
            }
            retained.push_back(std::move(hypothesis));
            if(retained.size()==config.maximum_hypotheses_per_lane) break;
        }
        for(Hypothesis& hypothesis:originals) {
            for(std::size_t index:hypothesis.indexes)
                used.insert(points[index].source->candidate_id);
            result.tracks.push_back(finish(lane,std::move(hypothesis),points,reference,spacing,
                result.tracks.size()));
            ++result.stats.retained_original_alternatives;
        }
        for(Hypothesis& hypothesis:retained) {
            for(std::size_t index:hypothesis.indexes)
                used.insert(points[index].source->candidate_id);
            result.tracks.push_back(finish(lane,std::move(hypothesis),points,reference,spacing,
                result.tracks.size()));
        }
    }
    if(external_seeds!=nullptr &&
       result.stats.external_seed_tracks!=external_seeds->size())
        throw std::invalid_argument("external seed lane is absent from input");
    result.used_candidate_count=used.size();
    return result;
}

Result reconstruct(const std::vector<tracking::Candidate>& candidates,const Config& config) {
    return reconstruct_impl(candidates,nullptr,false,config);
}

Result reconstruct_seeded(const std::vector<tracking::Candidate>& candidates,
                          const std::vector<SeedTrack>& seeds,
                          bool retain_original_alternatives,const Config& config) {
    if(seeds.empty() || seeds.size()>config.maximum_seeds_per_lane)
        throw std::invalid_argument("external seed track bound");
    return reconstruct_impl(candidates,&seeds,retain_original_alternatives,config);
}

}  // namespace leo::adaptive::tracking::research::curvature_tracks
