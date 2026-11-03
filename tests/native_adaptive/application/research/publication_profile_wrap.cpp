#include "live.hpp"
#include "../pipeline/pipeline.hpp"
#include "../tracking/tracking.hpp"

#include <array>
#include <chrono>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <vector>

namespace {
using Clock=std::chrono::steady_clock;
using Time=Clock::time_point;
using leo::adaptive::online::Status;

struct Record {
    std::uint64_t sequence{};
    std::size_t candidates{},tracks{},location_tracks{};
    int session_status{},coordinator_status{};
    Time session_start{},coordinator_start{},reconstruct_start{},reconstruct_end{},
        location_start{},location_end{},coordinator_end{},session_end{};
};

constexpr std::size_t maximum_records=128;
std::array<Record,maximum_records> records{};
std::size_t record_count{};
std::size_t active_record=maximum_records;
bool output_registered{};

std::uint64_t elapsed(Time end,Time start) {
    if (end==Time{} || start==Time{} || end<start) return 0;
    return static_cast<std::uint64_t>(std::chrono::duration_cast<
        std::chrono::nanoseconds>(end-start).count());
}

void write_output() {
    FILE* output=stderr;
    const char* path=std::getenv("LEO_PUBLICATION_PROFILE_PATH");
    if (path && *path) {
        output=std::fopen(path,"w");
        if (!output) output=stderr;
    }
    for (std::size_t index=0;index<record_count;++index) {
        const auto& value=records[index];
        const auto session=elapsed(value.session_end,value.session_start);
        const auto coordinator=elapsed(value.coordinator_end,value.coordinator_start);
        const auto materialization=elapsed(value.reconstruct_start,value.coordinator_start);
        const auto tracking=elapsed(value.reconstruct_end,value.reconstruct_start);
        const auto between=elapsed(value.location_start,value.reconstruct_end);
        const auto location=elapsed(value.location_end,value.location_start);
        const auto snapshot=elapsed(value.coordinator_end,value.location_end);
        const auto outer=session>=coordinator ? session-coordinator : 0;
        const auto partition=materialization+tracking+between+location+snapshot;
        const auto coordinator_unattributed=coordinator>=partition ? coordinator-partition : 0;
        const auto session_partition=outer+coordinator;
        const auto session_unattributed=session>=session_partition ?
            session-session_partition : 0;
        const bool complete=value.session_status==static_cast<int>(Status::ok) &&
            value.coordinator_status==static_cast<int>(Status::ok) && value.candidates &&
            value.reconstruct_start!=Time{} && value.reconstruct_end!=Time{} &&
            value.location_start!=Time{} && value.location_end!=Time{};
        std::fprintf(output,
            "{\"schema\":\"leo-publication-stage-profile/v1\","
            "\"sequence\":%" PRIu64 ",\"session_status\":%d,"
            "\"coordinator_status\":%d,\"candidates\":%zu,"
            "\"tracks\":%zu,\"location_tracks\":%zu,"
            "\"session_total_ns\":%" PRIu64 ","
            "\"coordinator_total_ns\":%" PRIu64 ","
            "\"session_wrapper_ns\":%" PRIu64 ","
            "\"candidate_graph_materialization_ns\":%" PRIu64 ","
            "\"tracking_reconstruct_ns\":%" PRIu64 ","
            "\"tracking_to_location_ns\":%" PRIu64 ","
            "\"make_location_tracks_ns\":%" PRIu64 ","
            "\"snapshot_publication_cleanup_ns\":%" PRIu64 ","
            "\"coordinator_partition_ns\":%" PRIu64 ","
            "\"coordinator_unattributed_ns\":%" PRIu64 ","
            "\"session_partition_ns\":%" PRIu64 ","
            "\"session_unattributed_ns\":%" PRIu64 ","
            "\"stages_complete\":%s}\n",
            value.sequence,value.session_status,value.coordinator_status,
            value.candidates,value.tracks,value.location_tracks,session,coordinator,
            outer,materialization,tracking,between,location,snapshot,partition,
            coordinator_unattributed,session_partition,session_unattributed,
            complete ? "true" : "false");
    }
    if (output!=stderr) std::fclose(output);
}

void ensure_output() {
    if (!output_registered) {
        if (std::atexit(write_output)!=0) std::abort();
        output_registered=true;
    }
}
} // namespace

extern "C" Status real_session_publish(
    leo::adaptive::application::Session*,
    std::shared_ptr<const leo::adaptive::online::Snapshot>*)
    asm("__real__ZN3leo8adaptive11application7Session7publishEPSt10shared_ptrIKNS0_6online8SnapshotEE");

extern "C" Status wrap_session_publish(
    leo::adaptive::application::Session* owner,
    std::shared_ptr<const leo::adaptive::online::Snapshot>* snapshot)
    asm("__wrap__ZN3leo8adaptive11application7Session7publishEPSt10shared_ptrIKNS0_6online8SnapshotEE");

