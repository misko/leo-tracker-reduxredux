#include "scanner_source.h"

#include <algorithm>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <tuple>
#include <vector>

namespace {
constexpr uint32_t rate=2500000U;
constexpr size_t dwell_times=300000U;
constexpr size_t block_times=50000U;

template <typename T> std::vector<T> read_file(const char* path) {
    FILE* file=std::fopen(path,"rb"); assert(file);
    assert(std::fseek(file,0,SEEK_END)==0);
    const long bytes=std::ftell(file); assert(bytes>=0 && bytes%sizeof(T)==0);
    assert(std::fseek(file,0,SEEK_SET)==0);
    std::vector<T> value(static_cast<size_t>(bytes)/sizeof(T));
    assert(std::fread(value.data(),sizeof(T),value.size(),file)==value.size());
    assert(std::fclose(file)==0); return value;
}

struct Source {
    std::vector<int16_t> iq;
    uint64_t coordinate=51000U;
    size_t next=0;
};

int source_capabilities(void*,leo_source_capabilities* out) {
    *out={}; out->abi_version=LEO_SOURCE_PORT_ABI_VERSION;
    out->sample_format=LEO_SOURCE_SAMPLE_FORMAT_CI16;
    out->flags=LEO_SOURCE_CAP_CANCEL|LEO_SOURCE_CAP_SELECT|
        LEO_SOURCE_CAP_SIMULTANEOUS_RX|LEO_SOURCE_CAP_COHERENT_RX|
        LEO_SOURCE_CAP_FREQUENCY_ATTESTATION|LEO_SOURCE_CAP_TARGET_ATTESTATION|
        LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION|LEO_SOURCE_CAP_EXACT_GAP|
        LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    out->sample_rate_hz=rate; out->receiver_count=2U;
    out->maximum_samples_per_block=block_times;
    out->counter_authority=LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    out->position_semantics=LEO_SOURCE_POSITION_COHERENT_CURRENT;
    return 0;
}
int source_position(void* context,leo_source_position* out) {
    const auto& source=*static_cast<Source*>(context); *out={};
    out->coordinate=source.coordinate;
    out->counter_authority=LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    out->semantics=LEO_SOURCE_POSITION_COHERENT_CURRENT; return 0;
}
int source_select(void* context,const leo_source_selection* selection,
                  leo_source_transition* out) {
    const auto& source=*static_cast<Source*>(context); *out={};
    out->selected_target_key=selection->target_key;
    out->actual_frequency_hz=selection->requested_frequency_hz;
    out->profile_crc32=0x12345678U;
    out->previous_valid_end=source.coordinate; out->valid_start=source.coordinate;
    out->counter_authority=LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    out->position_semantics=LEO_SOURCE_POSITION_COHERENT_CURRENT;
    out->flags=LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED|
        LEO_SOURCE_TRANSITION_TARGET_ATTESTED|
        LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED|
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY; return 0;
}
int source_next(void* context,leo_source_block* out) {
    auto& source=*static_cast<Source*>(context);
    const size_t total_blocks=source.iq.size()/(block_times*4U);
    if (source.next>=total_blocks) return -ENODATA;
    *out={}; out->ci16=source.iq.data()+source.next*block_times*4U;
    out->iq_bytes=block_times*4U*sizeof(int16_t);
    out->samples_per_receiver=block_times; out->receiver_count=2U;
    out->counter_authority=LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    out->first_coordinate=source.coordinate;
    out->end_coordinate=source.coordinate+block_times;
    out->buffer_sequence=source.next+1U; out->lease_token=++source.next;
    source.coordinate=out->end_coordinate; return 0;
}
int source_release(void*,leo_source_block*) { return 0; }
int source_cancel(void*) { return 0; }
const leo_source_ops source_ops{source_capabilities,source_position,source_select,
    source_next,source_release,source_cancel};

int detector_analyze(void* context,const int16_t* iq,size_t times,
                     uint32_t dwell_ms,uint32_t stride_ms,
                     leo_native_glrt_result* result) {
    return leo_native_glrt_analyze(static_cast<leo_native_glrt*>(context),iq,times,
        dwell_ms,stride_ms,result);
}
int detector_capabilities(void*,leo_native_glrt_capabilities* out) {
    return leo_native_glrt_get_capabilities(out);
}

struct Events { std::vector<leo_scanner_source_event> values; };
void collect(void* context,const leo_scanner_source_event* event) {
    static_cast<Events*>(context)->values.push_back(*event);
}

leo_scanner_config config() {
    leo_scanner_config c{}; c.abi_version=LEO_SCANNER_ABI_VERSION;
    c.session=11U; c.generation=12U; c.seed=13U; c.sample_rate_hz=rate;
    c.receiver_count=2U; c.duration_ms=700U; c.maximum_visits=2U;
    timespec now{}; assert(clock_gettime(CLOCK_MONOTONIC,&now)==0);
    c.wall_deadline_monotonic_ns=static_cast<uint64_t>(now.tv_sec)*1000000000U+
        static_cast<uint64_t>(now.tv_nsec)+10000000000U;
    c.dwell_ms=120U; c.transition_budget_ms=20U; c.maximum_revisit_ms=3000U;
    c.feedback_age_ms=1000U; c.application_delay_ms=1000U; c.decay_ms=3000U;
    c.maximum_boost=3U; c.detector_queue_capacity=2U;
    c.active_threshold_dbfs=-38.0; c.target_count=1U;
    c.targets[0]={0U,UINT64_C(1000000000),0x12345678U,1U}; return c;
}
leo_scanner_source_requirements requirements() {
    leo_scanner_source_requirements r{};
    r.abi_version=LEO_SCANNER_SOURCE_ABI_VERSION;
    r.counter_authority=LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    r.position_semantics=LEO_SOURCE_POSITION_COHERENT_CURRENT;
    leo_source_capabilities caps{}; assert(source_capabilities(nullptr,&caps)==0);
    r.required_capability_flags=caps.flags;
    r.required_transition_flags=LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED|
        LEO_SOURCE_TRANSITION_TARGET_ATTESTED|
        LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED|
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    r.maximum_frequency_error_hz=2U; r.require_physical_counter_qualified=1U;
    return r;
}
leo_scanner_detector_binding binding(leo_native_glrt* context) {
    leo_scanner_detector_binding b{};
    b.abi_version=LEO_SCANNER_EXECUTION_ABI_VERSION;
    b.ops={context,detector_analyze,detector_capabilities};
    std::memset(b.configuration_digest,0x4c,sizeof(b.configuration_digest)); return b;
}

Events run(const std::vector<int16_t>& first,const std::vector<int16_t>& second,
           leo_scanner_detector_binding* bindings,uint32_t workers) {
    Source source; source.iq.reserve(first.size()+second.size());
    source.iq.resize(block_times*4U);
    source.iq.insert(source.iq.end(),first.begin(),first.end());
    source.iq.insert(source.iq.end(),second.begin(),second.end());
    leo_source_port port{}; assert(leo_source_port_init(&port,&source,&source_ops)==0);
    const leo_scanner_execution_options execution{
        LEO_SCANNER_EXECUTION_ABI_VERSION,workers,bindings};
    auto scan=config(); auto needed=requirements(); Events events;
    leo_scanner_source_stats stats{};
    const int status=leo_scanner_run_source_ex(&scan,&port,&needed,&execution,
        collect,&events,&stats);
    if (status) std::fprintf(stderr,"scanner status=%d stop=%u/%d visits=%llu\n",
        status,stats.scanner.stop_reason,stats.scanner.stop_status,
        static_cast<unsigned long long>(stats.scanner.visits_started));
    assert(status==0);
    assert(stats.scanner.visits_intact==2U && stats.scanner.detector_completed==2U &&
        !stats.scanner.detector_queue_drops);
    return events;
}

void strip_timing(leo_scanner_source_event& value) {
    value.event.detector_enqueued_monotonic_ns=0U;
    value.event.detector_started_monotonic_ns=0U;
    value.event.detector_finished_monotonic_ns=0U;
    value.event.detector_queue_ns=0U; value.event.detector_runtime_ns=0U;
}
} // namespace

