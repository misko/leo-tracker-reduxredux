#include "usb_source.h"
#include "runtime.hpp"

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#define CHECK(x) do { if (!(x)) { std::cerr << __FILE__ << ':' << __LINE__ \
    << ": check failed: " #x "\n"; std::exit(1); } } while (0)

namespace {

struct Fake {
    leo_usb_capabilities caps{};
    std::vector<int16_t> samples;
    uint32_t receivers=1;
    uint32_t chunk=3;
    uint64_t counter=100;
    size_t position=0;
    int probes=0, opens=0, acquires=0, releases=0, closes=0, cancels=0, retunes=0;
    int open_error=0, acquire_error=0, release_error=0, close_error=0;
    bool overflow=false, regression=false;
};

leo_usb_capabilities standard_caps() {
    leo_usb_capabilities c{};
    c.abi_version=LEO_USB_SOURCE_ABI_VERSION;
    c.sample_format_mask=LEO_USB_SAMPLE_FORMAT_CI16;
    c.flags=LEO_USB_CAP_EXCLUSIVE_OPEN|LEO_USB_CAP_CANCEL|
        LEO_USB_CAP_OVERFLOW_REPORTING|LEO_USB_CAP_RETUNE|
        LEO_USB_CAP_SIMULTANEOUS_RX|LEO_USB_CAP_COHERENT_RX;
    c.max_receivers=2;
    c.max_samples_per_block=1000000;
    c.counter_authority=LEO_USB_COUNTER_PROVIDER_EXACT;
    c.time_authority=LEO_USB_TIME_DEVICE;
    c.minimum_time_uncertainty_ns=50;
    c.minimum_sample_rate_hz=1000;
    c.maximum_sample_rate_hz=10000000;
    c.minimum_bandwidth_hz=1000;
    c.maximum_bandwidth_hz=10000000;
    c.minimum_frequency_hz=1000000;
    c.maximum_frequency_hz=6000000000ULL;
    return c;
}

leo_usb_config config(uint32_t receivers=1) {
    leo_usb_config c{};
    c.abi_version=LEO_USB_SOURCE_ABI_VERSION;
    c.selector="fake=0";
    c.sample_rate_hz=7500000;
    c.analog_bandwidth_hz=6000000;
    c.samples_per_block=900000;
    c.receiver_count=receivers;
    c.center_frequency_hz=1710000000;
    c.maximum_frequency_error_hz=2;
    c.maximum_time_uncertainty_ns=100;
    return c;
}

int probe(void *opaque,const char *,leo_usb_capabilities *out) {
    auto &f=*static_cast<Fake *>(opaque); ++f.probes; *out=f.caps; return 0;
}
int open_exclusive(void *opaque,const leo_usb_config *,void **capture) {
    auto &f=*static_cast<Fake *>(opaque); ++f.opens;
    if (f.open_error) return f.open_error;
    *capture=&f; return 0;
}
int acquire(void *opaque,void *,leo_usb_provider_block *out) {
    auto &f=*static_cast<Fake *>(opaque); ++f.acquires;
    if (f.acquire_error) return f.acquire_error;
    const size_t available=f.samples.size()/(f.receivers*2)-f.position;
    if (!available) return -ENODATA;
    const uint32_t count=static_cast<uint32_t>(std::min<size_t>(available,f.chunk));
    out->ci16=f.samples.data()+f.position*f.receivers*2;
    out->iq_bytes=static_cast<size_t>(count)*f.receivers*2*sizeof(int16_t);
    out->samples_per_receiver=count;
    out->receiver_count=f.receivers;
    out->counter_authority=f.caps.counter_authority;
    out->time_authority=f.caps.time_authority;
    out->first_counter=f.counter+f.position;
    if (f.regression && f.position) out->first_counter=1;
    if (f.caps.time_authority!=LEO_USB_TIME_NONE) {
        out->first_time_ns=1000000+f.position*100;
        out->time_uncertainty_ns=f.caps.minimum_time_uncertainty_ns;
    }
    out->flags=f.overflow ? LEO_USB_BLOCK_OVERFLOW_BEFORE : 0;
    out->token=f.position+7;
    f.position+=count;
    return 0;
}
int cancel(void *opaque,void *) { ++static_cast<Fake *>(opaque)->cancels; return 0; }
int release(void *opaque,void *,uintptr_t) {
    auto &f=*static_cast<Fake *>(opaque); ++f.releases; return f.release_error;
}
int retune(void *opaque,void *,uint64_t frequency,leo_usb_provider_retune *out) {
    auto &f=*static_cast<Fake *>(opaque); ++f.retunes;
    out->actual_frequency_hz=frequency+1;
    out->flags=LEO_USB_RETUNE_VALID_COUNTER|LEO_USB_RETUNE_VALID_TIME;
    out->counter_authority=LEO_USB_COUNTER_PROVIDER_EXACT;
    out->time_authority=LEO_USB_TIME_DEVICE;
    out->valid_counter=f.counter+f.position;
    out->valid_time_ns=1000000+f.position*100;
    out->time_uncertainty_ns=50;
    return 0;
}
int close_capture(void *opaque,void *) {
    auto &f=*static_cast<Fake *>(opaque); ++f.closes; return f.close_error;
}
leo_usb_provider_ops ops(Fake &f) {
    return {LEO_USB_SOURCE_ABI_VERSION,&f,probe,open_exclusive,acquire,cancel,
        release,retune,close_capture};
}

void fill(Fake &f,uint32_t times=12) {
    f.samples.resize(static_cast<size_t>(times)*f.receivers*2);
    for (size_t i=0;i<f.samples.size();++i) f.samples[i]=static_cast<int16_t>(i);
}

void test_preflight_before_mutation() {
    Fake f; f.caps=standard_caps(); f.caps.flags&=~LEO_USB_CAP_COHERENT_RX;
    auto p=ops(f); auto c=config(2); leo_usb_source *source=nullptr;
    CHECK(leo_usb_source_open(&c,&p,&source)==-ENOTSUP);
    CHECK(!source && f.probes==1 && f.opens==0);
    c.receiver_count=1; c.require_exact_counter=1;
    f.caps.counter_authority=LEO_USB_COUNTER_PROVIDER_ESTIMATED;
    CHECK(leo_usb_source_open(&c,&p,&source)==-ENOTSUP);
    CHECK(f.opens==0);
    f.caps=standard_caps(); f.caps.flags&=~LEO_USB_CAP_EXCLUSIVE_OPEN;
    CHECK(leo_usb_source_open(&c,&p,&source)==-ENOTSUP);
    CHECK(f.opens==0);
    f.caps=standard_caps(); c.require_device_time=1; c.maximum_time_uncertainty_ns=49;
    CHECK(leo_usb_source_open(&c,&p,&source)==-ENOTSUP);
    CHECK(f.opens==0);
    c.maximum_time_uncertainty_ns=100;
    f.caps=standard_caps(); f.open_error=-EBUSY;
    CHECK(leo_usb_source_open(&c,&p,&source)==-EBUSY);
    CHECK(f.opens==1);
}

void test_exact_lifecycle_and_gap() {
    Fake f; f.caps=standard_caps(); fill(f); auto p=ops(f); auto c=config();
    c.require_exact_counter=1; c.require_device_time=1;
    leo_usb_source *source=nullptr; CHECK(leo_usb_source_open(&c,&p,&source)==0);
    leo_usb_block a{}; CHECK(leo_usb_source_next(source,&a)==0);
    CHECK(a.first_counter==100 && a.stream_ordinal==0 &&
        a.counter_authority==LEO_USB_COUNTER_PROVIDER_EXACT &&
        !(a.flags&LEO_USB_BLOCK_GAP_EXACT) && a.missing_samples_before==0);
    leo_usb_block busy{}; CHECK(leo_usb_source_next(source,&busy)==-EBUSY);
    leo_usb_provider_retune tr{};
    CHECK(leo_usb_source_retune(source,1720000000,&tr)==-EBUSY);
    CHECK(leo_usb_source_release(source,&a)==0 && !a.ci16);
    f.counter+=2;
    leo_usb_block b{}; CHECK(leo_usb_source_next(source,&b)==0);
    CHECK(b.first_counter==105 && b.missing_samples_before==2 &&
        (b.flags&LEO_USB_BLOCK_GAP_EXACT) &&
        (b.flags&LEO_USB_BLOCK_DISCONTINUITY));
    CHECK(leo_usb_source_release(source,&b)==0);
    CHECK(leo_usb_source_retune(source,1720000000,&tr)==0);
    CHECK(tr.actual_frequency_hz==1720000001 && f.retunes==1);
    CHECK(leo_usb_source_cancel(source)==0 && f.cancels==1);
    CHECK(leo_usb_source_close(source)==0 && f.closes==1 && f.releases==2);
}

void test_software_ordinal_is_not_exact() {
    Fake f; f.caps=standard_caps(); f.caps.counter_authority=LEO_USB_COUNTER_NONE;
    f.caps.time_authority=LEO_USB_TIME_NONE; f.caps.minimum_time_uncertainty_ns=0;
    fill(f,7); auto p=ops(f); auto c=config(); leo_usb_source *source=nullptr;
    CHECK(leo_usb_source_open(&c,&p,&source)==0);
    leo_usb_block a{},b{}; CHECK(leo_usb_source_next(source,&a)==0);
    CHECK(a.counter_authority==LEO_USB_COUNTER_SOFTWARE_DELIVERED &&
        a.first_counter==0 && a.stream_ordinal==0 &&
        !(a.flags&LEO_USB_BLOCK_GAP_EXACT));
    CHECK(leo_usb_source_release(source,&a)==0);
    CHECK(leo_usb_source_next(source,&b)==0);
    CHECK(b.first_counter==3 && b.stream_ordinal==3 &&
        b.missing_samples_before==0);
    CHECK(leo_usb_source_close(source)==0); // releases b during close
    CHECK(f.releases==2);
}

void test_faults_release_provider_block() {
    Fake f; f.caps=standard_caps(); fill(f,8); f.chunk=4; auto p=ops(f);
    auto c=config(); leo_usb_source *source=nullptr;
    CHECK(leo_usb_source_open(&c,&p,&source)==0);
    leo_usb_block b{}; CHECK(leo_usb_source_next(source,&b)==0);
    CHECK(leo_usb_source_release(source,&b)==0);
    f.regression=true;
    CHECK(leo_usb_source_next(source,&b)==-EPROTO);
    CHECK(f.releases==2);
    CHECK(leo_usb_source_next(source,&b)==-EIO);
    CHECK(leo_usb_source_close(source)==0);
}

void test_overflow_and_release_failure() {
    Fake f; f.caps=standard_caps(); fill(f); f.overflow=true; f.release_error=-EIO;
    auto p=ops(f); auto c=config(); leo_usb_source *source=nullptr;
    CHECK(leo_usb_source_open(&c,&p,&source)==0);
    leo_usb_block b{}; CHECK(leo_usb_source_next(source,&b)==0);
    CHECK(b.flags&LEO_USB_BLOCK_OVERFLOW_BEFORE);
    CHECK(leo_usb_source_release(source,&b)==-EIO);
    CHECK(leo_usb_source_next(source,&b)==-EIO);
    CHECK(leo_usb_source_close(source)==0);
}

void test_provider_errors_and_malformed_block() {
    Fake f; f.caps=standard_caps(); fill(f); f.acquire_error=-ETIMEDOUT;
    auto p=ops(f); auto c=config(); leo_usb_source *source=nullptr;
    CHECK(leo_usb_source_open(&c,&p,&source)==0);
    leo_usb_block b{}; CHECK(leo_usb_source_next(source,&b)==-ETIMEDOUT);
    CHECK(f.releases==0);
    f.acquire_error=0; f.receivers=2;
    CHECK(leo_usb_source_next(source,&b)==-EPROTO);
    CHECK(f.releases==1);
    f.close_error=-ENODEV;
    CHECK(leo_usb_source_close(source)==-ENODEV);
}

void test_ds9_window_parity(const char *path) {
    std::ifstream in(path,std::ios::binary);
    CHECK(in.good());
    in.seekg(0,std::ios::end); const auto bytes=in.tellg(); in.seekg(0);
    CHECK(bytes==7200000);
    Fake f; f.caps=standard_caps(); f.receivers=2; f.chunk=77777;
    f.counter=1247924293582ULL;
    f.samples.resize(static_cast<size_t>(bytes)/sizeof(int16_t));
    in.read(reinterpret_cast<char *>(f.samples.data()),bytes); CHECK(in.good());
    auto p=ops(f); auto c=config(2); c.require_exact_counter=1;
    leo_usb_source *source=nullptr; CHECK(leo_usb_source_open(&c,&p,&source)==0);
    std::vector<int16_t> window;
    leo::adaptive::WindowAssembler assembler(7500000,2,
        [&](const leo::adaptive::Window &w) {
            CHECK(w.first==f.counter && w.samples==150000 && w.visit.receivers==2);
            window.assign(w.iq,w.iq+static_cast<size_t>(w.samples)*4);
        });
    assembler.begin({1,276,f.counter,f.counter+900000,7500000,2,1710000000.0});
    for (;;) {
        leo_usb_block b{}; const int status=leo_usb_source_next(source,&b);
        if (status==-ENODATA) break;
        CHECK(status==0 && b.counter_authority==LEO_USB_COUNTER_PROVIDER_EXACT);
        assembler.push(b.first_counter,b.ci16,b.samples_per_receiver);
        CHECK(leo_usb_source_release(source,&b)==0);
    }
    assembler.finish(); const auto stats=assembler.stats();
    CHECK(stats.emitted==1 && stats.missing==0 && stats.discontinuities==0);
    CHECK(window.size()==600000);
    CHECK(std::memcmp(window.data(),f.samples.data(),window.size()*sizeof(int16_t))==0);
    CHECK(leo_usb_source_close(source)==0);
}

void test_ds9_single_receiver_software_ordinal(const char *path) {
    std::ifstream in(path,std::ios::binary);
    CHECK(in.good());
    std::vector<int16_t> dual(3600000);
    in.read(reinterpret_cast<char *>(dual.data()),7200000);
    CHECK(in.good() && in.peek()==std::char_traits<char>::eof());
    for (size_t receiver=0;receiver<2;++receiver) {
        Fake f; f.caps=standard_caps(); f.receivers=1; f.chunk=77777;
        f.caps.max_receivers=1;
        f.caps.flags&=~(LEO_USB_CAP_SIMULTANEOUS_RX|LEO_USB_CAP_COHERENT_RX);
        f.caps.counter_authority=LEO_USB_COUNTER_NONE;
        f.caps.time_authority=LEO_USB_TIME_NONE;
        f.caps.minimum_time_uncertainty_ns=0;
        for (size_t sample=0;sample<dual.size()/4;++sample) {
            f.samples.push_back(dual[sample*4+receiver*2]);
            f.samples.push_back(dual[sample*4+receiver*2+1]);
        }
        auto p=ops(f); auto c=config(1); leo_usb_source *source=nullptr;
        CHECK(leo_usb_source_open(&c,&p,&source)==0);
        std::vector<int16_t> window;
        // This is a delivered-ordinal window, not a hardware-counter/UTC claim.
        // The saved fixture's rate is not an RTL-SDR capability claim either.
        leo::adaptive::WindowAssembler assembler(7500000,1,
            [&](const leo::adaptive::Window &w) {
                CHECK(w.first==0 && w.samples==150000 && w.visit.receivers==1);
                window.assign(w.iq,w.iq+static_cast<size_t>(w.samples)*2);
            });
        assembler.begin({1,276,0,900000,7500000,1,1710000000.0});
        uint64_t delivered=0;
        for (;;) {
            leo_usb_block b{}; const int status=leo_usb_source_next(source,&b);
            if (status==-ENODATA) break;
            CHECK(status==0 && b.receiver_count==1);
            CHECK(b.counter_authority==LEO_USB_COUNTER_SOFTWARE_DELIVERED);
            CHECK(b.first_counter==delivered && b.stream_ordinal==delivered);
            CHECK(b.time_authority==LEO_USB_TIME_NONE && b.first_time_ns==0);
            CHECK(!(b.flags&LEO_USB_BLOCK_GAP_EXACT));
            CHECK(b.iq_bytes==static_cast<size_t>(b.samples_per_receiver)*4);
            assembler.push(b.stream_ordinal,b.ci16,b.samples_per_receiver);
            delivered+=b.samples_per_receiver;
            CHECK(leo_usb_source_release(source,&b)==0);
        }
        assembler.finish(); const auto stats=assembler.stats();
        CHECK(delivered==900000 && stats.emitted==1 && stats.missing==0 &&
            stats.discontinuities==0 && window.size()==300000);
        CHECK(std::memcmp(window.data(),f.samples.data(),window.size()*sizeof(int16_t))==0);
        CHECK(leo_usb_source_close(source)==0 && f.closes==1);
        CHECK(f.releases==12);
    }
}

} // namespace

int main(int argc,char **argv) {
    if (argc!=2) {
        std::cerr << "usage: test-usb-source DS9-CI16\n";
        return 2;
    }
    test_preflight_before_mutation();
    test_exact_lifecycle_and_gap();
    test_software_ordinal_is_not_exact();
    test_faults_release_provider_block();
    test_overflow_and_release_failure();
    test_provider_errors_and_malformed_block();
    test_ds9_window_parity(argv[1]);
    test_ds9_single_receiver_software_ordinal(argv[1]);
    std::cout << "usb source: unit lifecycle and DS9 window parity pass\n";
}
