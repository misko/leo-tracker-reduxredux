#include "ingest.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace leo::adaptive::ingest {
namespace {
constexpr std::uint64_t maximum_exact_counter_delta=UINT64_C(9007199254740992);

bool digest(const std::string& value) {
    return value.size()==71 && value.compare(0,7,"sha256:")==0 &&
        value.find_first_not_of("0123456789abcdef",7)==std::string::npos;
}

bool profile_name(const std::string& value) {
    if(value.empty() || value.size()>128) return false;
    return std::all_of(value.begin(),value.end(),[](unsigned char character) {
        return (character>='a' && character<='z') ||
            (character>='A' && character<='Z') ||
            (character>='0' && character<='9') || character=='-' ||
            character=='_' || character=='.' || character=='+';
    });
}

Status validate_event(const Authority& a,const leo_scanner_event& e,
                      const Target*& target,std::uint64_t& window,
                      std::uint64_t& support_end) {
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
    if(e.valid_start>std::numeric_limits<std::uint64_t>::max()-offset)
        return Status::invalid_event;
    window=e.valid_start+offset;
    const auto support_samples=static_cast<std::uint64_t>(a.sample_rate_hz/50);
    if(window>std::numeric_limits<std::uint64_t>::max()-support_samples)
        return Status::invalid_event;
    support_end=window+support_samples;
    target=&t;
    return Status::emitted;
}

void finish_source(const Authority& a,const leo_scanner_event& e,const Target& t,
                   std::uint64_t window,std::uint64_t anchor_counter,
                   std::int64_t anchor_utc_ns,double width,
                   ProjectionSource& source,FractionalCandidate& candidate) {
    source=ProjectionSource{a.input_digest,a.analysis_digest,a.generation,
        anchor_counter,window,e.visit,anchor_utc_ns,a.sample_rate_hz,
        static_cast<std::uint32_t>(e.probe_index),static_cast<std::uint32_t>(e.receiver_id),
        t.channel,t.upper_edge,t.actual_rf_hz,width,true};
    const auto& c=e.candidate;
    candidate=FractionalCandidate{e.candidate_index,c.epoch,
        c.fractional_epoch_offset_samples,c.fractional_tracking_cfo_hz,
        c.fractional_exact_score,c.fractional_control_score,c.fractional_margin,
        c.fractional_epoch_status==1};
}

Status prepare(const Authority& a, const timing::Timebase& clock,
               const leo_scanner_event& e, ProjectionSource& source,
               FractionalCandidate& candidate) {
    const Target* target=nullptr;
    std::uint64_t window=0,support_end=0;
    const auto validated=validate_event(a,e,target,window,support_end);
    if(validated!=Status::emitted) return validated;
    timing::Anchor anchor; double width;
    if(clock.anchor_for(a.generation,window,anchor,width,a.sample_rate_hz/50)!=timing::Status::ok ||
       anchor.sample_rate_hz!=a.sample_rate_hz)
        return Status::timing_unavailable;
    (void)support_end;
    finish_source(a,e,*target,window,anchor.counter,anchor.utc_ns,width,source,candidate);
    return Status::emitted;
}

Status prepare(const Authority& a,const HistoricalTimingProfile& timing,
               const leo_scanner_event& e,ProjectionSource& source,
               FractionalCandidate& candidate) {
    const Target* target=nullptr;
    std::uint64_t window=0,support_end=0;
    const auto validated=validate_event(a,e,target,window,support_end);
    if(validated!=Status::emitted) return validated;
    if(!valid_historical_timing_profile(a,timing)) return Status::invalid_event;
    if(window<timing.minimum_window_counter ||
       support_end>timing.maximum_support_end_counter)
        return Status::timing_unavailable;
    finish_source(a,e,*target,window,timing.anchor_counter,timing.anchor_utc_ns,
        static_cast<double>(timing.utc_bracket_width_ns),source,candidate);
    return Status::emitted;
}
}

bool valid_historical_timing_profile(
    const Authority& authority,const HistoricalTimingProfile& timing) noexcept {
    if(!timing.generation || timing.generation!=authority.generation ||
       !timing.sample_rate_hz || timing.sample_rate_hz!=authority.sample_rate_hz ||
       timing.anchor_utc_ns<=0 || !timing.utc_bracket_width_ns ||
       timing.utc_bracket_width_ns>maximum_exact_counter_delta ||
       timing.minimum_window_counter<timing.anchor_counter ||
       timing.maximum_support_end_counter<timing.minimum_window_counter ||
       timing.maximum_support_end_counter-timing.anchor_counter>
           maximum_exact_counter_delta ||
       !profile_name(timing.profile_name) || !digest(timing.profile_manifest_digest))
        return false;
    const auto lower=timing.utc_bracket_width_ns/2;
    const auto upper=timing.utc_bracket_width_ns-lower;
    return static_cast<std::uint64_t>(timing.anchor_utc_ns)>lower &&
        upper<=static_cast<std::uint64_t>(
            std::numeric_limits<std::int64_t>::max()-timing.anchor_utc_ns);
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

Status project_event(const Authority& a,const HistoricalTimingProfile& timing,
                     const leo_scanner_event& e,Observation& out) {
    PreparedProjection value;
    const auto prepared=prepare_event(a,timing,e,value);
    if(prepared!=Status::emitted) return prepared;
    try {
        return project(value.source,value.candidate,out) ? Status::emitted : Status::nonpassing;
    } catch(const std::invalid_argument&) { return Status::invalid_event; }
      catch(const std::overflow_error&) { return Status::invalid_event; }
}

Status prepare_event(const Authority& a,const HistoricalTimingProfile& timing,
                     const leo_scanner_event& e,PreparedProjection& out) {
    ProjectionSource source;
    FractionalCandidate candidate;
    const auto prepared=prepare(a,timing,e,source,candidate);
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
