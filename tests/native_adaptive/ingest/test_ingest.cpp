#include "ingest.hpp"
#include <cassert>
#include <cstdio>
using namespace leo::adaptive;
namespace {
struct Fake { unsigned calls{};bool unavailable{}; };
SupportDerivationStatus derive(void* context,std::uint32_t rate,std::uint32_t samples,
    std::int64_t epoch,double offset,SupportDerivation* output) {
    auto& fake=*static_cast<Fake*>(context);++fake.calls;
    if(fake.unavailable) return SupportDerivationStatus::unavailable;
    if(!output) return SupportDerivationStatus::invalid_input;
    output->numeric=fractional_support(rate,samples,epoch,offset);
    char second[64],third[64];
    std::snprintf(second,sizeof(second),"%.17g",output->numeric.moment2);
    std::snprintf(third,sizeof(third),"%.17g",output->numeric.moment3);
    output->factorial_moment_lexemes={"1.0","0.0",second,third};
    return SupportDerivationStatus::ok;
}
}
int main() {
    const std::uint64_t counter=(UINT64_C(1)<<54)+123;
    const std::int64_t utc=1790740000000000000LL;
    timing::Timebase clock({2500000,1000000,10000000000ULL,10,100,8});
    assert(clock.begin(7)==timing::Status::ok);
    assert(clock.observe({10000,10200,counter,utc,utc+200,true})==timing::Status::ok);
    ingest::Authority authority{7,2500000,"sha256:"+std::string(64,'a'),
        "sha256:"+std::string(64,'b'),{{2,123,4,1500000000,11.2e9,true}}};
    leo_scanner_event e{}; e.kind=LEO_SCANNER_CANDIDATE; e.visit=4;
    e.valid_start=counter+1000; e.valid_end=e.valid_start+900000;
    e.profile=2;e.attested_profile_crc32=123;e.frequency_hz=1500000000;
    e.receiver_id=1;e.probe_index=2;e.candidate_index=3;
    auto& c=e.candidate;c.epoch=100;c.fractional_epoch_status=1;
    c.fractional_epoch_offset_samples=.25;c.fractional_tracking_cfo_hz=1234;
    c.fractional_exact_score=.2;c.fractional_control_score=.05;c.fractional_margin=.15;
    Observation out; assert(ingest::project_event(authority,clock,e,out)==ingest::Status::emitted);
    assert(out.generation==7 && out.channel==4 && out.actual_rf_hz==11.2e9);
    assert(out.measured_cfo_hz==1234 && out.probe_index==2);
    assert(out.support_start_utc_ns>utc+240000000 && out.support_end_utc_ns<utc+261000000);
    const auto saved=out;
    timing::Timebase prepared_clock({2500000,1000000,10000000000ULL,10,100,8});
    assert(prepared_clock.begin(7)==timing::Status::ok);
    assert(prepared_clock.observe({10000,10200,counter,utc,utc+200,true})==
        timing::Status::ok);
    ingest::PreparedProjection prepared;
    assert(ingest::prepare_event(authority,prepared_clock,e,prepared)==
        ingest::Status::emitted);
    assert(prepared_clock.begin(8)==timing::Status::ok);
    Observation after_clock_reset;
    assert(project(prepared.source,prepared.candidate,after_clock_reset));
    assert(after_clock_reset.candidate_id==saved.candidate_id &&
        after_clock_reset.support_start_utc_ns==saved.support_start_utc_ns &&
        after_clock_reset.support_center_utc_ns==saved.support_center_utc_ns &&
        after_clock_reset.support_end_utc_ns==saved.support_end_utc_ns &&
        after_clock_reset.moment2==saved.moment2 && after_clock_reset.moment3==saved.moment3);
    Fake fake;const std::string manifest="sha256:"+std::string(64,'c');
    const SupportDerivationPort port{&fake,"unit-profile",manifest,derive};
    SupportDerivation support;Observation explicit_out;
    assert(ingest::project_event(authority,clock,e,port,explicit_out,support)==
        ingest::Status::emitted);
    assert(fake.calls==1 && explicit_out.candidate_id==saved.candidate_id &&
        explicit_out.support_center_utc_ns==saved.support_center_utc_ns &&
        explicit_out.moment2==saved.moment2 && explicit_out.moment3==saved.moment3);
    const auto explicit_id=explicit_out.candidate_id;
    fake.unavailable=true;
    assert(ingest::project_event(authority,clock,e,port,explicit_out,support)==
        ingest::Status::invalid_event);
    assert(fake.calls==2 && explicit_out.candidate_id==explicit_id);
    fake.unavailable=false;
    const auto calls_before_invalid=fake.calls;
    c.epoch=-1;
    assert(ingest::project_event(authority,clock,e,port,explicit_out,support)==
        ingest::Status::invalid_event);
    assert(fake.calls==calls_before_invalid && explicit_out.candidate_id==explicit_id);
    c.epoch=100;
    // Detector completion/queue timing must never influence physical UTC.
    e.detector_finished_monotonic_ns=UINT64_MAX;e.detector_queue_ns=999999999;
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::emitted);
    assert(out.candidate_id==saved.candidate_id && out.support_center_utc_ns==saved.support_center_utc_ns);
    e.probe_index=3;assert(ingest::project_event(authority,clock,e,out)==ingest::Status::invalid_event);
    e.probe_index=2;e.attested_profile_crc32=124;
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::emitted);
    e.attested_profile_crc32=0;
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::invalid_event);
    e.attested_profile_crc32=123;e.profile=3;
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::invalid_event);
    e.profile=2;++e.frequency_hz;
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::invalid_event);
    --e.frequency_hz;
    authority.profile_authority=ingest::ProfileAuthority::historical_metadata;
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::invalid_event);
    authority.targets[0].profile_crc32=0;e.attested_profile_crc32=0;
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::emitted);
    authority.profile_authority=ingest::ProfileAuthority::live_attested;
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::invalid_event);
    authority.targets[0].profile_crc32=123;
    e.attested_profile_crc32=123;c.fractional_epoch_status=2;
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::nonpassing);
    const auto calls_before_nonpassing=fake.calls;
    assert(ingest::project_event(authority,clock,e,port,explicit_out,support)==
        ingest::Status::nonpassing);
    assert(fake.calls==calls_before_nonpassing);
    assert(out.candidate_id==saved.candidate_id);
    c.fractional_epoch_status=1;authority.generation=8;
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::timing_unavailable);
    authority.generation=7;authority.input_digest="invalid";
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::invalid_event);
    e.kind=LEO_SCANNER_QUEUE_DROP;
    assert(ingest::project_event(authority,clock,e,out)==ingest::Status::ignored);
}
