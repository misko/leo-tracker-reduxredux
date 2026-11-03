// Required recorded-data lane: pass the projection TSV on stdin. The bracket
// is reconstructed from persisted authority for replay, not measured live.
#include "ingest.hpp"
#include <cassert>
#include <cmath>
#include <iostream>
#include <sstream>
using namespace leo::adaptive;
int main() {
    std::string line; std::size_t rows=0, emitted=0;
    while(std::getline(std::cin,line)) {
        ProjectionSource s{};FractionalCandidate c{};
        unsigned upper,qualified,complete;std::string extra;
        std::istringstream in(line);
        if(!(in>>s.rate>>s.anchor_counter>>s.anchor_utc_ns>>s.generation>>s.visit>>s.window_counter
             >>s.probe_index>>s.receiver>>s.channel>>upper>>s.actual_rf_hz>>s.utc_bracket_width_ns
             >>s.input_digest>>s.analysis_digest>>qualified>>c.rank>>c.integer_epoch
             >>c.fractional_offset>>c.tracking_cfo_hz>>c.exact_score>>c.control_score>>c.margin>>complete)
           || (in>>extra) || upper>1 || qualified!=1 || complete>1) return 2;
        s.upper_edge=upper;s.continuity_qualified=true;c.complete=complete;
        // The historical 120-ms DS9 panel uses one probe per visit.
        if(s.probe_index || s.window_counter<s.anchor_counter ||
           s.utc_bracket_width_ns<1 || s.utc_bracket_width_ns>1e9) return 3;
        const auto width=static_cast<std::uint64_t>(s.utc_bracket_width_ns);
        if(static_cast<double>(width)!=s.utc_bracket_width_ns) return 4;
        timing::Timebase clock({s.rate,1000000000,3600000000000ULL,0,0,1});
        assert(clock.begin(s.generation)==timing::Status::ok);
        const auto before=s.anchor_utc_ns-static_cast<std::int64_t>(width/2);
        assert(clock.observe({1000000000,1000000000+width,s.anchor_counter,
            before,before+static_cast<std::int64_t>(width),true})==timing::Status::ok);
        ingest::Authority a{s.generation,s.rate,s.input_digest,s.analysis_digest,
            {{0,1,s.channel,1500000000,s.actual_rf_hz,s.upper_edge}}};
        leo_scanner_event e{};e.kind=LEO_SCANNER_CANDIDATE;e.visit=s.visit;
        e.valid_start=s.window_counter;e.valid_end=e.valid_start+static_cast<std::uint64_t>(s.rate)*120/1000;
        e.attested_profile_crc32=1;e.frequency_hz=1500000000;
        e.receiver_id=s.receiver;e.candidate_index=c.rank;
        e.candidate.epoch=c.integer_epoch;e.candidate.fractional_epoch_status=c.complete?1:2;
        e.candidate.fractional_epoch_offset_samples=c.fractional_offset;
        e.candidate.fractional_tracking_cfo_hz=c.tracking_cfo_hz;
        e.candidate.fractional_exact_score=c.exact_score;
        e.candidate.fractional_control_score=c.control_score;e.candidate.fractional_margin=c.margin;
        Observation expected,actual;const bool pass=project(s,c,expected);
        const auto status=ingest::project_event(a,clock,e,actual);
        assert(status==(pass?ingest::Status::emitted:ingest::Status::nonpassing));
        if(pass) {
            assert(actual.candidate_id==expected.candidate_id && actual.source_group_id==expected.source_group_id);
            assert(actual.support_start_utc_ns==expected.support_start_utc_ns);
            assert(actual.support_center_utc_ns==expected.support_center_utc_ns);
            assert(actual.support_end_utc_ns==expected.support_end_utc_ns);
            assert(actual.measured_cfo_hz==expected.measured_cfo_hz);
            assert(actual.standard_uncertainty_hz==expected.standard_uncertainty_hz);
            assert(actual.moment2==expected.moment2 && actual.moment3==expected.moment3);
            ++emitted;
        }
        ++rows;
    }
    if(!std::cin.eof() || !rows || !emitted) return 5;
    std::cout<<"{\"rows\":"<<rows<<",\"observations\":"<<emitted<<",\"exact_projection_parity\":true}\n";
}
