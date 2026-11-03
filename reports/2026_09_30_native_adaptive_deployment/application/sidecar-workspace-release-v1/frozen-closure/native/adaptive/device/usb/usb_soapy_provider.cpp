#include "usb_soapy_provider.h"

#include <SoapySDR/Device.hpp>
#include <SoapySDR/Errors.hpp>
#include <SoapySDR/Formats.hpp>
#include <SoapySDR/Types.hpp>

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <fcntl.h>
#include <limits>
#include <stdexcept>
#include <string>
#include <sys/file.h>
#include <unistd.h>
#include <vector>

namespace {

constexpr uint32_t maximum_block_samples=1000000;

struct Capture {
    SoapySDR::Device *device=nullptr;
    SoapySDR::Stream *stream=nullptr;
    int lock_fd=-1;
    std::atomic<bool> cancelled{false};
    std::vector<int16_t> samples;
    uint32_t requested=0;
    uintptr_t token=0;
    uintptr_t leased_token=0;
    bool pending_overflow=false;
    bool pending_discontinuity=false;
    bool hardware_time=false;
    bool stream_active=false;
    bool originals_valid=false;
    double original_rate=0;
    double original_bandwidth=0;
    double original_frequency=0;
};

int cleanup(Capture *capture,bool restore) {
    int status=0;
    if (capture->stream && capture->device) {
        if (capture->stream_active) {
            try { if (capture->device->deactivateStream(capture->stream)!=0) status=-EIO; }
            catch (...) { status=-EIO; }
        }
        try { capture->device->closeStream(capture->stream); }
        catch (...) { status=-EIO; }
        capture->stream=nullptr;
    }
    if (restore && capture->device && capture->originals_valid) {
        try { capture->device->setSampleRate(SOAPY_SDR_RX,0,capture->original_rate); }
        catch (...) { status=-EIO; }
        try { capture->device->setBandwidth(SOAPY_SDR_RX,0,capture->original_bandwidth); }
        catch (...) { status=-EIO; }
        try { capture->device->setFrequency(SOAPY_SDR_RX,0,capture->original_frequency); }
        catch (...) { status=-EIO; }
        try {
            if (std::abs(capture->device->getSampleRate(SOAPY_SDR_RX,0)-
                    capture->original_rate)>0.5 ||
                std::abs(capture->device->getBandwidth(SOAPY_SDR_RX,0)-
                    capture->original_bandwidth)>0.5 ||
                std::abs(capture->device->getFrequency(SOAPY_SDR_RX,0)-
                    capture->original_frequency)>0.5) status=-EIO;
        } catch (...) { status=-EIO; }
    }
    if (capture->device) {
        try { SoapySDR::Device::unmake(capture->device); }
        catch (...) { status=-EIO; }
        capture->device=nullptr;
    }
    if (capture->lock_fd>=0) { ::close(capture->lock_fd); capture->lock_fd=-1; }
    return status;
}

bool bounds(const std::vector<SoapySDR::Range> &ranges,uint64_t &low,uint64_t &high) {
    if (ranges.empty()) return false;
    double minimum=std::numeric_limits<double>::infinity(), maximum=0;
    for (const auto &range:ranges) {
        minimum=std::min(minimum,range.minimum());
        maximum=std::max(maximum,range.maximum());
    }
    if (!std::isfinite(minimum) || !std::isfinite(maximum) || minimum<=0 ||
        maximum<minimum || maximum>static_cast<double>(UINT64_MAX)) return false;
    low=static_cast<uint64_t>(std::ceil(minimum));
    high=static_cast<uint64_t>(std::floor(maximum));
    return low<=high;
}

SoapySDR::Device *make_device(const char *selector) {
    return SoapySDR::Device::make(SoapySDR::KwargsFromString(selector));
}

int probe(void *,const char *selector,leo_usb_capabilities *out) {
    SoapySDR::Device *device=nullptr;
    try {
        device=make_device(selector);
        if (!device) return -ENODEV;
        leo_usb_capabilities c{};
        c.abi_version=LEO_USB_SOURCE_ABI_VERSION;
        c.sample_format_mask=LEO_USB_SAMPLE_FORMAT_CI16;
        c.flags=LEO_USB_CAP_EXCLUSIVE_OPEN|LEO_USB_CAP_CANCEL|
            LEO_USB_CAP_OVERFLOW_REPORTING|LEO_USB_CAP_RETUNE;
        c.max_receivers=static_cast<uint32_t>(std::min<size_t>(2,
            device->getNumChannels(SOAPY_SDR_RX)));
        c.max_samples_per_block=maximum_block_samples;
        c.counter_authority=LEO_USB_COUNTER_NONE;
        c.time_authority=device->hasHardwareTime() ? LEO_USB_TIME_DEVICE :
            LEO_USB_TIME_NONE;
        c.minimum_time_uncertainty_ns=c.time_authority==LEO_USB_TIME_DEVICE ?
            UINT64_MAX : 0;
        if (!c.max_receivers ||
            !bounds(device->getSampleRateRange(SOAPY_SDR_RX,0),
                c.minimum_sample_rate_hz,c.maximum_sample_rate_hz) ||
            !bounds(device->getBandwidthRange(SOAPY_SDR_RX,0),
                c.minimum_bandwidth_hz,c.maximum_bandwidth_hz) ||
            !bounds(device->getFrequencyRange(SOAPY_SDR_RX,0),
                c.minimum_frequency_hz,c.maximum_frequency_hz)) {
            SoapySDR::Device::unmake(device);
            return -ENOTSUP;
        }
        *out=c;
        SoapySDR::Device::unmake(device);
        return 0;
    } catch (...) {
        if (device) SoapySDR::Device::unmake(device);
        return -EIO;
    }
}

int open_exclusive(void *,const leo_usb_config *config,void **out) {
    Capture *capture=nullptr;
    try {
        capture=new Capture;
        /* A deliberately global cooperative lock prevents two instances of
         * this provider from sharing any USB SDR. Other applications must be
         * stopped by the operator; Soapy has no portable exclusivity query. */
        capture->lock_fd=::open("/tmp/leo-usb-soapy.lock",O_RDWR|O_CREAT|O_CLOEXEC,0600);
        if (capture->lock_fd<0 || flock(capture->lock_fd,LOCK_EX|LOCK_NB)<0) {
            const int error=(errno==EWOULDBLOCK || errno==EAGAIN) ? -EBUSY : -errno;
            if (capture->lock_fd>=0) ::close(capture->lock_fd);
            delete capture;
            return error;
        }
        capture->device=make_device(config->selector);
        if (!capture->device) throw std::runtime_error("device not found");
        capture->original_rate=capture->device->getSampleRate(SOAPY_SDR_RX,0);
        capture->original_bandwidth=capture->device->getBandwidth(SOAPY_SDR_RX,0);
        capture->original_frequency=capture->device->getFrequency(SOAPY_SDR_RX,0);
        capture->originals_valid=std::isfinite(capture->original_rate) &&
            std::isfinite(capture->original_bandwidth) &&
            std::isfinite(capture->original_frequency) &&
            capture->original_rate>0 && capture->original_bandwidth>0 &&
            capture->original_frequency>0;
        if (!capture->originals_valid)
            throw std::runtime_error("cannot snapshot original configuration");
        capture->device->setSampleRate(SOAPY_SDR_RX,0,config->sample_rate_hz);
        capture->device->setBandwidth(SOAPY_SDR_RX,0,config->analog_bandwidth_hz);
        capture->device->setFrequency(SOAPY_SDR_RX,0,config->center_frequency_hz);
        const double actual_rate=capture->device->getSampleRate(SOAPY_SDR_RX,0);
        const double actual_bandwidth=capture->device->getBandwidth(SOAPY_SDR_RX,0);
        const double actual_frequency=capture->device->getFrequency(SOAPY_SDR_RX,0);
        if (!std::isfinite(actual_rate) || !std::isfinite(actual_bandwidth) ||
            !std::isfinite(actual_frequency) || actual_rate<=0 ||
            actual_bandwidth<=0 || actual_frequency<=0 ||
            std::abs(actual_rate-config->sample_rate_hz)>0.5 ||
            std::abs(actual_bandwidth-config->analog_bandwidth_hz)>0.5 ||
            std::abs(actual_frequency-config->center_frequency_hz)>
                static_cast<double>(config->maximum_frequency_error_hz))
            throw std::runtime_error("configuration was coerced");
        const std::vector<size_t> channels{0};
        capture->stream=capture->device->setupStream(SOAPY_SDR_RX,
            SOAPY_SDR_CS16,channels);
        if (!capture->stream || capture->device->activateStream(capture->stream)!=0)
            throw std::runtime_error("stream activation failed");
        capture->stream_active=true;
        capture->requested=config->samples_per_block;
        capture->samples.resize(static_cast<size_t>(capture->requested)*2);
        capture->hardware_time=capture->device->hasHardwareTime();
        *out=capture;
        return 0;
    } catch (...) {
        if (capture) {
            (void)cleanup(capture,true);
            delete capture;
        }
        return -EIO;
    }
}

int acquire(void *,void *opaque,leo_usb_provider_block *out) {
    auto &capture=*static_cast<Capture *>(opaque);
    if (capture.leased_token) return -EBUSY;
    void *buffers[]={capture.samples.data()};
    for (;;) {
        if (capture.cancelled.load(std::memory_order_acquire)) return -ECANCELED;
        int flags=0; long long time_ns=0;
        int count;
        try {
            count=capture.device->readStream(capture.stream,buffers,
                capture.requested,flags,time_ns,100000);
        } catch (...) { return -EIO; }
        if (count==SOAPY_SDR_TIMEOUT) continue;
        if (count==SOAPY_SDR_OVERFLOW) { capture.pending_overflow=true; continue; }
        if (count<0) return -EIO;
        if (!count) continue;
        out->ci16=capture.samples.data();
        out->iq_bytes=static_cast<size_t>(count)*2*sizeof(int16_t);
        out->samples_per_receiver=static_cast<uint32_t>(count);
        out->receiver_count=1;
        out->flags=capture.pending_discontinuity ? LEO_USB_BLOCK_DISCONTINUITY : 0;
        if (capture.pending_overflow)
            out->flags|=LEO_USB_BLOCK_OVERFLOW_BEFORE|LEO_USB_BLOCK_DISCONTINUITY;
        out->counter_authority=LEO_USB_COUNTER_NONE;
        if ((flags&SOAPY_SDR_HAS_TIME) && capture.hardware_time && time_ns>=0) {
            out->time_authority=LEO_USB_TIME_DEVICE;
            out->first_time_ns=static_cast<uint64_t>(time_ns);
            out->time_uncertainty_ns=UINT64_MAX;
        }
        out->token=++capture.token;
        if (!out->token) out->token=++capture.token;
        capture.leased_token=out->token;
        capture.pending_overflow=false;
        capture.pending_discontinuity=false;
        return 0;
    }
}

int cancel(void *,void *opaque) {
    static_cast<Capture *>(opaque)->cancelled.store(true,std::memory_order_release);
    return 0;
}

int release(void *,void *opaque,uintptr_t token) {
    auto &capture=*static_cast<Capture *>(opaque);
    if (!capture.leased_token || capture.leased_token!=token) return -EINVAL;
    capture.leased_token=0;
    return 0;
}

int retune(void *,void *opaque,uint64_t frequency,leo_usb_provider_retune *out) {
    auto &capture=*static_cast<Capture *>(opaque);
    try {
        if (capture.device->deactivateStream(capture.stream)!=0)
            throw std::runtime_error("stream deactivation failed");
        capture.stream_active=false;
        capture.device->setFrequency(SOAPY_SDR_RX,0,frequency);
        const double actual=capture.device->getFrequency(SOAPY_SDR_RX,0);
        if (!std::isfinite(actual) || actual<=0 ||
            actual>static_cast<double>(std::numeric_limits<long long>::max()))
            throw std::runtime_error("invalid frequency readback");
        if (capture.device->activateStream(capture.stream)!=0)
            throw std::runtime_error("stream activation failed");
        capture.stream_active=true;
        capture.pending_discontinuity=true;
        out->actual_frequency_hz=static_cast<uint64_t>(std::llround(actual));
        /* Generic Soapy exposes neither a sample counter nor a portable
         * post-retune validity boundary. Leave both flags clear. */
        out->counter_authority=LEO_USB_COUNTER_NONE;
        out->time_authority=LEO_USB_TIME_NONE;
        out->time_uncertainty_ns=0;
        return 0;
    } catch (...) { return -EIO; }
}

int close_capture(void *,void *opaque) {
    auto *capture=static_cast<Capture *>(opaque);
    const int status=cleanup(capture,true);
    delete capture;
    return status;
}

const leo_usb_provider_ops provider={LEO_USB_SOURCE_ABI_VERSION,nullptr,probe,
    open_exclusive,acquire,cancel,release,retune,close_capture};

} // namespace

extern "C" const leo_usb_provider_ops *leo_usb_soapy_provider(void) {
    return &provider;
}
