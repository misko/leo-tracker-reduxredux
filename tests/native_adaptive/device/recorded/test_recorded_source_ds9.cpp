#include "../../../../native/adaptive/device/recorded/recorded_source.h"

#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <string>

namespace {
std::array<std::uint8_t,32> digest(const std::string& text) {
    assert(text.size()==64);
    std::array<std::uint8_t,32> result{};
    for(std::size_t i=0;i<result.size();++i)
        result[i]=static_cast<std::uint8_t>(std::stoul(text.substr(2*i,2),nullptr,16));
    return result;
}
}

int main(int argc,char** argv) {
    assert(argc==2);
    leo_recorded_source_visit_file file{};
    file.visit.visit=301;
    file.visit.target_index=0;
    file.visit.target_key=0;
    file.visit.dwell_ms=120;
    file.visit.selection_applied=1;
    file.visit.expected_transition_flags=
        LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED|
        LEO_SOURCE_TRANSITION_TARGET_ATTESTED|
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    file.visit.requested_frequency_hz=960000000;
    file.visit.expected_actual_frequency_hz=960000000;
    file.visit.selection_counter=1247949281424ULL;
    file.visit.transition_previous_valid_end=1247949281424ULL;
    file.visit.transition_valid_start=1247949437197ULL;
    file.visit.valid_start=1247949437197ULL;
    file.visit.valid_end=1247950337197ULL;
    file.raw_ci16_path=argv[1];
    file.raw_bytes=7200000;
    const auto expected=digest("3530f06a807aec4f0d94cf1a7b58de928d6dc433d3310b70de1c5763d3364a6a");
    std::copy(expected.begin(),expected.end(),file.raw_sha256);
    const leo_recorded_source_config config{LEO_RECORDED_SOURCE_ABI_VERSION,
        7500000,2,100000,1,&file};
    leo_recorded_source* source=nullptr;
    assert(leo_recorded_source_create(&config,&source)==0);
    auto* port=leo_recorded_source_port(source);
    leo_source_position position{};
    assert(leo_source_port_position(port,&position)==0 &&
        position.coordinate==file.visit.selection_counter);
    leo_source_selection selection{0,960000000,0};
    leo_source_transition transition{};
    assert(leo_source_port_select(port,&selection,&transition)==0);
    std::uint64_t received=0;
    while(received<900000) {
        leo_source_block block{};
        assert(leo_source_port_next(port,&block)==0);
        assert(block.first_coordinate==file.visit.valid_start+received);
        received+=block.samples_per_receiver;
        assert(leo_source_port_release(port,&block)==0);
    }
    assert(received==900000);
    assert(leo_recorded_source_destroy(source)==0);
}
