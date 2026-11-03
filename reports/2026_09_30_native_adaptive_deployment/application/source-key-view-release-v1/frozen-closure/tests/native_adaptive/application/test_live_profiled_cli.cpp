#define main leo_portable_live_cli_test_main_not_used
#include "test_live_cli.cpp"
#undef main

#include <functional>
#include <iomanip>
#include <iostream>
#include <locale>
#include <sstream>

using leo::adaptive::SupportDerivation;
using leo::adaptive::SupportDerivationPort;
using leo::adaptive::SupportDerivationStatus;
using leo::adaptive::application::live::run_cli_with_providers_and_support;

namespace {

struct ProfileFake {
    SupportDerivationStatus status{SupportDerivationStatus::ok};
    std::uint64_t calls{};
};

std::string numeric(double value) {
    std::ostringstream text;
    text.imbue(std::locale::classic());
    text<<std::setprecision(17)<<value;
    return text.str();
}

SupportDerivationStatus derive_support(void* context,std::uint32_t rate,
        std::uint32_t samples,std::int64_t epoch,double offset,
        SupportDerivation* output) {
    auto& fake=*static_cast<ProfileFake*>(context);
    ++fake.calls;
    if (fake.status!=SupportDerivationStatus::ok) return fake.status;
    if (!output) return SupportDerivationStatus::invalid_input;
    output->numeric=leo::adaptive::fractional_support(rate,samples,epoch,offset);
    output->factorial_moment_lexemes={"1.0","0.0",
        numeric(output->numeric.moment2),numeric(output->numeric.moment3)};
    return SupportDerivationStatus::ok;
}

SupportDerivationPort port(ProfileFake& fake) {
    return {&fake,"test-profile-v1",
        "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        derive_support};
}

std::pair<int,std::string> capture_stdout(const std::function<int()>& callback) {
    std::ostringstream output;
    auto* previous=std::cout.rdbuf(output.rdbuf());
    const int status=callback();
    std::cout.flush();
    std::cout.rdbuf(previous);
    return {status,output.str()};
}

int invoke_profiled(std::vector<std::string>& values,const leo_local_provider_ops* source,
                    const leo_local_radio_prepare_ops* radio,
                    const SupportDerivationPort& support) {
    std::vector<char*> argv;
    for (auto& item:values) argv.push_back(item.data());
    return run_cli_with_providers_and_support(
        static_cast<int>(argv.size()),argv.data(),source,radio,support);
}

void no_args_reports_profile_without_providers() {
    ProfileFake fake;
    const auto support=port(fake);
    char name[]="leo-live-profiled";
    char* argv[]={name};
    const auto captured=capture_stdout([&] {
        return run_cli_with_providers_and_support(1,argv,nullptr,nullptr,support);
    });
    assert(captured.first==0 && fake.calls==0);
    assert(captured.second.find("leo-native-live-profiled-capabilities/v1")!=
        std::string::npos);
    assert(captured.second.find("\"support_profile_name\":\"test-profile-v1\"")!=
        std::string::npos);
    assert(captured.second.find("\"strict_pipeline_parity_qualified\":false")!=
        std::string::npos);
}

void malformed_no_args_profile_fails_before_output_or_providers() {
    ProfileFake fake;
    auto support=port(fake);
    support.profile_name="bad\"profile";
    char name[]="leo-live-profiled";
    char* argv[]={name};
    const auto captured=capture_stdout([&] {
        return run_cli_with_providers_and_support(1,argv,nullptr,nullptr,support);
    });
    assert(captured.first==2 && captured.second.empty() && fake.calls==0);
}

void profiled_capture(SupportDerivationStatus derivation_status) {
    reset_detector_stub();
    detector_stub.emit_candidate=true;
    detector_stub.scanner_status=0;
    SourceFake source;
    source.fail_capture_open=false;
    RadioFake radio;
    initialize_radio(radio);
    auto source_provider=source_ops(source);
    auto radio_provider=radio_ops(radio);
    std::string exact,control,tles;
    const auto directory=write_inputs(exact,control,tles);
    auto args=arguments(exact,control,tles);
    ProfileFake fake{derivation_status};
    const auto support=port(fake);
    const auto captured=capture_stdout([&] {
        return invoke_profiled(args,&source_provider,&radio_provider,support);
    });
    assert(fake.calls==1 && !source.counter_open && !source.firmware_active &&
        !source.lease && source.release_calls==1 && radio.restores==1 &&
        !std::memcmp(&radio.settings,&radio.original,sizeof(radio.original)));
    assert(captured.second.find("leo-native-live-profiled-summary/v1")!=
        std::string::npos);
    assert(captured.second.find("\"profile_prepared\":1")!=std::string::npos);
    if (derivation_status==SupportDerivationStatus::unavailable) {
        assert(captured.first==8);
        assert(captured.second.find("\"support_unavailable\":1")!=std::string::npos);
        assert(captured.second.find("\"support_unhealthy\":true")!=std::string::npos);
        assert(captured.second.find("\"support_profile_qualified\":false")!=
            std::string::npos);
    } else if (derivation_status==SupportDerivationStatus::invalid_input) {
        assert(captured.first==8);
        assert(captured.second.find("\"support_invalid\":1")!=std::string::npos);
        assert(captured.second.find("\"support_unhealthy\":true")!=std::string::npos);
        assert(captured.second.find("\"support_profile_qualified\":false")!=
            std::string::npos);
    } else {
        assert(captured.first==0);
        assert(captured.second.find("\"support_derived\":1")!=std::string::npos);
        assert(captured.second.find("\"support_profile_qualified\":true")!=
            std::string::npos);
    }
    cleanup_inputs(directory,exact,control,tles);
}

void quiet_capture_is_not_profile_qualified() {
    reset_detector_stub();
    detector_stub.scanner_status=0;
    SourceFake source;
    source.fail_capture_open=false;
    RadioFake radio;
    initialize_radio(radio);
    auto source_provider=source_ops(source);
    auto radio_provider=radio_ops(radio);
    std::string exact,control,tles;
    const auto directory=write_inputs(exact,control,tles);
    auto args=arguments(exact,control,tles);
    ProfileFake fake;
    const auto support=port(fake);
    const auto captured=capture_stdout([&] {
        return invoke_profiled(args,&source_provider,&radio_provider,support);
    });
    assert(captured.first==8 && fake.calls==0);
    assert(captured.second.find("\"accepted_candidates\":0")!=std::string::npos);
    assert(captured.second.find("\"support_profile_qualified\":false")!=
        std::string::npos);
    assert(!source.counter_open && !source.firmware_active && radio.restores==1);
    cleanup_inputs(directory,exact,control,tles);
}

}  // namespace

int main() {
    assert(leo_portable_live_cli_test_main_not_used()==0);
    no_args_reports_profile_without_providers();
    malformed_no_args_profile_fails_before_output_or_providers();
    profiled_capture(SupportDerivationStatus::ok);
    profiled_capture(SupportDerivationStatus::unavailable);
    profiled_capture(SupportDerivationStatus::invalid_input);
    quiet_capture_is_not_profile_qualified();
    return 0;
}
