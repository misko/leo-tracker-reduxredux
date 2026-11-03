#include "recorded_source.h"
#include "../../runtime/sha256.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <limits>
#include <memory>
#include <new>
#include <string>
#include <vector>

namespace {
using leo::adaptive::sha256;

struct VisitFile {
    leo_scanner_recorded_visit visit{};
    std::string path;
    std::array<std::uint8_t,32> digest{};
    std::uint64_t bytes{};
};

bool nonzero(const std::array<std::uint8_t,32>& digest) {
    return std::any_of(digest.begin(),digest.end(),[](std::uint8_t value) {
        return value!=0;
    });
}

std::array<std::uint8_t,32> parse_digest(const std::string& text) {
    std::array<std::uint8_t,32> result{};
    if(text.size()!=64) return result;
    const auto nibble=[](char value)->int {
        if(value>='0' && value<='9') return value-'0';
        if(value>='a' && value<='f') return value-'a'+10;
        return -1;
    };
    for(std::size_t i=0;i<result.size();++i) {
        const int high=nibble(text[2*i]),low=nibble(text[2*i+1]);
        if(high<0 || low<0) return {};
        result[i]=static_cast<std::uint8_t>((high<<4)|low);
    }
    return result;
}
}

struct leo_recorded_source {
    std::uint32_t rate{},receivers{},block_samples{};
    std::vector<VisitFile> visits;
    std::size_t next_visit{},selected_visit{std::numeric_limits<std::size_t>::max()};
    std::vector<std::int16_t> raw;
    std::size_t sample_offset{};
    std::uintptr_t lease{};
    std::atomic<bool> cancelled{false};
    bool selected{},faulted{};
    leo_source_port port{};
};

