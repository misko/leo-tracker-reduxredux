#include "live.hpp"
#include "scanner.h"
#include "vendor/adi-rx-counter.h"

#include <algorithm>
#include <array>
#include <cassert>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <exception>
#include <thread>
#include <vector>

using namespace leo::adaptive;
using namespace leo::adaptive::application::live;

namespace {
constexpr std::uint32_t rate = 2'500'000U;
constexpr std::uint32_t block_samples = 50'000U;
constexpr std::size_t block_bytes = 8U + static_cast<std::size_t>(block_samples) * 8U;
constexpr std::uint64_t counter_origin = (UINT64_C(1) << 54) + 100'000U;
constexpr std::int64_t utc_origin = INT64_C(1790740000000000000);

void put64(std::uint8_t* output, std::uint64_t value) {
    for (unsigned i = 0; i < 8U; ++i)
        output[i] = static_cast<std::uint8_t>(value >> (8U * i));
}

struct Device {
    std::vector<std::uint8_t> raw = std::vector<std::uint8_t>(block_bytes);
    std::uint64_t next_first{counter_origin};
    std::uint32_t counter{};
    std::uint64_t profiles[8]{};
    std::uint32_t crcs[8]{};
    std::uintptr_t sequence{};
    bool capture_open{}, lease{}, owned{}, cancelled{};
};
Device* active_device{};

int capture_open(void* context, const leo_local_config* config, void** output) {
    auto& device = *static_cast<Device*>(context);
    assert(config && output && config->sample_rate_hz == rate &&
        config->samples_per_block == block_samples && config->receiver_count == 2U);
    if (device.capture_open) return -EBUSY;
    device.capture_open = true;
    *output = &device;
    return 0;
}

int capture_acquire(void* context, void* capture, leo_local_provider_block* output) {
    auto& device = *static_cast<Device*>(context);
    assert(capture == &device && output && !device.lease);
    if (device.cancelled) return -ECANCELED;
    // This provider deliberately delivers one physical 20 ms block every 20 ms.
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
    put64(device.raw.data(), device.next_first + 2U);
    auto* iq = reinterpret_cast<std::int16_t*>(device.raw.data() + 8U);
    for (std::uint32_t i = 0; i < block_samples; ++i) {
        iq[4U * i] = 2000;
        iq[4U * i + 1U] = -2000;
        iq[4U * i + 2U] = 17;
        iq[4U * i + 3U] = -19;
    }
    device.counter = static_cast<std::uint32_t>(device.next_first + block_samples);
    device.next_first += block_samples;
    device.lease = true;
    output->raw = device.raw.data();
    output->raw_bytes = device.raw.size();
    output->token = ++device.sequence;
    return 0;
}

int capture_cancel(void* context, void*) {
    static_cast<Device*>(context)->cancelled = true;
    return 0;
}
int capture_release(void* context, void* capture, std::uintptr_t) {
    auto& device = *static_cast<Device*>(context);
    assert(capture == &device && device.lease);
    device.lease = false;
    return 0;
}
int capture_close(void* context, void* capture) {
    auto& device = *static_cast<Device*>(context);
    assert(capture == &device && !device.lease);
    device.capture_open = false;
    return 0;
}
int counter_open() { return 19; }
int counter_close(int fd) { assert(fd == 19); return 0; }

int ioctl_call(int fd, unsigned long request, void* argument) {
    assert(fd == 19 && active_device);
    auto& device = *active_device;
    if (request == ADI_RX_COUNTER_IOC_GET_SCAN_CAPS) {
        auto* value = static_cast<adi_rx_counter_scan_caps*>(argument);
        value->magic = ADI_RX_COUNTER_MAGIC;
        value->version = ADI_RX_COUNTER_SCAN_VERSION;
        value->size = sizeof(*value);
        value->features = ADI_RX_COUNTER_SCAN_FEATURES;
        value->maximum_profiles = 8U;
        value->source_counter_bits = 32U;
        value->frequency_resolution_hz = 2U;
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_ACQUIRE) {
        if (device.owned) { errno = EBUSY; return -1; }
        device.owned = true;
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_CONFIGURE_SCAN) {
        const auto* value = static_cast<const adi_rx_counter_scan_config*>(argument);
        for (unsigned i = 0; i < 8U; ++i) {
            device.profiles[i] = value->profiles[i].frequency_hz;
            device.crcs[i] = value->profiles[i].crc32;
        }
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_SCAN_SNAPSHOT) {
        static_cast<adi_rx_counter_scan_snapshot*>(argument)->counter = device.counter;
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_RECALL) {
        auto* value = static_cast<adi_rx_counter_scan_recall*>(argument);
        value->frequency_hz = device.profiles[value->profile];
        value->profile_crc32 = device.crcs[value->profile] + 1U;
        value->counter_before = device.counter;
        value->counter_after = device.counter;
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_RELEASE_SCAN) {
        auto* value = static_cast<adi_rx_counter_scan_release*>(argument);
        value->frequency_hz = 1'500'000'000ULL;
        value->counter_before = device.counter;
        value->counter_after = device.counter;
        device.owned = false;
        return 0;
    }
    errno = ENOTTY;
    return -1;
}

leo_tle_record tle() {
    leo_tle_record value{};
    value.satellite_id = 44714;
    constexpr char one[] =
        "1 44714U 19074B   26270.09087237  .00034246  00000-0  33881-3 0  9999";
    constexpr char two[] =
        "2 44714  53.1459 294.7156 0002678  78.6558 281.4759 15.65554847380103";
    static_assert(sizeof(one) == 70U && sizeof(two) == 70U);
    std::memcpy(value.line1, one, sizeof(one));
    std::memcpy(value.line2, two, sizeof(two));
    return value;
}

AnalysisConfig analysis_config() {
    ingest::Authority authority{7U, rate, "sha256:" + std::string(64U, 'a'),
        "sha256:" + std::string(64U, 'b'),
        {{2U, 124U, 4U, 1'500'000'000ULL, 11.2e9, true}}};
    online::Config online;
    online.history_window_ns = 10'000'000'000LL;
    online.maximum_satellites = 1U;
    online.maximum_knots = 32U;
    online.maximum_orbit_bytes = 32U * sizeof(leo_orbit_state) * 2U;
    online::SearchConfig search{};
    search.origin_latitude_deg = 37.8;
    search.origin_longitude_deg = -122.4;
    search.score = leo_score_default_config();
    search.policy.radius_km = 1.0;
    search.policy.region_size_km = 2.0;
    search.policy.level_count = 1U;
    search.policy.levels_km[0] = 2.0;
    search.policy.budget_points = 1U;
    return {authority, {rate, 1'000'000U, 120'000'000'000ULL, 10.0, 100U, 1024U},
        online, {"local-pipeline", "sha256:" + std::string(64U, 'a'), utc_origin},
        {tle()}, search, 100'000'000ULL, 1'000'000'000ULL, 1U, 1.0, 32U,
        true, 1U, {}};
}

struct Detector { std::uint32_t calls{}; std::vector<std::uint32_t> dwells; };
int capabilities(void*, leo_native_glrt_capabilities* output) {
    *output = {};
    output->abi_version = LEO_NATIVE_GLRT_ABI_VERSION;
    output->receiver_count = 2U;
    output->probe_ms = 20U;
    output->process_serialized = 1U;
    output->fractional_epoch_mode_available = 1U;
    return 0;
}
int analyze(void* context, const std::int16_t* iq, std::size_t complex_times,
        std::uint32_t dwell_ms, std::uint32_t stride_ms,
        leo_native_glrt_result* output) {
    auto& detector = *static_cast<Detector*>(context);
    assert(iq && complex_times == static_cast<std::size_t>(rate) * dwell_ms / 1000U &&
        stride_ms == 120U && output);
    detector.dwells.push_back(dwell_ms);
    *output = {};
    output->row_count = 1U;
    auto& row = output->rows[0];
    row.receiver_id = 0;
    row.probe_index = 0;
    row.candidate_count = 1U;
    auto& candidate = row.candidates[0];
    candidate.epoch = 100;
    candidate.fractional_epoch_status = 1U;
    candidate.fractional_epoch_offset_samples = 0.25;
    candidate.fractional_tracking_cfo_hz = 1000.0 + detector.calls * 180.0;
    candidate.fractional_exact_score = 0.2;
    candidate.fractional_control_score = 0.05;
    candidate.fractional_margin = 0.15;
    ++detector.calls;
    return 0;
}

struct Clock {
    leo_local_source* source{};
    Analysis* analysis{};
    std::uint64_t counter_zero{};
};
timing::Bracket bracket(std::uint64_t counter, std::uint64_t zero) {
    const auto elapsed = counter - zero;
    const auto elapsed_ns = elapsed * 1'000'000'000ULL / rate;
    return {1'000'000'000ULL + elapsed_ns, 1'000'000'200ULL + elapsed_ns,
        counter, utc_origin + static_cast<std::int64_t>(elapsed_ns),
        utc_origin + static_cast<std::int64_t>(elapsed_ns) + 200LL, true};
}
int snapshot(void* context, std::uint64_t* output) {
    auto& clock = *static_cast<Clock*>(context);
    const int status = leo_local_source_snapshot(clock.source, output);
    if (status) return status;
    return clock.analysis->observe(bracket(*output, clock.counter_zero)) == timing::Status::ok ?
        0 : -ERANGE;
}

struct Sink {
    Analysis* analysis{};
    leo_local_source* source{};
    std::exception_ptr failure;
};
void event_sink(void* context, const leo_scanner_event* event) noexcept {
    auto& sink = *static_cast<Sink*>(context);
    if (sink.failure || !event) return;
    try { sink.analysis->event(*event); }
    catch (...) {
        sink.failure = std::current_exception();
        (void)leo_local_source_cancel(sink.source);
    }
}
int cancel_source(void* context) {
    return leo_local_source_cancel(static_cast<leo_local_source*>(context));
}
}

int main() {
    Device device;
    active_device = &device;
    leo_local_provider_ops provider{&device, capture_open, capture_acquire,
        capture_cancel, capture_release, capture_close, counter_open, counter_close,
        ioctl_call};
    leo_local_config local{};
    local.sample_rate_hz = rate;
    local.analog_bandwidth_hz = rate;
    local.samples_per_block = block_samples;
    local.receiver_count = 2U;
    local.kernel_buffer_count = 4U;
    local.profile_count = 1U;
    local.profiles[0] = {2U, 1'500'000'000ULL, 123U};
    leo_local_source* source{};
    assert(leo_local_source_open(&local, &provider, &source) == 0);
    leo_local_prime_receipt prime{};
    assert(leo_local_source_prime(source, &prime) == 0);

    Analysis analysis(analysis_config());
    Clock clock{source, &analysis, prime.coherent_counter};
    std::uint64_t initial{};
    assert(snapshot(&clock, &initial) == 0);
    analysis.set_cancel(source, cancel_source);

    Detector detector;
    leo_scanner_detector_binding binding{};
    binding.abi_version = LEO_SCANNER_EXECUTION_ABI_VERSION;
    binding.ops = {&detector, analyze, capabilities};
    std::fill(std::begin(binding.configuration_digest),
        std::end(binding.configuration_digest), 0x5aU);
    leo_scanner_execution_options execution{LEO_SCANNER_EXECUTION_ABI_VERSION,
        1U, &binding};
    leo_scanner_counter_ops counter{&clock, snapshot};
    leo_scanner_config scanner{};
    scanner.abi_version = LEO_SCANNER_ABI_VERSION;
    scanner.session = 11U;
    scanner.generation = 7U;
    scanner.seed = 13U;
    scanner.sample_rate_hz = rate;
    scanner.receiver_count = 2U;
    scanner.duration_ms = 8'000U;
    scanner.maximum_visits = 16U;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(12);
    scanner.wall_deadline_monotonic_ns = static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(deadline.time_since_epoch()).count());
    scanner.dwell_ms = 360U;
    scanner.transition_budget_ms = 20U;
    scanner.maximum_revisit_ms = 3'000U;
    scanner.feedback_age_ms = 1'000U;
    scanner.application_delay_ms = 1'000U;
    scanner.decay_ms = 3'000U;
    scanner.maximum_boost = 3U;
    scanner.detector_queue_capacity = 4U;
    scanner.active_threshold_dbfs = -38.0;
    scanner.target_count = 1U;
    scanner.targets[0] = {2U, 1'500'000'000ULL, 123U, 1U};
    Sink sink{&analysis, source, {}};
    leo_scanner_stats stats{};
    const auto run_started = std::chrono::steady_clock::now();
    const int scanner_status = leo_scanner_run_timed_ex(&scanner, source, &counter,
        &execution, event_sink, &sink, &stats);
    const auto run_elapsed = std::chrono::steady_clock::now() - run_started;
    analysis.detach_cancel();
    if (sink.failure) std::rethrow_exception(sink.failure);
    assert(scanner_status == 0);
    assert(stats.stop_reason == LEO_SCANNER_STOP_MAXIMUM_VISITS);
    assert(stats.visits_intact == 16U && stats.detector_accepted == 16U &&
        stats.detector_completed == 16U && stats.detector_candidates == 16U);
    assert(!stats.detector_failures && !stats.detector_queue_drops &&
        stats.detector_queue_high_water <= 4U);
    assert(stats.feedback_active > 0U);
    assert(std::find(detector.dwells.begin(), detector.dwells.end(), 360U) !=
        detector.dwells.end());
    assert(run_elapsed >= std::chrono::seconds(5));

    std::uint64_t final_counter{};
    assert(snapshot(&clock, &final_counter) == 0);
    leo_local_restore_receipt close_receipt{};
    assert(leo_local_source_close(source, &close_receipt) == 0);
    source = nullptr;
    const auto result = analysis.finish_after_rf_stopped();
    const auto publication = analysis.final_published_snapshot();
    assert(result.accepted_candidates == 16U && !result.session.queue_dropped &&
        !result.session.rejected && result.timing_qualified);
    assert(result.publications_with_tracks >= 1U && result.searches_complete >= 1U &&
        result.last_search.has_incumbent);
    assert(publication && !publication->tracking_result.tracks.empty());
    assert(!device.capture_open && !device.lease && !device.owned);
    return 0;
}
