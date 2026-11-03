#include "usb_soapy_provider.h"

#include <cerrno>
#include <cstdlib>
#include <iostream>

static uint64_t required_integer(const char *name) {
    const char *text=std::getenv(name); char *end=nullptr;
    if (!text || !*text) { std::cerr << "missing " << name << '\n'; std::exit(2); }
    const auto value=std::strtoull(text,&end,10);
    if (!value || !end || *end) { std::cerr << "invalid " << name << '\n'; std::exit(2); }
    return value;
}

int main() {
    const char *selector=std::getenv("LEO_USB_SDR_SELECTOR");
    const char *allow=std::getenv("LEO_USB_ALLOW_CAPTURE");
    if (!selector || !*selector || !allow || std::string(allow)!="yes") {
        std::cerr << "hardware test requires LEO_USB_SDR_SELECTOR and "
            "LEO_USB_ALLOW_CAPTURE=yes\n";
        return 2;
    }
    leo_usb_capabilities caps{};
    auto *provider=leo_usb_soapy_provider();
    int status=leo_usb_source_probe(selector,provider,&caps);
    if (status) { std::cerr << "probe failed: " << status << '\n'; return 1; }
    leo_usb_config c{}; c.abi_version=LEO_USB_SOURCE_ABI_VERSION; c.selector=selector;
    c.sample_rate_hz=required_integer("LEO_USB_SAMPLE_RATE_HZ");
    c.analog_bandwidth_hz=required_integer("LEO_USB_BANDWIDTH_HZ");
    c.samples_per_block=required_integer("LEO_USB_BLOCK_SAMPLES");
    c.receiver_count=1;
    c.center_frequency_hz=required_integer("LEO_USB_FREQUENCY_HZ");
    c.maximum_frequency_error_hz=required_integer("LEO_USB_FREQUENCY_ERROR_HZ");
    leo_usb_source *source=nullptr;
    status=leo_usb_source_open(&c,provider,&source);
    if (status) { std::cerr << "open failed: " << status << '\n'; return 1; }
    leo_usb_block block{}; status=leo_usb_source_next(source,&block);
    const uint32_t samples=block.samples_per_receiver;
    const uint32_t counter_authority=block.counter_authority;
    const uint32_t time_authority=block.time_authority;
    if (!status) status=leo_usb_source_release(source,&block);
    const int close_status=leo_usb_source_close(source);
    if (!status) status=close_status;
    if (status) { std::cerr << "capture failed: " << status << '\n'; return 1; }
    std::cout << "samples=" << samples
        << " counter_authority=" << counter_authority
        << " time_authority=" << time_authority << '\n';
    return 0;
}