namespace {
constexpr std::uint32_t historical_flags=
    LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
    LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
    LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;

bool valid_visit(const leo_recorded_source_config& config,
                 const leo_recorded_source_visit_file& input,
                 const leo_scanner_recorded_visit* previous) {
    const auto& visit=input.visit;
    const std::uint64_t samples=static_cast<std::uint64_t>(config.sample_rate_hz)*120U/1000U;
    const std::uint64_t scalars=samples*config.receiver_count*2U;
    return input.raw_ci16_path && *input.raw_ci16_path &&
        visit.dwell_ms==120U && visit.selection_applied==1U &&
        visit.expected_transition_flags==historical_flags &&
        visit.expected_profile_crc32==0U && visit.target_index<LEO_SCANNER_MAX_TARGETS &&
        visit.target_key<LEO_SCANNER_MAX_TARGETS && visit.requested_frequency_hz &&
        visit.expected_actual_frequency_hz && visit.valid_end>=visit.valid_start &&
        visit.valid_end-visit.valid_start==samples &&
        visit.transition_valid_start==visit.valid_start &&
        visit.transition_previous_valid_end<=visit.transition_valid_start &&
        visit.transition_previous_valid_end<=visit.selection_counter &&
        visit.selection_counter<=visit.transition_valid_start &&
        scalars<=std::numeric_limits<std::uint64_t>::max()/sizeof(std::int16_t) &&
        input.raw_bytes==scalars*sizeof(std::int16_t) &&
        (!previous || (visit.visit>previous->visit &&
            visit.valid_start>previous->valid_start &&
            visit.selection_counter>=previous->valid_end));
}

int capabilities(void* opaque,leo_source_capabilities* output) {
    auto& source=*static_cast<leo_recorded_source*>(opaque);
    *output={};
    output->abi_version=LEO_SOURCE_PORT_ABI_VERSION;
    output->sample_format=LEO_SOURCE_SAMPLE_FORMAT_CI16;
    output->flags=LEO_SOURCE_CAP_CANCEL|LEO_SOURCE_CAP_SELECT|
        LEO_SOURCE_CAP_SIMULTANEOUS_RX|LEO_SOURCE_CAP_COHERENT_RX|
        LEO_SOURCE_CAP_FREQUENCY_ATTESTATION|LEO_SOURCE_CAP_TARGET_ATTESTATION|
        LEO_SOURCE_CAP_EXACT_GAP|LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    output->sample_rate_hz=source.rate;
    output->receiver_count=source.receivers;
    output->maximum_samples_per_block=source.block_samples;
    output->counter_authority=LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    output->position_semantics=LEO_SOURCE_POSITION_COHERENT_CURRENT;
    output->time_authority=LEO_SOURCE_TIME_NONE;
    return 0;
}

int position(void* opaque,leo_source_position* output) {
    auto& source=*static_cast<leo_recorded_source*>(opaque);
    if(source.faulted) return -EIO;
    if(source.cancelled.load()) return -ECANCELED;
    if(source.lease) return -EBUSY;
    if(source.next_visit>=source.visits.size()) return -ENODATA;
    output->coordinate=source.visits[source.next_visit].visit.selection_counter;
    output->counter_authority=LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    output->semantics=LEO_SOURCE_POSITION_COHERENT_CURRENT;
    return 0;
}

int load_selected(leo_recorded_source& source,const VisitFile& file) {
    if(file.bytes>std::numeric_limits<std::size_t>::max()) return -EOVERFLOW;
    std::ifstream input(file.path,std::ios::binary);
    if(!input) return -ENOENT;
    input.seekg(0,std::ios::end);
    if(input.tellg()!=static_cast<std::streamoff>(file.bytes)) return -EIO;
    input.seekg(0,std::ios::beg);
    std::string bytes(static_cast<std::size_t>(file.bytes),'\0');
    input.read(bytes.data(),static_cast<std::streamsize>(bytes.size()));
    if(input.gcount()!=static_cast<std::streamsize>(bytes.size())) return -EIO;
    if(parse_digest(sha256(bytes))!=file.digest) return -EBADMSG;
    source.raw.resize(bytes.size()/sizeof(std::int16_t));
    std::memcpy(source.raw.data(),bytes.data(),bytes.size());
    source.sample_offset=0;
    return 0;
}

int select_visit(void* opaque,const leo_source_selection* selection,
                 leo_source_transition* output) {
    auto& source=*static_cast<leo_recorded_source*>(opaque);
    if(source.faulted) return -EIO;
    if(source.cancelled.load()) return -ECANCELED;
    if(source.lease || source.selected) return -EBUSY;
    if(source.next_visit>=source.visits.size()) return -ENODATA;
    const auto& file=source.visits[source.next_visit];
    const auto& visit=file.visit;
    const std::uint64_t error=visit.expected_actual_frequency_hz>=
        selection->requested_frequency_hz ?
        visit.expected_actual_frequency_hz-selection->requested_frequency_hz :
        selection->requested_frequency_hz-visit.expected_actual_frequency_hz;
    if(selection->target_key!=visit.target_key ||
       selection->requested_frequency_hz!=visit.requested_frequency_hz ||
       error>selection->maximum_frequency_error_hz) return -EPROTO;
    int loaded=0;
    try {
        loaded=load_selected(source,file);
    } catch(const std::bad_alloc&) {
        loaded=-ENOMEM;
    } catch(...) {
        loaded=-EIO;
    }
    if(loaded) { source.faulted=true; return loaded; }
    if(source.cancelled.load()) {
        source.raw.clear();
        return -ECANCELED;
    }
    *output={};
    output->flags=visit.expected_transition_flags;
    output->selected_target_key=visit.target_key;
    output->profile_crc32=0;
    output->counter_authority=LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    output->position_semantics=LEO_SOURCE_POSITION_COHERENT_CURRENT;
    output->time_authority=LEO_SOURCE_TIME_NONE;
    output->actual_frequency_hz=visit.expected_actual_frequency_hz;
    output->previous_valid_end=visit.transition_previous_valid_end;
    output->valid_start=visit.transition_valid_start;
    source.selected=true;
    source.selected_visit=source.next_visit;
    return 0;
}

int next_block(void* opaque,leo_source_block* output) {
    auto& source=*static_cast<leo_recorded_source*>(opaque);
    if(source.faulted) return -EIO;
    if(source.cancelled.load()) return -ECANCELED;
    if(source.lease) return -EBUSY;
    if(!source.selected || source.selected_visit>=source.visits.size()) return -ENODATA;
    const auto& visit=source.visits[source.selected_visit].visit;
    const std::size_t total=source.raw.size()/(source.receivers*2U);
    if(source.sample_offset>=total) return -ENODATA;
    const std::size_t count=std::min<std::size_t>(source.block_samples,
        total-source.sample_offset);
    source.lease=source.sample_offset+1U;
    *output={};
    output->ci16=source.raw.data()+source.sample_offset*source.receivers*2U;
    output->iq_bytes=count*source.receivers*2U*sizeof(std::int16_t);
    output->samples_per_receiver=static_cast<std::uint32_t>(count);
    output->receiver_count=source.receivers;
    /* Selection establishes a fresh recorded validity boundary. There is no
     * preceding delivered block inside this visit for the first block; later
     * blocks explicitly attest a zero exact gap. */
    output->flags=source.sample_offset ?
        static_cast<std::uint32_t>(LEO_SOURCE_BLOCK_GAP_EXACT) : 0U;
    output->counter_authority=LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    output->time_authority=LEO_SOURCE_TIME_NONE;
    output->first_coordinate=visit.valid_start+source.sample_offset;
    output->end_coordinate=output->first_coordinate+count;
    output->stream_ordinal=source.sample_offset;
    output->missing_samples_before=0;
    output->buffer_sequence=source.sample_offset/source.block_samples;
    output->lease_token=source.lease;
    return 0;
}

int release_block(void* opaque,leo_source_block*) {
    auto& source=*static_cast<leo_recorded_source*>(opaque);
    if(!source.lease) return -EINVAL;
    const std::size_t total=source.raw.size()/(source.receivers*2U);
    source.sample_offset=std::min<std::size_t>(total,
        source.sample_offset+source.block_samples);
    source.lease=0;
    if(source.sample_offset==total) {
        source.selected=false;
        source.raw.clear();
        ++source.next_visit;
        source.selected_visit=std::numeric_limits<std::size_t>::max();
    }
    return 0;
}

int cancel(void* opaque) {
    static_cast<leo_recorded_source*>(opaque)->cancelled=true;
    return 0;
}

const leo_source_ops operations={capabilities,position,select_visit,next_block,
    release_block,cancel};
}