int main(int argc,char** argv) {
    assert(argc==5);
    const auto exact=read_file<leo_native_glrt_complex>(argv[1]);
    const auto control=read_file<leo_native_glrt_complex>(argv[2]);
    const auto first=read_file<int16_t>(argv[3]);
    const auto second=read_file<int16_t>(argv[4]);
    assert(exact.size()==control.size() && first.size()==dwell_times*4U &&
        second.size()==dwell_times*4U);
    leo_native_glrt* contexts[2]{};
    for (auto& context:contexts)
        assert(leo_native_glrt_create_with_mode(&context,rate,exact.data(),
            control.data(),exact.size(),
            LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH)==0);
    auto first_binding=binding(contexts[0]);
    Events sequential=run(first,second,&first_binding,1U);
    leo_scanner_detector_binding concurrent_bindings[2]{binding(contexts[0]),
        binding(contexts[1])};
    Events concurrent=run(first,second,concurrent_bindings,2U);
    auto order=[](const leo_scanner_source_event& a,
                  const leo_scanner_source_event& b) {
        return std::tie(a.event.visit,a.event.kind,a.event.row_index,
            a.event.candidate_index)<std::tie(b.event.visit,b.event.kind,
            b.event.row_index,b.event.candidate_index);
    };
    std::sort(sequential.values.begin(),sequential.values.end(),order);
    std::sort(concurrent.values.begin(),concurrent.values.end(),order);
    assert(sequential.values.size()==concurrent.values.size());
    bool candidate_positive=false;
    for (size_t i=0;i<sequential.values.size();++i) {
        strip_timing(sequential.values[i]); strip_timing(concurrent.values[i]);
        candidate_positive|=sequential.values[i].event.kind==LEO_SCANNER_CANDIDATE;
        assert(std::memcmp(&sequential.values[i],&concurrent.values[i],
            sizeof(leo_scanner_source_event))==0);
    }
    assert(candidate_positive);
    for (auto* context:contexts) assert(leo_native_glrt_destroy(context)==0);
    return 0;
}
