#include "live.hpp"
#include "vendor/adi-rx-counter.h"

#include <algorithm>
#include <array>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <string>
#include <stdexcept>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

using leo::adaptive::application::live::run_cli_with_providers;

namespace {
struct DetectorStubState {
    unsigned creates{},destroys{},capability_calls{},scanner_calls{};
    unsigned fail_create_call{};
    unsigned scanner_workers{};
    std::array<std::uint8_t,32> scanner_digest{};
    bool process_serialized{};
    bool emit_candidate{};
    int scanner_status{-EIO};
} detector_stub;

void reset_detector_stub() { detector_stub=DetectorStubState{}; }

struct SourceFake {
    bool counter_open{}, firmware_active{};
    bool fail_capture_open{true},lease{};
    unsigned capture_open_calls{}, release_calls{};
    std::uint64_t counter{51000U};
    std::vector<std::uint8_t> raw;
};
SourceFake* active_source;

int counter_open() {
    assert(active_source && !active_source->counter_open);
    active_source->counter_open=true;
    return 17;
}
int counter_close(int fd) {
    assert(active_source && active_source->counter_open && fd==17);
    active_source->counter_open=false;
    return 0;
}
int ioctl_call(int fd,unsigned long request,void* argument) {
    assert(fd==17 && active_source);
    if (request==ADI_RX_COUNTER_IOC_GET_SCAN_CAPS) {
        auto* caps=static_cast<adi_rx_counter_scan_caps*>(argument);
        caps->magic=ADI_RX_COUNTER_MAGIC;
        caps->version=ADI_RX_COUNTER_SCAN_VERSION;
        caps->size=sizeof(*caps);
        caps->features=ADI_RX_COUNTER_SCAN_FEATURES;
        caps->maximum_profiles=ADI_RX_COUNTER_SCAN_MAX_PROFILES;
        caps->source_counter_bits=32;
        caps->frequency_resolution_hz=2;
        return 0;
    }
    if (request==ADI_RX_COUNTER_IOC_ACQUIRE) {
        active_source->firmware_active=true;
        return 0;
    }
    if (request==ADI_RX_COUNTER_IOC_CONFIGURE_SCAN) return 0;
    if (request==ADI_RX_COUNTER_IOC_SCAN_SNAPSHOT) {
        static_cast<adi_rx_counter_scan_snapshot*>(argument)->counter=
            active_source->counter;
        return 0;
    }
    if (request==ADI_RX_COUNTER_IOC_RELEASE_SCAN) {
        auto* receipt=static_cast<adi_rx_counter_scan_release*>(argument);
        receipt->frequency_hz=915000000;
        receipt->counter_before=100;
        receipt->counter_after=101;
        active_source->firmware_active=false;
        ++active_source->release_calls;
        return 0;
    }
    errno=ENOTTY;
    return -1;
}
int capture_open(void* context,const leo_local_config* config,void** out) {
    auto& fake=*static_cast<SourceFake*>(context);
    assert(config->sample_rate_hz==2500000 && config->samples_per_block==50000 &&
        config->receiver_count==2 && config->profile_count==1);
    ++fake.capture_open_calls;
    if (fake.fail_capture_open) return -EIO;
    fake.raw.assign(8U+static_cast<std::size_t>(config->samples_per_block)*8U,0U);
    const std::uint64_t wire=fake.counter-config->samples_per_block+2U;
    for (unsigned i=0;i<8U;++i)
        fake.raw[i]=static_cast<std::uint8_t>(wire>>(8U*i));
    *out=&fake; return 0;
}
int fake_acquire(void* context,void* capture,leo_local_provider_block* out) {
    auto& fake=*static_cast<SourceFake*>(context); assert(capture==&fake && !fake.lease);
    fake.lease=true; out->raw=fake.raw.data(); out->raw_bytes=fake.raw.size();
    out->token=1U; return 0;
}
int unused_capture(void*,void*) { return 0; }
int fake_release(void* context,void*,uintptr_t token) {
    auto& fake=*static_cast<SourceFake*>(context); assert(fake.lease && token==1U);
    fake.lease=false; return 0;
}

leo_local_provider_ops source_ops(SourceFake& fake) {
    active_source=&fake;
    return {&fake,capture_open,fake_acquire,unused_capture,fake_release,
        unused_capture,counter_open,counter_close,ioctl_call};
}

struct RadioFake {
    leo_local_radio_settings settings{},original{};
    std::uint32_t buffers{4};
    std::uint8_t slots[8][LEO_LOCAL_RADIO_PROFILE_BYTES]{};
    int active{-1};
    unsigned opens{},closes{},restores{};
};
int radio_open(void* context,void** out) {
    auto* radio=static_cast<RadioFake*>(context); ++radio->opens; *out=radio; return 0;
}
int radio_close(void* context,void* opaque) {
    auto* radio=static_cast<RadioFake*>(context); assert(opaque==radio);
    ++radio->closes; return 0;
}
int read_settings(void* context,void* opaque,leo_local_radio_settings* out) {
    auto* radio=static_cast<RadioFake*>(context); assert(opaque==radio);
    *out=radio->settings; return 0;
}
int configure(void* context,void* opaque,const leo_local_radio_prepare_config* config,
              leo_local_radio_settings* out) {
    auto* radio=static_cast<RadioFake*>(context); assert(opaque==radio);
    radio->settings.sample_rate_hz=config->sample_rate_hz;
    radio->settings.capture_sample_rate_hz=config->sample_rate_hz;
    radio->settings.analog_bandwidth_hz=config->analog_bandwidth_hz;
    radio->settings.receiver_mask=3;
    for (unsigned i=0;i<2;++i) {
        std::strcpy(radio->settings.gain_mode[i],"manual");
        radio->settings.gain_millidb[i]=config->manual_gain_millidb;
    }
    *out=radio->settings; return 0;
}
int restore(void* context,void* opaque,const leo_local_radio_settings* expected,
            leo_local_radio_settings* out) {
    auto* radio=static_cast<RadioFake*>(context); assert(opaque==radio);
    radio->settings=*expected; radio->active=-1; *out=radio->settings;
    ++radio->restores; return 0;
}
int get_buffers(void* context,void*,std::uint32_t* out) {
    *out=static_cast<RadioFake*>(context)->buffers; return 0;
}
int set_buffers(void* context,void*,std::uint32_t requested,std::uint32_t* out) {
    auto* radio=static_cast<RadioFake*>(context); radio->buffers=requested;
    *out=requested; return 0;
}
int read_active(void* context,void*,std::int32_t* out) {
    *out=static_cast<RadioFake*>(context)->active; return 0;
}
int write_frequency(void* context,void*,std::uint64_t value) {
    auto* radio=static_cast<RadioFake*>(context);
    radio->settings.center_frequency_hz=value; radio->active=-1; return 0;
}
int read_frequency(void* context,void*,std::uint64_t* out) {
    *out=static_cast<RadioFake*>(context)->settings.center_frequency_hz; return 0;
}
int store_profile(void* context,void*,std::uint32_t profile,std::uint8_t* out) {
    auto* radio=static_cast<RadioFake*>(context);
    for (unsigned i=0;i<LEO_LOCAL_RADIO_PROFILE_BYTES;++i)
        radio->slots[profile][i]=static_cast<std::uint8_t>(profile*29+i+1);
    std::memcpy(out,radio->slots[profile],LEO_LOCAL_RADIO_PROFILE_BYTES); return 0;
}
int save_profile(void* context,void*,std::uint32_t profile,std::uint8_t* out) {
    auto* radio=static_cast<RadioFake*>(context);
    std::memcpy(out,radio->slots[profile],LEO_LOCAL_RADIO_PROFILE_BYTES); return 0;
}
int load_profile(void* context,void*,std::uint32_t profile,const std::uint8_t* in) {
    auto* radio=static_cast<RadioFake*>(context);
    std::memcpy(radio->slots[profile],in,LEO_LOCAL_RADIO_PROFILE_BYTES); return 0;
}
int recall(void* context,void*,std::uint32_t profile) {
    auto* radio=static_cast<RadioFake*>(context); radio->active=static_cast<int>(profile);
    radio->slots[profile][15]^=0x55; return 0;
}
leo_local_radio_prepare_ops radio_ops(RadioFake& radio) {
    return {&radio,radio_open,radio_close,read_settings,configure,restore,get_buffers,
        set_buffers,read_active,write_frequency,read_frequency,store_profile,
        save_profile,load_profile,recall};
}

void initialize_radio(RadioFake& radio) {
    radio.settings.center_frequency_hz=915000000;
    radio.settings.sample_rate_hz=1000000;
    radio.settings.capture_sample_rate_hz=1000000;
    radio.settings.analog_bandwidth_hz=1200000;
    radio.settings.receiver_mask=1;
    std::strcpy(radio.settings.gain_mode[0],"slow_attack");
    std::strcpy(radio.settings.gain_mode[1],"slow_attack");
    radio.original=radio.settings;
}

std::string write_inputs(std::string& exact,std::string& control,std::string& tles) {
    const char* scratch=std::getenv("TMPDIR");
    std::string pattern=std::string(scratch && *scratch ? scratch : "/tmp")+
        "/leo-live-cli.XXXXXX";
    std::vector<char> writable(pattern.begin(),pattern.end());
    writable.push_back('\0');
    char* made=mkdtemp(writable.data()); assert(made);
    std::string directory=made;
    exact=directory+"/exact.bin"; control=directory+"/control.bin";
    tles=directory+"/catalogue.txt";
    const std::vector<leo_native_glrt_complex> values((2500000U+375U)/750U);
    for (const auto& path:{exact,control}) {
        std::ofstream out(path,std::ios::binary);
        out.write(reinterpret_cast<const char*>(values.data()),
            static_cast<std::streamsize>(values.size()*sizeof(values[0])));
        out.close();
        if(!out) throw std::runtime_error("cannot write test template: "+path);
    }
    std::ofstream tle(tles);
    tle<<"1\n"
       <<"1 A0001U 19074B   26270.09087237  .00034246  00000-0  33881-3 0  9999\n"
       <<"2 A0001  53.1459 294.7156 0002678  78.6558 281.4759 15.65554847380103\n";
    tle.close();
    if(!tle) throw std::runtime_error("cannot write test TLE: "+tles);
    return directory;
}

std::vector<std::string> arguments(const std::string& exact,const std::string& control,
                                   const std::string& tles) {
    const std::string digest_a="sha256:"+std::string(64,'a');
    const std::string digest_b="sha256:"+std::string(64,'b');
    return {"leo-live","--capture","--duration-ms","1000","--maximum-visits","1",
        "--active-dwell-ms","120","--block-ms","20","--maximum-detector-latency-ms",
        "100","--publication-ms","1000","--history-seconds","10","--generation","1",
        "--exact-template",exact,"--control-template",control,"--tle-catalogue",tles,
        "--input-digest",digest_a,"--analysis-digest",digest_b,"--session-id","fake",
        "--search-origin","0","0","--search-radius-km","1","--search-region-km","2",
        "--search-level-km","2","--search-point-budget","1","--search-slice-points","1",
        "--target","0","2400000000","1","lower","11200000000"};
}

int invoke(std::vector<std::string>& values,const leo_local_provider_ops* source,
           const leo_local_radio_prepare_ops* radio) {
    std::vector<char*> argv; for (auto& item:values) argv.push_back(item.data());
    return run_cli_with_providers(static_cast<int>(argv.size()),argv.data(),source,radio);
}

void cleanup_inputs(const std::string& directory,const std::string& exact,
                    const std::string& control,const std::string& tles) {
    unlink(exact.c_str()); unlink(control.c_str()); unlink(tles.c_str());
    rmdir(directory.c_str());
}

void no_args_does_not_touch_providers() {
    reset_detector_stub();
    char name[]="leo-live"; char* argv[]={name};
    assert(run_cli_with_providers(1,argv,nullptr,nullptr)==0);
}

void history_profiles_parse_before_provider_use() {
    reset_detector_stub();
    SourceFake source; RadioFake radio; initialize_radio(radio);
    auto source_provider=source_ops(source); auto radio_provider=radio_ops(radio);
    std::string exact,control,tles;
    const auto directory=write_inputs(exact,control,tles);
    auto args=arguments(exact,control,tles);
    const auto found=std::find(args.begin(),args.end(),"--history-seconds");
    assert(found!=args.end() && found+1!=args.end());
    *(found+1)="600";
    assert(invoke(args,nullptr,nullptr)==3);
    *(found+1)="300";
    assert(invoke(args,&source_provider,&radio_provider)==2);
    assert(!source.counter_open && !source.capture_open_calls && !radio.opens);
    cleanup_inputs(directory,exact,control,tles);
}

void preparation_failure_restores_same_lifecycle() {
    reset_detector_stub();
    SourceFake source; RadioFake radio; initialize_radio(radio);
    auto source_provider=source_ops(source); auto radio_provider=radio_ops(radio);
    std::string exact,control,tles;
    const auto directory=write_inputs(exact,control,tles);
    auto args=arguments(exact,control,tles);
    assert(invoke(args,&source_provider,&radio_provider)==5);
    assert(source.capture_open_calls==1 && source.release_calls==1);
    assert(!source.counter_open && !source.firmware_active);
    assert(radio.restores==1 && radio.buffers==4 && radio.active==-1);
    assert(!std::memcmp(&radio.settings,&radio.original,sizeof(radio.original)));
    assert(radio.opens==3 && radio.closes==3);
    assert(detector_stub.creates==1U && detector_stub.destroys==1U &&
        detector_stub.capability_calls==1U && !detector_stub.scanner_calls);
    cleanup_inputs(directory,exact,control,tles);
}

void bad_tle_identity_fails_before_provider_mutation() {
    reset_detector_stub();
    SourceFake source; RadioFake radio; initialize_radio(radio);
    auto source_provider=source_ops(source); auto radio_provider=radio_ops(radio);
    std::string exact,control,tles;
    const auto directory=write_inputs(exact,control,tles);
    auto expect_bad=[&](const std::string& body) {
        { std::ofstream output(tles); output<<body; }
        auto args=arguments(exact,control,tles); bool threw=false;
        try { (void)invoke(args,&source_provider,&radio_provider); }
        catch (const std::runtime_error&) { threw=true; }
        assert(threw && !source.counter_open && !source.capture_open_calls &&
            !radio.opens && !radio.restores);
    };
    expect_bad("1\n"
        "1 A0001U 19074B   26270.09087237  .00034246  00000-0  33881-3 0  9999\n"
        "2 A0002  53.1459 294.7156 0002678  78.6558 281.4759 15.65554847380103\n");
    expect_bad("2\n"
        "1 A0001U 19074B   26270.09087237  .00034246  00000-0  33881-3 0  9999\n"
        "2 A0001  53.1459 294.7156 0002678  78.6558 281.4759 15.65554847380103\n"
        "1 A0001U 19074B   26270.09087237  .00034246  00000-0  33881-3 0  9999\n"
        "2 A0001  53.1459 294.7156 0002678  78.6558 281.4759 15.65554847380103\n");
    cleanup_inputs(directory,exact,control,tles);
}

void execution_budget_rejects_before_detector_or_provider() {
    reset_detector_stub();
    SourceFake source; RadioFake radio; initialize_radio(radio);
    auto source_provider=source_ops(source); auto radio_provider=radio_ops(radio);
    std::string exact,control,tles;
    const auto directory=write_inputs(exact,control,tles);
    auto expect_bad=[&](std::initializer_list<const char*> extra) {
        auto args=arguments(exact,control,tles);
        for (const char* value:extra) args.emplace_back(value);
        assert(invoke(args,&source_provider,&radio_provider)==2);
        assert(!detector_stub.creates && !source.counter_open &&
            !source.capture_open_calls && !radio.opens);
    };
    expect_bad({"--cpu-workers","2","--detector-workers","2",
        "--analysis-workers","1"});
    expect_bad({"--cpu-workers","5"});
    expect_bad({"--analysis-workers","0"});
    expect_bad({"--detector-workers","1","--detector-workers","1"});
    cleanup_inputs(directory,exact,control,tles);
}

void partial_detector_creation_and_capability_failure_precede_radio() {
    SourceFake source; RadioFake radio; initialize_radio(radio);
    auto source_provider=source_ops(source); auto radio_provider=radio_ops(radio);
    std::string exact,control,tles;
    const auto directory=write_inputs(exact,control,tles);
    auto args=arguments(exact,control,tles);
    args.insert(args.end(),{"--cpu-workers","3","--detector-workers","2",
        "--analysis-workers","1"});

    reset_detector_stub(); detector_stub.fail_create_call=2U;
    assert(invoke(args,&source_provider,&radio_provider)==4);
    assert(detector_stub.creates==2U && detector_stub.destroys==1U &&
        !detector_stub.capability_calls && !source.counter_open && !radio.opens);

    reset_detector_stub(); detector_stub.process_serialized=true;
    assert(invoke(args,&source_provider,&radio_provider)==4);
    assert(detector_stub.creates==2U && detector_stub.destroys==2U &&
        detector_stub.capability_calls==1U && !source.counter_open && !radio.opens);
    cleanup_inputs(directory,exact,control,tles);
}

void valid_worker_counts_reach_versioned_scanner_options() {
    reset_detector_stub();
    SourceFake source; source.fail_capture_open=false;
    RadioFake radio; initialize_radio(radio);
    auto source_provider=source_ops(source); auto radio_provider=radio_ops(radio);
    std::string exact,control,tles;
    const auto directory=write_inputs(exact,control,tles);
    auto args=arguments(exact,control,tles);
    args.insert(args.end(),{"--cpu-workers","4","--detector-workers","2",
        "--analysis-workers","2"});
    assert(invoke(args,&source_provider,&radio_provider)==8);
    assert(detector_stub.creates==2U && detector_stub.destroys==2U &&
        detector_stub.capability_calls==2U && detector_stub.scanner_calls==1U &&
        detector_stub.scanner_workers==2U);
    assert(!source.counter_open && !source.firmware_active && !source.lease &&
        radio.restores==1U);
    const auto first_digest=detector_stub.scanner_digest;
    {
        std::fstream changed(exact,std::ios::in|std::ios::out|std::ios::binary);
        const char byte=1; changed.write(&byte,1); assert(changed.good());
    }
    reset_detector_stub(); SourceFake second_source; second_source.fail_capture_open=false;
    RadioFake second_radio; initialize_radio(second_radio);
    auto second_source_provider=source_ops(second_source);
    auto second_radio_provider=radio_ops(second_radio);
    assert(invoke(args,&second_source_provider,&second_radio_provider)==8);
    assert(detector_stub.scanner_calls==1U &&
        detector_stub.scanner_digest!=first_digest);
    cleanup_inputs(directory,exact,control,tles);
}
} // namespace

