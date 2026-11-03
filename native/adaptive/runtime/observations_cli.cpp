#include "projection.hpp"
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
int main(int argc,char** argv) {
    const bool checkpoint=argc==2&&std::string(argv[1])=="--checkpoint";
    if(argc!=1&&!checkpoint) return 2;
    std::string line;size_t line_number=0;
    try {
        if(checkpoint)std::cout<<"candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\tsupport_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\tmeasured_cfo_hz\texact_score\tcontrol_score\tmargin\n";
        while(std::getline(std::cin,line)) {
            ++line_number;if(line.size()>4096) throw std::invalid_argument("oversized record");
            std::istringstream in(line);leo::adaptive::ProjectionSource s{};
            leo::adaptive::FractionalCandidate c{};
            unsigned upper,complete,qualified;std::string extra;
            if(!(in>>s.rate>>s.anchor_counter>>s.anchor_utc_ns>>s.generation>>s.visit>>s.window_counter
                 >>s.probe_index>>s.receiver>>s.channel>>upper>>s.actual_rf_hz>>s.utc_bracket_width_ns
                 >>s.input_digest>>s.analysis_digest>>qualified>>c.rank>>c.integer_epoch
                 >>c.fractional_offset>>c.tracking_cfo_hz>>c.exact_score>>c.control_score>>c.margin>>complete)
               || (in>>extra) || upper>1 || complete>1 || qualified>1)
                throw std::invalid_argument("invalid projection record");
            s.upper_edge=upper;s.continuity_qualified=qualified;c.complete=complete;
            leo::adaptive::Observation o;
            if(!leo::adaptive::project(s,c,o)) {if(!checkpoint)std::cout<<"unavailable\n";continue;}
            if(checkpoint){
                std::cout<<std::setprecision(17)<<o.candidate_id<<'\t'<<o.source_group_id<<'\t'
                    <<o.receiver<<'\t'<<o.channel<<'\t'<<(o.upper_edge?"upper":"lower")<<'\t'
                    <<o.actual_rf_hz<<'\t'<<o.support_start_utc_ns<<'\t'<<o.support_center_utc_ns<<'\t'
                    <<o.support_end_utc_ns<<'\t'<<o.measured_cfo_hz<<'\t'<<o.exact_score<<'\t'
                    <<o.control_score<<'\t'<<o.margin<<'\n';
                continue;
            }
            std::cout<<std::setprecision(17)<<o.candidate_id<<'\t'<<o.source_group_id<<'\t'
                <<o.support_start_utc_ns<<'\t'<<o.support_center_utc_ns<<'\t'<<o.support_end_utc_ns
                <<'\t'<<o.measured_cfo_hz<<'\t'<<o.standard_uncertainty_hz<<'\t'<<o.moment2
                <<'\t'<<o.moment3<<'\n';
        }
        if(!std::cin.eof()) throw std::runtime_error("input read failed");
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"projection record "<<line_number<<": "<<error.what()<<'\n';return 2;
    }
}