extern "C" int leo_recorded_source_create(
    const leo_recorded_source_config* config,leo_recorded_source** output) {
    if(!output) return -EINVAL;
    *output=nullptr;
    if(!config || config->abi_version!=LEO_RECORDED_SOURCE_ABI_VERSION ||
       !config->sample_rate_hz || config->sample_rate_hz%1000U ||
       config->receiver_count!=2U || !config->maximum_samples_per_block ||
       !config->visit_count || config->visit_count>LEO_SCANNER_RECORDED_PLAN_MAX_VISITS ||
       !config->visits) return -EINVAL;
    try {
        auto source=std::make_unique<leo_recorded_source>();
        source->rate=config->sample_rate_hz;
        source->receivers=config->receiver_count;
        source->block_samples=config->maximum_samples_per_block;
        source->visits.reserve(config->visit_count);
        const leo_scanner_recorded_visit* previous=nullptr;
        for(std::uint32_t i=0;i<config->visit_count;++i) {
            const auto& input=config->visits[i];
            if(!valid_visit(*config,input,previous)) return -EINVAL;
            VisitFile copied;
            copied.visit=input.visit;
            copied.path=input.raw_ci16_path;
            std::copy(std::begin(input.raw_sha256),std::end(input.raw_sha256),
                copied.digest.begin());
            if(!nonzero(copied.digest)) return -EINVAL;
            copied.bytes=input.raw_bytes;
            source->visits.push_back(std::move(copied));
            previous=&input.visit;
        }
        const int status=leo_source_port_init(&source->port,source.get(),&operations);
        if(status) return status;
        *output=source.release();
        return 0;
    } catch(const std::bad_alloc&) { return -ENOMEM; }
      catch(...) { return -EINVAL; }
}

extern "C" leo_source_port* leo_recorded_source_port(leo_recorded_source* source) {
    return source ? &source->port : nullptr;
}

extern "C" int leo_recorded_source_destroy(leo_recorded_source* source) {
    if(!source) return -EINVAL;
    if(source->port.outstanding_lease || source->lease) return -EBUSY;
    delete source;
    return 0;
}