extern "C" {
struct leo_native_glrt { unsigned id; };
int leo_native_glrt_create_with_mode(leo_native_glrt** out,std::uint32_t,
    const leo_native_glrt_complex*,const leo_native_glrt_complex*,std::size_t count,
    std::uint32_t) {
    static leo_native_glrt contexts[4]{}; assert(count==(2500000U+375U)/750U);
    ++detector_stub.creates;
    if (detector_stub.creates==detector_stub.fail_create_call) return -ENOMEM;
    contexts[detector_stub.creates-1U].id=detector_stub.creates;
    *out=&contexts[detector_stub.creates-1U]; return 0;
}
int leo_native_glrt_destroy(leo_native_glrt*) { ++detector_stub.destroys; return 0; }
int leo_native_glrt_analyze(leo_native_glrt*,const std::int16_t*,std::size_t,
    std::uint32_t,std::uint32_t,leo_native_glrt_result*) { return -EIO; }
int leo_native_glrt_get_capabilities(leo_native_glrt_capabilities* out) {
    ++detector_stub.capability_calls; *out={};
    out->abi_version=LEO_NATIVE_GLRT_ABI_VERSION; out->receiver_count=2U;
    out->probe_ms=20U; out->process_serialized=detector_stub.process_serialized;
    out->fractional_epoch_mode_available=1U; return 0;
}
int leo_scanner_run_timed_ex(const leo_scanner_config* config,leo_local_source*,
    const leo_scanner_counter_ops* counter,const leo_scanner_execution_options* execution,
    leo_scanner_event_sink sink,void* sink_context,leo_scanner_stats* stats) {
    ++detector_stub.scanner_calls; assert(execution);
    detector_stub.scanner_workers=execution->detector_worker_count;
    assert(execution->abi_version==LEO_SCANNER_EXECUTION_ABI_VERSION &&
        execution->detectors);
    for (std::uint32_t i=0;i<execution->detector_worker_count;++i) {
        assert(execution->detectors[i].abi_version==LEO_SCANNER_EXECUTION_ABI_VERSION);
        std::uint8_t nonzero=0;
        for (auto byte:execution->detectors[i].configuration_digest) nonzero|=byte;
        assert(nonzero);
        if (i) assert(!std::memcmp(execution->detectors[0].configuration_digest,
            execution->detectors[i].configuration_digest,32U));
        if (i) assert(execution->detectors[0].ops.context!=
            execution->detectors[i].ops.context);
    }
    std::copy_n(execution->detectors[0].configuration_digest,32U,
        detector_stub.scanner_digest.begin());
    if (detector_stub.emit_candidate) {
        assert(config && counter && counter->snapshot && sink && stats && config->target_count==1);
        assert(active_source);
        const std::uint64_t now=active_source->counter;
        leo_scanner_event event{};
        event.kind=LEO_SCANNER_CANDIDATE;
        event.visit=1;
        event.valid_start=now;
        event.valid_end=now+static_cast<std::uint64_t>(config->sample_rate_hz)*120U/1000U;
        event.target=0;
        event.profile=config->targets[0].profile;
        event.attested_profile_crc32=config->targets[0].profile_crc32;
        event.frequency_hz=config->targets[0].frequency_hz;
        event.receiver_id=0;
        event.probe_index=0;
        event.candidate_index=0;
        timespec timestamp{};
        assert(clock_gettime(CLOCK_MONOTONIC,&timestamp)==0);
        const auto monotonic=static_cast<std::uint64_t>(timestamp.tv_sec)*1000000000ULL+
            static_cast<std::uint64_t>(timestamp.tv_nsec);
        event.detector_enqueued_monotonic_ns=monotonic;
        event.detector_started_monotonic_ns=monotonic;
        event.detector_finished_monotonic_ns=monotonic;
        event.candidate.epoch=100;
        event.candidate.fractional_epoch_status=1;
        event.candidate.fractional_epoch_offset_samples=0;
        event.candidate.fractional_tracking_cfo_hz=125;
        event.candidate.fractional_exact_score=1;
        event.candidate.fractional_control_score=0;
        event.candidate.fractional_margin=1;
        sink(sink_context,&event);
        stats->visits_started=1;
        stats->visits_intact=1;
        stats->detector_accepted=1;
        stats->detector_completed=1;
        stats->detector_candidates=1;
    }
    return detector_stub.scanner_status;
}
}

int main() {
    no_args_does_not_touch_providers();
    history_profiles_parse_before_provider_use();
    preparation_failure_restores_same_lifecycle();
    bad_tle_identity_fails_before_provider_mutation();
    execution_budget_rejects_before_detector_or_provider();
    partial_detector_creation_and_capability_failure_precede_radio();
    valid_worker_counts_reach_versioned_scanner_options();
    return 0;
}
