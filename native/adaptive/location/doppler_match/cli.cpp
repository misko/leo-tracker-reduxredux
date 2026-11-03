#include "matcher.hpp"
#include "tle_id.hpp"
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>

using namespace leo::adaptive::location::doppler_match;
namespace {
void require(bool condition,const char* message) {if(!condition)throw std::runtime_error(message);}
void number(double v) {if(std::isfinite(v))std::cout<<v;else std::cout<<"null";}
bool read_tle(void* user,leo_tle_record& tle) {
    auto& input=*static_cast<std::istream*>(user);
    std::string a,b;
    require(bool(std::getline(input,a))&&bool(std::getline(input,b))
        &&a.size()==69&&b.size()==69&&a[0]=='1'&&b[0]=='2'&&a.substr(2,5)==b.substr(2,5)
        &&leo::adaptive::location::parse_tle_catalogue_id(std::string_view(a).substr(2,5),tle.satellite_id),
        "invalid TLE record");
    std::memcpy(tle.line1,a.data(),69);std::memcpy(tle.line2,b.data(),69);
    return true;
}
} // namespace

int main(int argc,char** argv) {
    try {
        const auto started=std::chrono::steady_clock::now();
        require(argc>=3,"usage: leo-doppler-match OBSERVATIONS CATALOGUE [--audit-gate] [--endpoint-proposals] [--no-gate]");
        Options options;
        for(int i=3;i<argc;++i) {
            const std::string flag=argv[i];
            if(flag=="--audit-gate")options.audit_gate=true;
            else if(flag=="--full-proposals")options.endpoint_proposals=false;
            else if(flag=="--endpoint-proposals")options.endpoint_proposals=true;
            else if(flag=="--no-gate")options.disable_gate=true;
            else throw std::runtime_error("unknown experiment flag");
        }
        std::ifstream input(argv[1]);std::string magic;size_t track_count=0;
        auto& o=options;
        input>>magic>>o.epoch_utc_ns>>o.carrier_hz>>o.region.latitude>>o.region.longitude>>o.region.radius
             >>o.time_bound_s>>o.fine_step_s>>o.coarse_step_s>>o.time_step_s>>o.keep_per_track>>track_count;
        require(bool(input)&&magic=="SDP1"&&track_count>0&&track_count<=1000,"invalid observations header");
        std::vector<Track> tracks(track_count);
        for(auto& tr:tracks) {
            size_t n=0,k=0;input>>n>>k;
            require(bool(input)&&n>=6&&n<=10000&&k>=3&&k<=101&&k%2==1,"invalid track dimensions");
            tr.times.resize(n);tr.measured.resize(n);tr.training.resize(n);
            tr.nodes.resize(k);tr.values.resize(k);
            for(size_t i=0;i<n;++i) {
                int mask=0;input>>tr.times[i]>>tr.measured[i]>>mask;
                require(bool(input)&&(mask==0||mask==1),"invalid observation");
                tr.training[i]=static_cast<unsigned char>(mask);
            }
            for(size_t i=0;i<k;++i) {
                input>>tr.nodes[i]>>tr.values[i];require(bool(input),"invalid spline nodes");
            }
        }
        input>>std::ws;require(input.eof(),"trailing observations");
        std::ifstream catalogue(argv[2]);size_t catalogue_count=0;catalogue>>catalogue_count;
        require(bool(catalogue),"invalid catalogue header");
        std::string line;std::getline(catalogue,line);
        // Pass a base pointer explicitly; the callback only knows istream.
        const auto result=match(tracks,options,{catalogue_count,read_tle,static_cast<std::istream*>(&catalogue)});
        catalogue>>std::ws;require(catalogue.eof(),"trailing catalogue records");
        const auto& s=result.statistics;
        const double total_s=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
        std::cout<<std::setprecision(17)<<"{\"schema\":\"leo-streaming-doppler-result/v1\",\"catalogue_records\":"<<s.catalogue_records
            <<",\"track_count\":"<<tracks.size()<<",\"observation_count\":"<<s.observation_count
            <<",\"retained_catalogue_count\":"<<s.retained_catalogue_count<<",\"invalid_catalogue_count\":"<<s.invalid_catalogue_ids.size()
            <<",\"gate_audited\":"<<(o.audit_gate?"true":"false")<<",\"gate_fine_envelope_misses\":"<<s.gate_fine_envelope_misses
            <<",\"full_spline_proposals\":"<<(o.endpoint_proposals?"false":"true")<<",\"gate_disabled\":"<<(o.disable_gate?"true":"false")
            <<",\"fine_step_s\":"<<o.fine_step_s<<",\"coarse_step_s\":"<<o.coarse_step_s
            <<",\"cache_begin_s\":"<<s.cache_begin_s<<",\"cache_end_s\":"<<s.cache_end_s
            <<",\"orbit_state_capacity_bytes\":"<<s.orbit_state_capacity_bytes
            <<",\"hypothesis_capacity_bytes\":"<<s.hypothesis_capacity_bytes
            <<",\"propagated_states\":"<<s.propagated_states<<",\"seed_evaluations\":"<<s.seed_evaluations
            <<",\"refined_hypotheses\":"<<s.refined_hypotheses<<",\"propagation_s\":"<<s.propagation_s
            <<",\"proposal_s\":"<<s.proposal_s<<",\"refinement_s\":"<<s.refinement_s
            <<",\"total_s\":"<<total_s<<",\"candidate_only\":true,\"global_completeness_claimed\":false"
            <<",\"time_policy\":\"independent track offsets; no joint clock or position fix\",\"invalid_catalogue_ids\":[";
        for(size_t i=0;i<s.invalid_catalogue_ids.size();++i){if(i)std::cout<<',';std::cout<<s.invalid_catalogue_ids[i];}
        std::cout<<"],\"retained_catalogue_ids\":[";
        for(size_t i=0;i<s.retained_catalogue_ids.size();++i){if(i)std::cout<<',';std::cout<<s.retained_catalogue_ids[i];}
        std::cout<<"],\"tracks\":[";
        for(size_t i=0;i<result.tracks.size();++i) {
            if(i)std::cout<<',';
            std::cout<<"{\"track_index\":"<<i<<",\"hypotheses\":[";
            size_t emitted=0;
            for(const auto& h:result.tracks[i]) {
                if(emitted++)std::cout<<',';
                std::cout<<"{\"satellite_id\":"<<h.satellite_id<<",\"east_km\":"<<h.east_km
                    <<",\"north_km\":"<<h.north_km<<",\"latitude_deg\":"<<h.latitude_deg
                    <<",\"longitude_deg\":"<<h.longitude_deg<<",\"time_offset_s\":"<<h.time_offset_s
                    <<",\"frequency_offset_hz\":"<<h.frequency_offset_hz<<",\"training_rms_hz\":";
                number(h.training_rms_hz);std::cout<<",\"validation_rms_hz\":";number(h.validation_rms_hz);
                std::cout<<'}';
            }
            std::cout<<"]}";
        }
        std::cout<<"]}\n";
        return s.gate_fine_envelope_misses ? 2 : 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
