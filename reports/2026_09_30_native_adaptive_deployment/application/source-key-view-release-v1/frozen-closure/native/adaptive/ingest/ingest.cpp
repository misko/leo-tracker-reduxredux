#include "ingest.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace leo::adaptive::ingest {
namespace {
Status prepare(const Authority& a, const timing::Timebase& clock,
               const leo_scanner_event& e, ProjectionSource& source,
               FractionalCandidate& candidate) {
    if(e.kind!=LEO_SCANNER_CANDIDATE) return Status::ignored;
    if(!a.generation || !a.sample_rate_hz || a.sample_rate_hz>10000000 ||
       a.sample_rate_hz%1000 || e.target>=a.targets.size() ||
       e.receiver_id<0 || e.receiver_id>1 || e.probe_index<0 ||
       e.candidate_index>=LEO_NATIVE_GLRT_MAX_CANDIDATES ||
       e.valid_end<=e.valid_start || e.detector_status)
        return Status::invalid_event;
    const auto& t=a.targets[e.target];
    // Source attestation validates immutable profile bytes. v0.59 Fast Lock
    // recall may update ALC, so its post-recall CRC need not equal prepared CRC.
    const bool attested=a.profile_authority==ProfileAuthority::live_attested &&
        t.profile_crc32 && e.attested_profile_crc32;
    const bool recorded=a.profile_authority==ProfileAuthority::historical_metadata &&
        !t.profile_crc32 && !e.attested_profile_crc32;
    if(t.profile!=e.profile || (!attested && !recorded) ||
       t.tuning_frequency_hz!=e.frequency_hz || t.channel<1 || t.channel>4 ||
       !std::isfinite(t.actual_rf_hz) || t.actual_rf_hz<=0)
        return Status::invalid_event;
    const std::uint64_t stride=static_cast<std::uint64_t>(a.sample_rate_hz)*120/1000;
    const auto offset=stride*static_cast<std::uint32_t>(e.probe_index);
    const auto duration=e.valid_end-e.valid_start;
    // Scanner v2 emits 20-ms probes at 120-ms offsets. Require complete
    // support inside an intact, bounded 120/240/360-ms detector dwell.
    if(duration!=stride && duration!=2*stride && duration!=3*stride)
        return Status::invalid_event;
    if(offset>duration || a.sample_rate_hz/50>duration-offset)
        return Status::invalid_event;
    const auto window=e.valid_start+offset;
    timing::Anchor anchor; double width;
    if(clock.anchor_for(a.generation,window,anchor,width,a.sample_rate_hz/50)!=timing::Status::ok ||
       anchor.sample_rate_hz!=a.sample_rate_hz)
        return Status::timing_unavailable;
    source=ProjectionSource{a.input_digest,a.analysis_digest,a.generation,
        anchor.counter,window,e.visit,anchor.utc_ns,a.sample_rate_hz,
        static_cast<std::uint32_t>(e.probe_index),static_cast<std::uint32_t>(e.receiver_id),
        t.channel,t.upper_edge,t.actual_rf_hz,width,true};
    const auto& c=e.candidate;
    candidate=FractionalCandidate{e.candidate_index,c.epoch,
        c.fractional_epoch_offset_samples,c.fractional_tracking_cfo_hz,
        c.fractional_exact_score,c.fractional_control_score,c.fractional_margin,
        c.fractional_epoch_status==1};
    return Status::emitted;
}
}

Status project_event(const Authority& a, const timing::Timebase& clock,
                     const leo_scanner_event& e, Observation& out) {
    PreparedProjection value;
    const auto prepared=prepare_event(a,clock,e,value);
    if(prepared!=Status::emitted) return prepared;
    try {
        return project(value.source,value.candidate,out) ? Status::emitted : Status::nonpassing;
    } catch(const std::invalid_argument&) { return Status::invalid_event; }
      catch(const std::overflow_error&) { return Status::invalid_event; }
}

Status prepare_event(const Authority& a,const timing::Timebase& clock,
                     const leo_scanner_event& e,PreparedProjection& out) {
    ProjectionSource source;
    FractionalCandidate candidate;
    const auto prepared=prepare(a,clock,e,source,candidate);
    if(prepared!=Status::emitted) return prepared;
    try {
        if(classify_projection_input(source,candidate)==ProjectionInputStatus::nonpassing)
            return Status::nonpassing;
    } catch(const std::invalid_argument&) { return Status::invalid_event; }
      catch(const std::overflow_error&) { return Status::invalid_event; }
    PreparedProjection value{std::move(source),candidate};
    out=std::move(value);
    return Status::emitted;
}

Status project_event(const Authority& a, const timing::Timebase& clock,
                     const leo_scanner_event& e, const SupportDerivationPort& port,
                     Observation& out, SupportDerivation& derivation) {
    PreparedProjection value;
    const auto prepared=prepare_event(a,clock,e,value);
    if(prepared!=Status::emitted) return prepared;
    try {
        const auto status=project(value.source,value.candidate,port,out,derivation);
        return status==SupportProjectionStatus::emitted ? Status::emitted :
            status==SupportProjectionStatus::nonpassing ? Status::nonpassing :
            Status::invalid_event;
    } catch(const std::invalid_argument&) { return Status::invalid_event; }
      catch(const std::overflow_error&) { return Status::invalid_event; }
}
}
