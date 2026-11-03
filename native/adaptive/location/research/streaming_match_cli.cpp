#include "streaming_match.hpp"
#include "tle_id.hpp"
#include <chrono>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <string>

using namespace leo::location::streaming;
using Clock=std::chrono::steady_clock;
using Context=std::unique_ptr<leo_orbit_context,decltype(&leo_orbit_context_destroy)>;
struct Hypothesis { leo_tle_record tle{}; Point point; double proposal=inf; Fit fit; };
static double elapsed(Clock::time_point t) {return std::chrono::duration<double>(Clock::now()-t).count();}
static void require(bool condition,const char* message) {if(!condition)throw std::runtime_error(message);}
static void number(double v) {if(std::isfinite(v))std::cout<<v;else std::cout<<"null";}

int main(int argc,char** argv) {
    try {
        const auto started=Clock::now();
        require(argc>=3,"usage: streaming-match OBSERVATIONS CATALOGUE [--audit-gate] [--endpoint-proposals] [--no-gate]");
        bool audit=false,full=true,no_gate=false;
        for(int i=3;i<argc;++i) {
            const std::string flag=argv[i];
            if(flag=="--audit-gate")audit=true;
            else if(flag=="--full-proposals")full=true;
            else if(flag=="--endpoint-proposals")full=false;
            else if(flag=="--no-gate")no_gate=true;
            else throw std::runtime_error("unknown experiment flag");
        }
        std::ifstream input(argv[1]);std::string magic;
        int64_t epoch;double carrier,tau_bound,fine_step,coarse_step,tau_step;
        Region region{};size_t keep,track_count;
        input>>magic>>epoch>>carrier>>region.latitude>>region.longitude>>region.radius
             >>tau_bound>>fine_step>>coarse_step>>tau_step>>keep>>track_count;
        require(bool(input)&&magic=="SDP1"&&epoch>0&&std::isfinite(carrier)&&carrier>0
                &&std::isfinite(region.latitude)&&std::abs(region.latitude)<=90
                &&std::isfinite(region.longitude)&&std::abs(region.longitude)<=180
                &&region.radius>0&&region.radius<=500&&tau_bound>0&&tau_bound<=60
                &&fine_step>0&&fine_step<=10&&coarse_step>=fine_step&&coarse_step<=30
                &&tau_step>0&&tau_step<=tau_bound&&keep>0&&keep<=32&&track_count>0&&track_count<=1000,
                "invalid private experiment configuration");
        std::vector<Track> tracks(track_count);
        double first=inf,last=-inf;size_t observation_count=0;
        for(auto& tr:tracks) {
            size_t n,k;input>>n>>k;
            require(bool(input)&&n>=6&&n<=10000&&k>=3&&k<=101&&k%2==1,"invalid track dimensions");
            tr.times.resize(n);tr.measured.resize(n);tr.training.resize(n);
            tr.nodes.resize(k);tr.values.resize(k);size_t training=0;
            for(size_t i=0;i<n;++i) {
                int m;input>>tr.times[i]>>tr.measured[i]>>m;
                require(bool(input)&&std::isfinite(tr.times[i])&&std::isfinite(tr.measured[i])
                        &&(m==0||m==1)&&(!i||tr.times[i]>tr.times[i-1]),"invalid observation");
                tr.training[i]=m;training+=m;
            }
            require(training>=4&&training<n,"invalid partition");
            for(size_t i=0;i<k;++i) {
                input>>tr.nodes[i]>>tr.values[i];
                require(bool(input)&&std::isfinite(tr.nodes[i])&&std::isfinite(tr.values[i])
                        &&(!i||tr.nodes[i]>tr.nodes[i-1]),"invalid spline nodes");
            }
            require(tr.nodes.front()>=tr.times.front()&&tr.nodes.back()<=tr.times.back()+1e-9,
                    "spline support differs from observed interval");
            first=std::min(first,tr.times.front());last=std::max(last,tr.times.back());observation_count+=n;
        }
        input>>std::ws;require(input.eof(),"trailing observations");
        require(last-first<=1200,"observation history exceeds prototype bound");
        const double begin=std::floor((first-tau_bound)/coarse_step)*coarse_step-coarse_step;
        const double end=std::ceil((last+tau_bound)/coarse_step)*coarse_step+coarse_step;
        const uint32_t coarse_n=static_cast<uint32_t>(std::ceil((end-begin)/coarse_step))+1;
        const uint32_t fine_n=static_cast<uint32_t>(std::ceil((end-begin)/fine_step))+1;
        Context coarse(leo_orbit_context_create(1,coarse_n),&leo_orbit_context_destroy);
        Context fine(leo_orbit_context_create(1,fine_n),&leo_orbit_context_destroy);
        require(bool(coarse)&&bool(fine),"orbit workspace allocation failed");
        std::vector<std::vector<Hypothesis>> candidates(track_count);
        for(auto& c:candidates)c.reserve(keep+1);
        std::vector<Point> sites={{0,0,0}};
        for(int i=0;i<8;++i)sites.push_back({region.radius*std::cos(i*pi/4),region.radius*std::sin(i*pi/4),0});
        const double scale=carrier/299792.458;
        std::ifstream catalogue(argv[2]);size_t catalogue_count;catalogue>>catalogue_count;
        require(bool(catalogue)&&catalogue_count>0&&catalogue_count<=20000,"invalid catalogue size");
        std::string line;std::getline(catalogue,line);
        uint64_t generation=0,propagations=0,seed_evaluations=0;
        size_t retained=0,audit_misses=0;std::vector<int32_t> invalid_ids,retained_ids;
        double propagation_s=0,proposal_s=0;
        for(size_t satellite=0;satellite<catalogue_count;++satellite) {
            leo_tle_record tle{};std::string a,b;
            require(bool(std::getline(catalogue,a))&&bool(std::getline(catalogue,b))
                    &&a.size()==69&&b.size()==69&&a[0]=='1'&&b[0]=='2'&&a.substr(2,5)==b.substr(2,5)
                    &&leo::adaptive::location::parse_tle_catalogue_id(std::string_view(a).substr(2,5),tle.satellite_id),
                    "invalid TLE record");
            std::memcpy(tle.line1,a.data(),69);std::memcpy(tle.line2,b.data(),69);
            leo_orbit_snapshot broad{},precise{};
            auto timer=Clock::now();
            auto status=leo_orbit_build_tle(coarse.get(),++generation,epoch,begin,coarse_step,coarse_n,&tle,1,&broad);
            propagations+=coarse_n;propagation_s+=elapsed(timer);
            if(status!=LEO_LOCATION_OK){invalid_ids.push_back(tle.satellite_id);continue;}
            const bool admitted=no_gate||regional_visible(broad,region);
            if(!admitted&&!audit)continue;
            timer=Clock::now();
            status=leo_orbit_build_tle(fine.get(),++generation,epoch,begin,fine_step,fine_n,&tle,1,&precise);
            propagations+=fine_n;propagation_s+=elapsed(timer);
            if(status!=LEO_LOCATION_OK){invalid_ids.push_back(tle.satellite_id);continue;}
            if(!admitted) {if(regional_visible(precise,region,0))++audit_misses;continue;}
            ++retained;retained_ids.push_back(tle.satellite_id);
            timer=Clock::now();
            for(size_t i=0;i<tracks.size();++i) {
                const auto& tr=tracks[i];
                if(!no_gate&&!regional_visible(precise,region,2,tr.times.front()-tau_bound,tr.times.back()+tau_bound))continue;
                Hypothesis best;best.tle=tle;
                for(const auto& site:sites)for(double tau=-tau_bound;tau<=tau_bound+1e-9;tau+=tau_step) {
                    Point p=site;p.tau=tau;
                    const double cost=evaluate(precise,tr,region,p,scale,!full);++seed_evaluations;
                    if(cost<best.proposal){best.point=p;best.proposal=cost;}
                }
                if(!std::isfinite(best.proposal))continue;
                auto& list=candidates[i];list.push_back(best);
                std::sort(list.begin(),list.end(),[](const auto& x,const auto& y){
                    return x.proposal!=y.proposal ? x.proposal<y.proposal : x.tle.satellite_id<y.tle.satellite_id;});
                if(list.size()>keep)list.resize(keep);
            }
            proposal_s+=elapsed(timer);
        }
        catalogue>>std::ws;require(catalogue.eof(),"trailing catalogue records");
        auto refine_start=Clock::now();size_t refined=0;
        for(size_t i=0;i<tracks.size();++i) {
            for(auto& candidate:candidates[i]) {
                leo_orbit_snapshot snapshot{};auto timer=Clock::now();
                require(leo_orbit_build_tle(fine.get(),++generation,epoch,begin,fine_step,fine_n,
                        &candidate.tle,1,&snapshot)==LEO_LOCATION_OK,"refinement propagation changed");
                propagations+=fine_n;propagation_s+=elapsed(timer);
                candidate.point=refine(snapshot,tracks[i],region,candidate.point,scale,tau_bound);
                candidate.fit=raw_fit(snapshot,tracks[i],region,candidate.point,scale);++refined;
            }
            std::sort(candidates[i].begin(),candidates[i].end(),[](const auto& a,const auto& b){
                return a.fit.cost!=b.fit.cost ? a.fit.cost<b.fit.cost : a.tle.satellite_id<b.tle.satellite_id;});
        }
        const double refinement_s=elapsed(refine_start);
        std::cout<<std::setprecision(17)<<"{\"schema\":\"leo-streaming-doppler-result/v1\",\"catalogue_records\":"<<catalogue_count
            <<",\"track_count\":"<<tracks.size()<<",\"observation_count\":"<<observation_count
            <<",\"retained_catalogue_count\":"<<retained<<",\"invalid_catalogue_count\":"<<invalid_ids.size()
            <<",\"gate_audited\":"<<(audit?"true":"false")<<",\"gate_fine_envelope_misses\":"<<audit_misses
            <<",\"full_spline_proposals\":"<<(full?"true":"false")<<",\"gate_disabled\":"<<(no_gate?"true":"false")
            <<",\"fine_step_s\":"<<fine_step<<",\"coarse_step_s\":"<<coarse_step
            <<",\"cache_begin_s\":"<<begin<<",\"cache_end_s\":"<<end
            <<",\"orbit_state_capacity_bytes\":"<<(coarse_n+fine_n)*2*sizeof(leo_orbit_state)
            <<",\"hypothesis_capacity_bytes\":"<<tracks.size()*(keep+1)*sizeof(Hypothesis)
            <<",\"propagated_states\":"<<propagations<<",\"seed_evaluations\":"<<seed_evaluations
            <<",\"refined_hypotheses\":"<<refined<<",\"propagation_s\":"<<propagation_s
            <<",\"proposal_s\":"<<proposal_s<<",\"refinement_s\":"<<refinement_s
            <<",\"total_s\":"<<elapsed(started)<<",\"candidate_only\":true,\"global_completeness_claimed\":false"
            <<",\"time_policy\":\"independent track offsets; no joint clock or position fix\",\"invalid_catalogue_ids\":[";
        for(size_t i=0;i<invalid_ids.size();++i){if(i)std::cout<<',';std::cout<<invalid_ids[i];}
        std::cout<<"],\"retained_catalogue_ids\":[";
        for(size_t i=0;i<retained_ids.size();++i){if(i)std::cout<<',';std::cout<<retained_ids[i];}
        std::cout<<"],\"tracks\":[";
        for(size_t i=0;i<tracks.size();++i) {
            if(i)std::cout<<',';std::cout<<"{\"track_index\":"<<i<<",\"hypotheses\":[";
            size_t emitted=0;
            for(const auto& h:candidates[i]) {
                if(!std::isfinite(h.fit.cost))continue;
                if(emitted++)std::cout<<',';const Site site=site_at(region,h.point);
                std::cout<<"{\"satellite_id\":"<<h.tle.satellite_id<<",\"east_km\":"<<h.point.east
                    <<",\"north_km\":"<<h.point.north<<",\"latitude_deg\":"<<site.latitude
                    <<",\"longitude_deg\":"<<site.longitude<<",\"time_offset_s\":"<<h.point.tau
                    <<",\"frequency_offset_hz\":"<<h.fit.offset<<",\"training_rms_hz\":";
                number(h.fit.train_rms);std::cout<<",\"validation_rms_hz\":";number(h.fit.validation_rms);
                std::cout<<'}';
            }
            std::cout<<"]}";
        }
        std::cout<<"]}\n";
        return audit_misses ? 2 : 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
