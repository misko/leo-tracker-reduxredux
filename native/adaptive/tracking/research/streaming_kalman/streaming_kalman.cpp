#include "streaming_kalman.hpp"

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

namespace leo::adaptive::tracking::research::streaming_kalman {
namespace {

constexpr double kNs=1e9;

struct LaneKey {
    int receiver{},channel{}; std::string edge; double rf{};
    bool operator<(const LaneKey& x) const {
        return std::tie(receiver,channel,edge,rf)<std::tie(x.receiver,x.channel,x.edge,x.rf);
    }
};
struct Point { const tracking::Candidate* source{}; double time{},raw{},weight{}; };
struct Group { std::string id; double time{}; std::vector<std::size_t> points; };
struct Hypothesis {
    double time{},frequency{},rate{},p00{},p01{},p11{};
    double last_detection{},score{},sum_sq{};
    std::vector<std::size_t> points; std::vector<double> frequencies;
};

bool digest(const std::string& s) {
    return s.size()==71 && s.compare(0,7,"sha256:")==0 &&
        s.find_first_not_of("0123456789abcdef",7)==std::string::npos;
}
double weight(const tracking::Candidate& c) {
    return std::min(std::max(c.margin,0.0)/std::max(c.control_score,0.02),16.0);
}
void validate(const std::vector<tracking::Candidate>& values,const Config& c) {
    const std::array<double,10> n{c.canonical_rf_hz,c.alias_spacing_hz,
        c.measurement_sigma_hz,c.acceleration_sigma_hz_per_s2,c.innovation_gate_hz,
        c.minimum_rate_hz_per_s,c.maximum_rate_hz_per_s,c.maximum_gap_s,
        c.minimum_span_s,c.minimum_point_weight};
    if(values.empty() || values.size()>c.maximum_input_points ||
       std::any_of(n.begin(),n.end(),[](double x){return !std::isfinite(x);}) ||
       c.canonical_rf_hz<=0 || c.alias_spacing_hz<=0 || c.measurement_sigma_hz<=0 ||
       c.acceleration_sigma_hz_per_s2<0 || c.innovation_gate_hz<=0 ||
       c.minimum_rate_hz_per_s>=c.maximum_rate_hz_per_s || c.maximum_gap_s<=0 ||
       c.minimum_span_s<=0 || c.minimum_support<2 || c.minimum_point_weight<=0 ||
       !c.association_branches || c.association_branches>4 ||
       !c.maximum_hypotheses_per_lane || c.maximum_hypotheses_per_lane>512 ||
       !c.maximum_output_tracks_per_lane || !c.maximum_candidates_per_source_group)
        throw std::invalid_argument("invalid streaming Kalman configuration");
    std::set<std::string> ids;
    std::map<std::string,std::tuple<int,int,std::string,double>> binding;
    std::map<std::string,std::size_t> counts;
    for(const auto& v:values) {
        const std::array<double,5> x{v.actual_rf_hz,v.measured_cfo_hz,v.exact_score,
            v.control_score,v.margin};
        if(!digest(v.candidate_id)||!digest(v.source_group_id)||!ids.insert(v.candidate_id).second||
           std::any_of(x.begin(),x.end(),[](double z){return !std::isfinite(z);})||
           v.receiver_id<0||v.channel<1||(v.edge!="lower"&&v.edge!="upper")||
           v.actual_rf_hz<=0||v.support_start_utc_ns<=0||
           v.support_start_utc_ns>v.support_center_utc_ns||
           v.support_center_utc_ns>=v.support_end_utc_ns||v.margin<=0)
            throw std::invalid_argument("invalid streaming Kalman candidate");
        auto key=std::make_tuple(v.receiver_id,v.channel,v.edge,v.actual_rf_hz);
        auto inserted=binding.emplace(v.source_group_id,key);
        if((!inserted.second&&inserted.first->second!=key)||
           ++counts[v.source_group_id]>c.maximum_candidates_per_source_group)
            throw std::invalid_argument("invalid streaming Kalman source group");
    }
}

Hypothesis predict(Hypothesis h,double time,const Config& c,Stats& stats) {
    const double dt=time-h.time,q2=c.acceleration_sigma_hz_per_s2*
        c.acceleration_sigma_hz_per_s2;
    h.frequency+=h.rate*dt;
    h.p00+=2*dt*h.p01+dt*dt*h.p11+q2*dt*dt*dt*dt/4;
    h.p01+=dt*h.p11+q2*dt*dt*dt/2;
    h.p11+=q2*dt*dt;
    h.time=time; ++stats.predictions; return h;
}
bool update(Hypothesis& h,std::size_t index,double raw,const std::vector<Point>& points,
            double spacing,const Config& c,Stats& stats) {
    const double z=raw+std::nearbyint((h.frequency-raw)/spacing)*spacing;
    const double residual=z-h.frequency;
    const double variance=h.p00+c.measurement_sigma_hz*c.measurement_sigma_hz;
    const double gate=std::min(c.innovation_gate_hz,std::max(3*c.measurement_sigma_hz,
        4*std::sqrt(variance)));
    if(std::abs(residual)>gate) return false;
    const double k0=h.p00/variance,k1=h.p01/variance;
    const double p00=h.p00,p01=h.p01;
    h.frequency+=k0*residual; h.rate+=k1*residual;
    h.p00=(1-k0)*p00; h.p01=(1-k0)*p01; h.p11-=k1*p01;
    if(h.rate<c.minimum_rate_hz_per_s||h.rate>c.maximum_rate_hz_per_s) return false;
    h.points.push_back(index); h.frequencies.push_back(z); h.last_detection=h.time;
    h.sum_sq+=residual*residual; h.score+=points[index].weight-residual*residual/(gate*gate);
    ++stats.accepted_updates; return true;
}

bool better(const Hypothesis& a,const Hypothesis& b) {
    return std::make_tuple(a.points.size(),a.score,a.last_detection-a.points.size(),
        -std::abs(a.rate)) > std::make_tuple(b.points.size(),b.score,
        b.last_detection-b.points.size(),-std::abs(b.rate));
}

tracking::Track output(const Hypothesis& h,const std::vector<Point>& points,
                       const LaneKey& lane,double spacing) {
    tracking::Track t;
    const double ref=points[h.points.front()].time;
    double sw=0,st=0,sf=0,stt=0,stf=0;
    for(std::size_t i=0;i<h.points.size();++i) {
        const auto& p=points[h.points[i]]; const double x=p.time-ref,w=p.weight,y=h.frequencies[i];
        sw+=w;st+=w*x;sf+=w*y;stt+=w*x*x;stf+=w*x*y;
    }
    const double denominator=sw*stt-st*st;
    const double rate=std::abs(denominator)>1e-12?(sw*stf-st*sf)/denominator:h.rate;
    const double intercept=(sf-rate*st)/sw;
    double sum=0,maximum=0;
    for(std::size_t i=0;i<h.points.size();++i) {
        const auto& p=points[h.points[i]]; const double r=h.frequencies[i]-(intercept+rate*(p.time-ref));
        sum+=r*r;maximum=std::max(maximum,std::abs(r));
        t.points.push_back({p.source->candidate_id,p.source->source_group_id,
            static_cast<int>(std::llround((h.frequencies[i]-p.raw)/
                -spacing)),p.raw,h.frequencies[i]});
    }
    t.segment_id=h.points.front()<h.points.back()?points[h.points.front()].source->candidate_id:
        points[h.points.back()].source->candidate_id;
    t.tracklet_id=points[h.points.back()].source->candidate_id;
    t.lane={lane.channel,lane.edge,lane.receiver,lane.rf};
    t.start_utc_ns=points[h.points.front()].source->support_start_utc_ns;
    t.end_utc_ns=points[h.points.front()].source->support_end_utc_ns;
    for(auto index:h.points) {
        t.start_utc_ns=std::min(t.start_utc_ns,points[index].source->support_start_utc_ns);
        t.end_utc_ns=std::max(t.end_utc_ns,points[index].source->support_end_utc_ns);
    }
    t.reference_utc_ns=points[h.points.front()].source->support_center_utc_ns;
    t.normalized_rate_hz_per_s=rate;
    t.normalized_intercept_hz=intercept;t.residual_rms_hz=std::sqrt(sum/h.points.size());
    t.residual_max_hz=maximum;t.weighted_support=sw; return t;
}

} // namespace

Result reconstruct(const std::vector<tracking::Candidate>& candidates,const Config& c) {
    validate(candidates,c); Result result; result.input_candidate_count=candidates.size();
    std::map<LaneKey,std::vector<const tracking::Candidate*>> lanes;
    for(const auto& v:candidates) if(weight(v)>=c.minimum_point_weight)
        lanes[{v.receiver_id,v.channel,v.edge,v.actual_rf_hz}].push_back(&v);
    result.stats.lanes=lanes.size();
    std::set<std::string> used;
    for(const auto& [lane,input]:lanes) {
        const auto origin=(*std::min_element(input.begin(),input.end(),[](auto a,auto b){
            return a->support_center_utc_ns<b->support_center_utc_ns;}))->support_center_utc_ns;
        std::vector<Point> points; std::map<std::string,std::vector<std::size_t>> by_group;
        const double scale=c.canonical_rf_hz/lane.rf;
        const double spacing=c.alias_spacing_hz*scale;
        for(auto source:input) { points.push_back({source,(source->support_center_utc_ns-origin)/kNs,
            source->measured_cfo_hz*scale,weight(*source)});by_group[source->source_group_id].push_back(points.size()-1); }
        std::vector<Group> groups;
        for(auto& [id,indexes]:by_group) { double time=0;for(auto i:indexes)time+=points[i].time;
            groups.push_back({id,time/indexes.size(),std::move(indexes)}); }
        std::sort(groups.begin(),groups.end(),[](const Group& a,const Group& b){
            return std::tie(a.time,a.id)<std::tie(b.time,b.id);});
        result.stats.source_groups+=groups.size(); std::vector<Hypothesis> bank,finished;
        for(std::size_t gi=0;gi<groups.size();++gi) {
            const auto& group=groups[gi]; std::vector<Hypothesis> next;
            for(const auto& old:bank) {
                if(group.time-old.last_detection>c.maximum_gap_s) { finished.push_back(old);continue; }
                struct Choice { std::size_t index;double residual;Hypothesis predicted; };
                std::vector<Choice> choices;
                for(auto index:group.points) { const double raw=points[index].raw;
                    auto predicted=predict(old,points[index].time,c,result.stats);
                    const double z=raw+std::nearbyint((predicted.frequency-raw)/spacing)*spacing;
                    choices.push_back({index,std::abs(z-predicted.frequency),std::move(predicted)}); }
                std::sort(choices.begin(),choices.end(),[](auto a,auto b){return a.residual<b.residual;});
                for(std::size_t k=0;k<std::min(c.association_branches,choices.size());++k) {
                    auto branch=choices[k].predicted;if(update(branch,choices[k].index,
                        points[choices[k].index].raw,points,spacing,c,result.stats))
                        next.push_back(std::move(branch));
                }
                Hypothesis base=predict(old,group.time,c,result.stats);
                base.score-=0.25;next.push_back(std::move(base));++result.stats.missed_detection_branches;
            }
            // Rolling pair births use every recent source group; no global seed ranking cap.
            for(std::size_t pj=gi;pj-->0;) {
                const double group_dt=group.time-groups[pj].time;
                if(group_dt>c.maximum_gap_s) break;
                for(auto a:groups[pj].points) for(auto b:group.points) {
                    const double dt=points[b].time-points[a].time;if(dt<=0||dt>c.maximum_gap_s)continue;
                    const double delta=points[b].raw-points[a].raw;
                    const int low=static_cast<int>(std::ceil((c.minimum_rate_hz_per_s*dt-delta)/spacing));
                    const int high=static_cast<int>(std::floor((c.maximum_rate_hz_per_s*dt-delta)/spacing));
                    for(int alias=low;alias<=high;++alias) {
                        const double second=points[b].raw+alias*spacing;
                        Hypothesis h{points[b].time,second,(second-points[a].raw)/dt,
                            c.measurement_sigma_hz*c.measurement_sigma_hz,0,
                            4*c.measurement_sigma_hz*c.measurement_sigma_hz/(dt*dt),group.time,
                            points[a].weight+points[b].weight,0,{a,b},{points[a].raw,second}};
                        next.push_back(std::move(h));++result.stats.rolling_births;
                    }
                }
            }
            std::vector<Hypothesis> established,births;
            for(auto& h:next)(h.points.size()>2?established:births).push_back(std::move(h));
            std::sort(established.begin(),established.end(),better);std::sort(births.begin(),births.end(),better);
            const std::size_t birth_slots=std::min(births.size(),c.maximum_hypotheses_per_lane/4);
            const std::size_t established_slots=std::min(established.size(),
                c.maximum_hypotheses_per_lane-birth_slots);
            bank.clear();
            bank.reserve(established_slots+birth_slots);
            for(std::size_t i=0;i<established_slots;++i)bank.push_back(std::move(established[i]));
            for(std::size_t i=0;i<birth_slots;++i)bank.push_back(std::move(births[i]));
            result.stats.peak_hypotheses=std::max(result.stats.peak_hypotheses,bank.size());
            std::sort(finished.begin(),finished.end(),better);
            const std::size_t finished_bound=4*c.maximum_output_tracks_per_lane;
            if(finished.size()>finished_bound)finished.resize(finished_bound);
        }
        finished.insert(finished.end(),bank.begin(),bank.end());std::sort(finished.begin(),finished.end(),better);
        std::set<std::vector<std::size_t>> memberships;std::size_t emitted=0;
        for(const auto& h:finished) {
            if(emitted>=c.maximum_output_tracks_per_lane||h.points.size()<c.minimum_support||
               points[h.points.back()].time-points[h.points.front()].time<c.minimum_span_s||
               !memberships.insert(h.points).second) continue;
            auto track=output(h,points,lane,spacing);for(const auto& p:track.points)used.insert(p.candidate_id);
            result.tracks.push_back(std::move(track));++emitted;
        }
    }
    result.used_candidate_count=used.size();return result;
}

}  // namespace leo::adaptive::tracking::research::streaming_kalman
