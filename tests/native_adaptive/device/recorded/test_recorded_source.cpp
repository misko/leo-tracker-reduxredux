#include "../../../../native/adaptive/device/recorded/recorded_source.h"
#include "../../../../native/adaptive/runtime/sha256.hpp"

#include <array>
#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>
#include <unistd.h>

namespace {
std::array<std::uint8_t,32> digest(const std::string& bytes) {
    const auto text=leo::adaptive::sha256(bytes);
    std::array<std::uint8_t,32> result{};
    for(std::size_t i=0;i<result.size();++i) {
        result[i]=static_cast<std::uint8_t>(std::stoul(text.substr(2*i,2),nullptr,16));
    }
    return result;
}

leo_recorded_source_visit_file row(std::uint64_t visit,std::uint64_t start,
        std::uint32_t target,const std::string& path,
        const std::string& bytes) {
    leo_recorded_source_visit_file value{};
    value.visit.visit=visit;
    value.visit.target_index=target;
    value.visit.target_key=target;
    value.visit.dwell_ms=120;
    value.visit.selection_applied=1;
    value.visit.expected_transition_flags=
        LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED|
        LEO_SOURCE_TRANSITION_TARGET_ATTESTED|
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    value.visit.requested_frequency_hz=960000000+target*250000000ULL;
    value.visit.expected_actual_frequency_hz=value.visit.requested_frequency_hz;
    value.visit.selection_counter=start-20;
    value.visit.transition_previous_valid_end=start-20;
    value.visit.transition_valid_start=start;
    value.visit.valid_start=start;
    value.visit.valid_end=start+120;
    value.raw_ci16_path=path.c_str();
    value.raw_bytes=bytes.size();
    const auto hash=digest(bytes);
    std::copy(hash.begin(),hash.end(),value.raw_sha256);
    return value;
}

struct Fixture {
    std::string directory;
    std::array<std::string,2> paths;
    std::array<std::string,2> bytes;
    std::array<leo_recorded_source_visit_file,2> rows;
    leo_recorded_source_config config{};
    Fixture() {
        const char* temporary=std::getenv("TMPDIR");
        std::string pattern=std::string(temporary ? temporary : "/var/tmp")+
            "/leo-recorded-source-test-XXXXXX";
        std::vector<char> writable(pattern.begin(),pattern.end());
        writable.push_back('\0');
        const char* made=::mkdtemp(writable.data());
        assert(made);
        directory=made; paths={directory+"/a.ci16",directory+"/b.ci16"};
        for(std::size_t visit=0;visit<2;++visit) {
            std::vector<std::int16_t> samples(120*2*2);
            for(std::size_t i=0;i<samples.size();++i)
                samples[i]=static_cast<std::int16_t>(i+visit*13);
            bytes[visit].assign(reinterpret_cast<const char*>(samples.data()),
                samples.size()*sizeof(samples[0]));
            std::ofstream output(paths[visit],std::ios::binary);
            output.write(bytes[visit].data(),static_cast<std::streamsize>(bytes[visit].size()));
            assert(output.good());
        }
        rows[0]=row(7,1000,0,paths[0],bytes[0]);
        rows[1]=row(301,2000,1,paths[1],bytes[1]);
        config={LEO_RECORDED_SOURCE_ABI_VERSION,1000,2,47,2,rows.data()};
    }
    ~Fixture() {
        for(const auto& path:paths) (void)::unlink(path.c_str());
        (void)::rmdir(directory.c_str());
    }
};

void check_capabilities_and_visits() {
    Fixture f; leo_recorded_source* source=nullptr;
    assert(leo_recorded_source_create(&f.config,&source)==0);
    auto* port=leo_recorded_source_port(source);
    leo_source_capabilities caps{};
    assert(leo_source_port_capabilities(port,&caps)==0);
    assert(caps.receiver_count==2 && caps.sample_rate_hz==1000 &&
        caps.counter_authority==LEO_SOURCE_COUNTER_PROVIDER_EXACT &&
        caps.position_semantics==LEO_SOURCE_POSITION_COHERENT_CURRENT &&
        caps.time_authority==LEO_SOURCE_TIME_NONE &&
        !(caps.flags&LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION));
    for(std::size_t ordinal=0;ordinal<2;++ordinal) {
        leo_source_position position{};
        assert(leo_source_port_position(port,&position)==0);
        assert(position.coordinate==f.rows[ordinal].visit.selection_counter);
        leo_source_selection selection{f.rows[ordinal].visit.target_key,
            f.rows[ordinal].visit.requested_frequency_hz,0};
        leo_source_transition transition{};
        const int selected=leo_source_port_select(port,&selection,&transition);
        if(selected) std::fprintf(stderr,"select %zu failed: %d\n",ordinal,selected);
        assert(selected==0);
        assert(transition.flags==f.rows[ordinal].visit.expected_transition_flags &&
            transition.profile_crc32==0 &&
            transition.valid_start==f.rows[ordinal].visit.valid_start);
        std::size_t samples=0;
        while(samples<120) {
            leo_source_block block{};
            assert(leo_source_port_next(port,&block)==0);
            assert(block.first_coordinate==f.rows[ordinal].visit.valid_start+samples &&
                block.time_authority==LEO_SOURCE_TIME_NONE &&
                block.missing_samples_before==0);
            assert((block.flags&LEO_SOURCE_BLOCK_GAP_EXACT)==
                (samples ? static_cast<std::uint32_t>(LEO_SOURCE_BLOCK_GAP_EXACT) : 0U));
            samples+=block.samples_per_receiver;
            assert(leo_source_port_release(port,&block)==0);
        }
        assert(samples==120);
    }
    leo_source_position done{};
    assert(leo_source_port_position(port,&done)==-ENODATA);
    assert(leo_recorded_source_destroy(source)==0);
}

void check_fail_closed_inputs() {
    Fixture f; leo_recorded_source* source=nullptr;
    auto invalid=f.config; invalid.receiver_count=1;
    assert(leo_recorded_source_create(&invalid,&source)==-EINVAL);
    invalid=f.config; auto rows=f.rows; rows[1].visit.visit=rows[0].visit.visit;
    invalid.visits=rows.data();
    assert(leo_recorded_source_create(&invalid,&source)==-EINVAL);
    rows=f.rows; rows[0].visit.dwell_ms=240; invalid.visits=rows.data();
    assert(leo_recorded_source_create(&invalid,&source)==-EINVAL);
    assert(leo_recorded_source_create(&f.config,&source)==0);
    auto* port=leo_recorded_source_port(source);
    leo_source_selection wrong{1,f.rows[0].visit.requested_frequency_hz,0};
    leo_source_transition transition{};
    assert(leo_source_port_select(port,&wrong,&transition)==-EPROTO);
    assert(leo_source_port_position(port,reinterpret_cast<leo_source_position*>(&transition))==-EPROTO);
    assert(leo_recorded_source_destroy(source)==0);

    assert(leo_recorded_source_create(&f.config,&source)==0);
    std::fstream corrupted(f.paths[0],std::ios::binary|std::ios::in|std::ios::out);
    char first{}; corrupted.read(&first,1); first=static_cast<char>(first^0x5a);
    corrupted.seekp(0); corrupted.write(&first,1); corrupted.close();
    leo_source_selection right{0,f.rows[0].visit.requested_frequency_hz,0};
    assert(leo_source_port_select(leo_recorded_source_port(source),&right,&transition)==-EBADMSG);
    assert(leo_recorded_source_destroy(source)==0);
}

void check_lease_and_cancel() {
    Fixture f; leo_recorded_source* source=nullptr;
    assert(leo_recorded_source_create(&f.config,&source)==0);
    auto* port=leo_recorded_source_port(source);
    leo_source_selection selection{0,f.rows[0].visit.requested_frequency_hz,0};
    leo_source_transition transition{};
    assert(leo_source_port_select(port,&selection,&transition)==0);
    leo_source_block block{};
    assert(leo_source_port_next(port,&block)==0);
    assert(leo_recorded_source_destroy(source)==-EBUSY);
    assert(leo_source_port_cancel(port)==0);
    assert(leo_source_port_release(port,&block)==0);
    assert(leo_source_port_next(port,&block)==-ECANCELED);
    assert(leo_recorded_source_destroy(source)==0);

    assert(leo_recorded_source_create(&f.config,&source)==0);
    port=leo_recorded_source_port(source);
    assert(leo_source_port_cancel(port)==0);
    assert(leo_source_port_select(port,&selection,&transition)==-ECANCELED);
    assert(leo_source_port_select(port,&selection,&transition)==-ECANCELED);
    assert(leo_recorded_source_destroy(source)==0);
}
}

int main() {
    check_capabilities_and_visits();
    check_fail_closed_inputs();
    check_lease_and_cancel();
}