extern "C" Status wrap_session_publish(
    leo::adaptive::application::Session* owner,
    std::shared_ptr<const leo::adaptive::online::Snapshot>* snapshot) {
    ensure_output();
    const std::size_t before=record_count;
    const Time started=Clock::now();
    const Status status=real_session_publish(owner,snapshot);
    const Time ended=Clock::now();
    if (record_count==before && record_count<maximum_records) {
        auto& value=records[record_count++];
        value.sequence=record_count;
        value.session_start=started;value.session_end=ended;
        value.session_status=static_cast<int>(status);
    } else if (record_count>before) {
        auto& value=records[before];
        value.session_start=started;value.session_end=ended;
        value.session_status=static_cast<int>(status);
    }
    return status;
}

#if __SIZEOF_LONG__ == 8
#define LEO_COORDINATOR_PUBLISH_REAL \
    "__real__ZN3leo8adaptive6online11Coordinator7publishElPSt10shared_ptrIKNS1_8SnapshotEE"
#define LEO_COORDINATOR_PUBLISH_WRAP \
    "__wrap__ZN3leo8adaptive6online11Coordinator7publishElPSt10shared_ptrIKNS1_8SnapshotEE"
#else
#define LEO_COORDINATOR_PUBLISH_REAL \
    "__real__ZN3leo8adaptive6online11Coordinator7publishExPSt10shared_ptrIKNS1_8SnapshotEE"
#define LEO_COORDINATOR_PUBLISH_WRAP \
    "__wrap__ZN3leo8adaptive6online11Coordinator7publishExPSt10shared_ptrIKNS1_8SnapshotEE"
#endif

extern "C" Status real_coordinator_publish(
    leo::adaptive::online::Coordinator*,std::int64_t,
    std::shared_ptr<const leo::adaptive::online::Snapshot>*)
    asm(LEO_COORDINATOR_PUBLISH_REAL);

extern "C" Status wrap_coordinator_publish(
    leo::adaptive::online::Coordinator* owner,std::int64_t watermark,
    std::shared_ptr<const leo::adaptive::online::Snapshot>* snapshot)
    asm(LEO_COORDINATOR_PUBLISH_WRAP);

extern "C" Status wrap_coordinator_publish(
    leo::adaptive::online::Coordinator* owner,std::int64_t watermark,
    std::shared_ptr<const leo::adaptive::online::Snapshot>* snapshot) {
    ensure_output();
    if (record_count>=maximum_records) return real_coordinator_publish(owner,watermark,snapshot);
    const std::size_t index=record_count++;
    auto& value=records[index];
    value.sequence=index+1;value.coordinator_start=Clock::now();
    active_record=index;
    const Status status=real_coordinator_publish(owner,watermark,snapshot);
    active_record=maximum_records;
    value.coordinator_end=Clock::now();
    value.coordinator_status=static_cast<int>(status);
    return status;
}

extern "C" leo::adaptive::tracking::Result real_reconstruct(
    const std::vector<leo::adaptive::tracking::Candidate>&,
    const leo::adaptive::tracking::Config&,
    const leo::adaptive::tracking::LaneExecution&)
    asm("__real__ZN3leo8adaptive8tracking11reconstructERKSt6vectorINS1_9CandidateESaIS3_EERKNS1_6ConfigERKNS1_13LaneExecutionE");

extern "C" leo::adaptive::tracking::Result wrap_reconstruct(
    const std::vector<leo::adaptive::tracking::Candidate>& candidates,
    const leo::adaptive::tracking::Config& config,
    const leo::adaptive::tracking::LaneExecution& execution)
    asm("__wrap__ZN3leo8adaptive8tracking11reconstructERKSt6vectorINS1_9CandidateESaIS3_EERKNS1_6ConfigERKNS1_13LaneExecutionE");

extern "C" leo::adaptive::tracking::Result wrap_reconstruct(
    const std::vector<leo::adaptive::tracking::Candidate>& candidates,
    const leo::adaptive::tracking::Config& config,
    const leo::adaptive::tracking::LaneExecution& execution) {
    Record* value=active_record<record_count ? &records[active_record] : nullptr;
    if (value) { value->candidates=candidates.size();value->reconstruct_start=Clock::now(); }
    auto result=real_reconstruct(candidates,config,execution);
    if (value) { value->reconstruct_end=Clock::now();value->tracks=result.tracks.size(); }
    return result;
}

extern "C" leo::adaptive::pipeline::LocationTrackBatch real_make_location_tracks(
    const leo::adaptive::tracking::Result&,
    const leo::adaptive::pipeline::GraphAuthority&)
    asm("__real__ZN3leo8adaptive8pipeline20make_location_tracksERKNS0_8tracking6ResultERKNS1_14GraphAuthorityE");

extern "C" leo::adaptive::pipeline::LocationTrackBatch wrap_make_location_tracks(
    const leo::adaptive::tracking::Result& tracks,
    const leo::adaptive::pipeline::GraphAuthority& graph)
    asm("__wrap__ZN3leo8adaptive8pipeline20make_location_tracksERKNS0_8tracking6ResultERKNS1_14GraphAuthorityE");

extern "C" leo::adaptive::pipeline::LocationTrackBatch wrap_make_location_tracks(
    const leo::adaptive::tracking::Result& tracks,
    const leo::adaptive::pipeline::GraphAuthority& graph) {
    Record* value=active_record<record_count ? &records[active_record] : nullptr;
    if (value) value->location_start=Clock::now();
    auto result=real_make_location_tracks(tracks,graph);
    if (value) { value->location_end=Clock::now();value->location_tracks=result.records.size(); }
    return result;
}
