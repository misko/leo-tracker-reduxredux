#include "matcher.hpp"
#include "detail.hpp"
#include <chrono>
#include <memory>
#include <stdexcept>

namespace leo::adaptive::location::doppler_match {
namespace {
using namespace detail;
using Clock=std::chrono::steady_clock;
using Context=std::unique_ptr<leo_orbit_context,decltype(&leo_orbit_context_destroy)>;
struct Hypothesis { leo_tle_record tle{}; Point point; double proposal=inf; Fit fit; };
double elapsed(Clock::time_point t) {return std::chrono::duration<double>(Clock::now()-t).count();}
void require(bool condition,const char* message) {if(!condition)throw std::invalid_argument(message);}

void validate(const std::vector<Track>& tracks,const Options& o,Catalogue catalogue) {
    const auto& r=o.region;
    require(o.epoch_utc_ns>0&&std::isfinite(o.carrier_hz)&&o.carrier_hz>0
        &&std::isfinite(r.latitude)&&std::abs(r.latitude)<=90
        &&std::isfinite(r.longitude)&&std::abs(r.longitude)<=180
        &&r.radius>0&&r.radius<=500&&o.time_bound_s>0&&o.time_bound_s<=60
        &&o.fine_step_s>0&&o.fine_step_s<=10&&o.coarse_step_s>=o.fine_step_s&&o.coarse_step_s<=30
        &&o.time_step_s>0&&o.time_step_s<=o.time_bound_s
        &&2*o.time_bound_s/o.time_step_s<=256
        &&o.keep_per_track>0&&o.keep_per_track<=32&&tracks.size()>0&&tracks.size()<=1000,
        "invalid Doppler matcher configuration");
    require(catalogue.read_next&&catalogue.count>0&&catalogue.count<=20000,"invalid catalogue source");
    for(const auto& tr:tracks) {
        const size_t n=tr.times.size(),k=tr.nodes.size();
        require(n>=6&&n<=10000&&tr.measured.size()==n&&tr.training.size()==n
            &&k>=3&&k<=101&&k%2==1&&tr.values.size()==k,"invalid track dimensions");
        size_t training=0;
        for(size_t i=0;i<n;++i) {
            require(std::isfinite(tr.times[i])&&std::isfinite(tr.measured[i])
                &&tr.training[i]<=1&&(!i||tr.times[i]>tr.times[i-1]),"invalid observation");
            training+=tr.training[i];
        }
        require(training>=4&&training<n,"invalid partition");
        for(size_t i=0;i<k;++i)
            require(std::isfinite(tr.nodes[i])&&std::isfinite(tr.values[i])
                &&(!i||tr.nodes[i]>tr.nodes[i-1]),"invalid spline nodes");
        require(tr.nodes.front()>=tr.times.front()&&tr.nodes.back()<=tr.times.back()+1e-9,
            "spline support differs from observed interval");
    }
}
} // namespace

Result match(const std::vector<Track>& tracks,const Options& o,Catalogue catalogue) {
    using namespace detail;
    const auto started=Clock::now();
    validate(tracks,o,catalogue);
    const auto& region=o.region;
    const double tau_bound=o.time_bound_s,coarse_step=o.coarse_step_s,fine_step=o.fine_step_s;
    const size_t keep=o.keep_per_track;
    Result result;
    auto& stats=result.statistics;
    stats.catalogue_records=catalogue.count;
    double first=inf,last=-inf;
    for(const auto& tr:tracks) {
        first=std::min(first,tr.times.front());last=std::max(last,tr.times.back());
        stats.observation_count+=tr.times.size();
    }
    require(last-first<=1200,"observation history exceeds 1200 seconds");
    const double begin=std::floor((first-tau_bound)/coarse_step)*coarse_step-coarse_step;
    const double end=std::ceil((last+tau_bound)/coarse_step)*coarse_step+coarse_step;
    const double coarse_count=std::ceil((end-begin)/coarse_step)+1;
    const double fine_count=std::ceil((end-begin)/fine_step)+1;
    // Validate before converting to integer or allocating. Pathological step
    // sizes must not turn a small workspace into an unbounded allocation.
    require(std::isfinite(begin)&&std::isfinite(end)&&end>begin
        &&coarse_count>=2&&coarse_count<=8192&&fine_count>=2&&fine_count<=8192,
        "orbit grid exceeds 8192 knots per context");
    const auto coarse_n=static_cast<uint32_t>(coarse_count),fine_n=static_cast<uint32_t>(fine_count);
    const long double first_ns=static_cast<long double>(begin)*1e9L;
    const long double last_ns=(static_cast<long double>(begin)+std::max(
        static_cast<long double>(fine_step)*(fine_n-1),
        static_cast<long double>(coarse_step)*(coarse_n-1)))*1e9L;
    const long double min_ns=static_cast<long double>(std::numeric_limits<int64_t>::min())+1;
    const long double max_ns=static_cast<long double>(std::numeric_limits<int64_t>::max())-1;
    require(first_ns>=min_ns&&last_ns<=max_ns
        &&first_ns+o.epoch_utc_ns>=min_ns&&last_ns+o.epoch_utc_ns<=max_ns,
        "orbit times exceed nanosecond epoch range");
    stats.cache_begin_s=begin;stats.cache_end_s=end;
    stats.orbit_state_capacity_bytes=(coarse_n+fine_n)*2*sizeof(leo_orbit_state);
    stats.hypothesis_capacity_bytes=tracks.size()*(keep+1)*sizeof(Hypothesis);
    Context coarse(leo_orbit_context_create(1,coarse_n),&leo_orbit_context_destroy);
    Context fine(leo_orbit_context_create(1,fine_n),&leo_orbit_context_destroy);
    if(!coarse||!fine)throw std::bad_alloc();
    std::vector<std::vector<Hypothesis>> candidates(tracks.size());
    for(auto& c:candidates)c.reserve(keep+1);
    std::vector<Point> sites={{0,0,0}};
    for(int i=0;i<8;++i)sites.push_back({region.radius*std::cos(i*pi/4),region.radius*std::sin(i*pi/4),0});
    const double scale=o.carrier_hz/299792.458;
    const size_t time_seed_count=static_cast<size_t>(std::floor(2*tau_bound/o.time_step_s))+1;
    uint64_t generation=0;
    for(size_t satellite=0;satellite<catalogue.count;++satellite) {
        leo_tle_record tle{};
        if(!catalogue.read_next(catalogue.user,tle))throw std::runtime_error("catalogue source ended early");
        leo_orbit_snapshot broad{},precise{};
        auto timer=Clock::now();
        auto status=leo_orbit_build_tle(coarse.get(),++generation,o.epoch_utc_ns,begin,coarse_step,coarse_n,&tle,1,&broad);
        stats.propagated_states+=coarse_n;stats.propagation_s+=elapsed(timer);
        if(status!=LEO_LOCATION_OK){stats.invalid_catalogue_ids.push_back(tle.satellite_id);continue;}
        const bool admitted=o.disable_gate||regional_visible(broad,region);
        if(!admitted&&!o.audit_gate)continue;
        timer=Clock::now();
        status=leo_orbit_build_tle(fine.get(),++generation,o.epoch_utc_ns,begin,fine_step,fine_n,&tle,1,&precise);
        stats.propagated_states+=fine_n;stats.propagation_s+=elapsed(timer);
        if(status!=LEO_LOCATION_OK){stats.invalid_catalogue_ids.push_back(tle.satellite_id);continue;}
        if(!admitted) {if(regional_visible(precise,region,0))++stats.gate_fine_envelope_misses;continue;}
        ++stats.retained_catalogue_count;stats.retained_catalogue_ids.push_back(tle.satellite_id);
        timer=Clock::now();
        for(size_t i=0;i<tracks.size();++i) {
            const auto& tr=tracks[i];
            if(!o.disable_gate&&!regional_visible(precise,region,2,tr.times.front()-tau_bound,tr.times.back()+tau_bound))continue;
            Hypothesis best;best.tle=tle;
            for(const auto& site:sites)for(size_t seed=0;seed<time_seed_count;++seed) {
                Point p=site;p.tau=std::min(tau_bound,-tau_bound+seed*o.time_step_s);
                const double cost=evaluate(precise,tr,region,p,scale,o.endpoint_proposals);++stats.seed_evaluations;
                if(cost<best.proposal){best.point=p;best.proposal=cost;}
            }
            if(!std::isfinite(best.proposal))continue;
            auto& list=candidates[i];list.push_back(best);
            std::sort(list.begin(),list.end(),[](const auto& x,const auto& y){
                return x.proposal!=y.proposal ? x.proposal<y.proposal : x.tle.satellite_id<y.tle.satellite_id;});
            if(list.size()>keep)list.resize(keep);
        }
        stats.proposal_s+=elapsed(timer);
    }
    const auto refine_start=Clock::now();
    for(size_t i=0;i<tracks.size();++i) {
        for(auto& candidate:candidates[i]) {
            leo_orbit_snapshot snapshot{};auto timer=Clock::now();
            if(leo_orbit_build_tle(fine.get(),++generation,o.epoch_utc_ns,begin,fine_step,fine_n,
                &candidate.tle,1,&snapshot)!=LEO_LOCATION_OK)
                throw std::runtime_error("refinement propagation changed");
            stats.propagated_states+=fine_n;stats.propagation_s+=elapsed(timer);
            candidate.point=refine(snapshot,tracks[i],region,candidate.point,scale,tau_bound);
            candidate.fit=raw_fit(snapshot,tracks[i],region,candidate.point,scale);++stats.refined_hypotheses;
        }
        std::sort(candidates[i].begin(),candidates[i].end(),[](const auto& a,const auto& b){
            return a.fit.cost!=b.fit.cost ? a.fit.cost<b.fit.cost : a.tle.satellite_id<b.tle.satellite_id;});
    }
    stats.refinement_s=elapsed(refine_start);
    result.tracks.resize(tracks.size());
    for(size_t i=0;i<tracks.size();++i)for(const auto& h:candidates[i]) {
        if(!std::isfinite(h.fit.cost))continue;
        const auto site=site_at(region,h.point);
        result.tracks[i].push_back({h.tle.satellite_id,h.point.east,h.point.north,site.latitude,site.longitude,
            h.point.tau,h.fit.offset,h.fit.train_rms,h.fit.validation_rms});
    }
    stats.total_s=elapsed(started);
    return result;
}
} // namespace leo::adaptive::location::doppler_match
