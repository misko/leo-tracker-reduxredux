#include "scanner.h"
#include "scanner_source.h"
#include "json_number.h"
#include "scanner_timing.h"
#include "vendor/adi-rx-counter.h"

#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <tuple>
#include <vector>

namespace {

constexpr uint32_t rate = 2500000U;
constexpr uint32_t block_samples = 50000U;
constexpr size_t block_bytes = 8U + static_cast<size_t>(block_samples) * 8U;

struct Device {
    std::vector<std::vector<uint8_t>> blocks;
    size_t next = 0;
    uint32_t counter = 0;
    uint64_t profiles[8]{};
    uint32_t crcs[8]{};
    bool owned = false;
    bool capture_opened = false;
    int64_t recall_frequency_delta = 0;
    uint32_t recall_latency_samples = 0;
    unsigned recall_count = 0;
    unsigned snapshot_count = 0;
    unsigned snapshot_advance_on_call = 0;
    uint32_t snapshot_advance_samples = 0;
    unsigned release_failures = 0;
    bool zero_recall_crc = false;
    bool block_after_prime = false;
    bool cancelled = false;
    bool lease_outstanding = false;
    int disconnect_at = -1;
    int disconnect_error = -ENODEV;
    std::mutex mutex;
    std::condition_variable changed;
};

Device* active_device = nullptr;

void put64(uint8_t* p, uint64_t value) {
    for (unsigned i = 0; i < 8; ++i) p[i] = static_cast<uint8_t>(value >> (8U * i));
}

void append_block(Device& device, uint64_t first, int16_t amplitude) {
    device.blocks.emplace_back(block_bytes, 0);
    std::vector<uint8_t>& raw = device.blocks.back();
    put64(raw.data(), first + 2U);
    int16_t* iq = reinterpret_cast<int16_t*>(raw.data() + 8U);
    for (uint32_t i = 0; i < block_samples; ++i) {
        iq[4U * i] = amplitude;
        iq[4U * i + 1U] = static_cast<int16_t>(-amplitude);
        iq[4U * i + 2U] = 17;
        iq[4U * i + 3U] = -19;
    }
}

int capture_open(void* context, const leo_local_config* config, void** capture) {
    Device* device = static_cast<Device*>(context);
    assert(config->sample_rate_hz == rate && config->receiver_count == 2U);
    if (device->capture_opened) return -EBUSY;
    device->capture_opened = true;
    *capture = device;
    return 0;
}

int capture_acquire(void* context, void* capture, leo_local_provider_block* block) {
    Device* device = static_cast<Device*>(context);
    assert(capture == device);
    assert(!device->lease_outstanding);
    if (device->disconnect_at >= 0 &&
        device->next >= static_cast<size_t>(device->disconnect_at))
        return device->disconnect_error;
    if (device->block_after_prime && device->next > 0) {
        std::unique_lock<std::mutex> lock(device->mutex);
        device->changed.wait(lock, [device] { return device->cancelled; });
        return -ECANCELED;
    }
    if (device->next >= device->blocks.size()) return -ENODEV;
    std::vector<uint8_t>& raw = device->blocks[device->next];
    uint64_t first = 0;
    for (unsigned i = 0; i < 8; ++i) first |= static_cast<uint64_t>(raw[i]) << (8U * i);
    first -= 2U;
    device->counter = static_cast<uint32_t>(first + block_samples);
    block->raw = raw.data();
    block->raw_bytes = raw.size();
    block->token = ++device->next;
    device->lease_outstanding = true;
    return 0;
}

int capture_release(void* context, void* capture, uintptr_t) {
    Device* device = static_cast<Device*>(context);
    assert(capture == device && device->lease_outstanding);
    if (device->release_failures) {
        --device->release_failures;
        return -EIO;
    }
    device->lease_outstanding = false;
    return 0;
}
int capture_cancel(void* context, void*) {
    Device* device = static_cast<Device*>(context);
    {
        std::lock_guard<std::mutex> lock(device->mutex);
        device->cancelled = true;
    }
    device->changed.notify_all();
    return 0;
}
int capture_close(void* context, void*) {
    static_cast<Device*>(context)->capture_opened = false;
    return 0;
}
int counter_open() { return 9; }
int counter_close(int fd) { assert(fd == 9); return 0; }

int ioctl_call(int, unsigned long request, void* argument) {
    assert(active_device);
    Device& device = *active_device;
    if (request == ADI_RX_COUNTER_IOC_GET_SCAN_CAPS) {
        auto* caps = static_cast<adi_rx_counter_scan_caps*>(argument);
        caps->magic = ADI_RX_COUNTER_MAGIC;
        caps->version = ADI_RX_COUNTER_SCAN_VERSION;
        caps->size = sizeof(*caps);
        caps->features = ADI_RX_COUNTER_SCAN_FEATURES;
        caps->maximum_profiles = 8;
        caps->source_counter_bits = 32;
        caps->frequency_resolution_hz = 2;
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_ACQUIRE) {
        auto* acquire = static_cast<adi_rx_counter_request*>(argument);
        assert(acquire->sample_rate_hz == rate);
        assert(acquire->samples_per_channel == block_samples);
        if (device.owned) { errno = EBUSY; return -1; }
        device.owned = true;
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_CONFIGURE_SCAN) {
        auto* setup = static_cast<adi_rx_counter_scan_config*>(argument);
        for (unsigned i = 0; i < 8; ++i) {
            device.profiles[i] = setup->profiles[i].frequency_hz;
            device.crcs[i] = setup->profiles[i].crc32;
        }
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_SCAN_SNAPSHOT) {
        ++device.snapshot_count;
        if (device.snapshot_count == device.snapshot_advance_on_call)
            device.counter += device.snapshot_advance_samples;
        static_cast<adi_rx_counter_scan_snapshot*>(argument)->counter = device.counter;
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_RECALL) {
        ++device.recall_count;
        auto* recall = static_cast<adi_rx_counter_scan_recall*>(argument);
        recall->frequency_hz = static_cast<uint64_t>(
            static_cast<int64_t>(device.profiles[recall->profile]) +
            device.recall_frequency_delta);
        /* Firmware may update the AD9361 ALC byte on recall. A changed nonzero
         * CRC is attested evidence and must not be compared to setup equality. */
        recall->profile_crc32 = device.zero_recall_crc ? 0 :
            device.crcs[recall->profile] + 1U;
        recall->counter_before = device.counter;
        device.counter += device.recall_latency_samples;
        recall->counter_after = device.counter;
        device.next += device.recall_latency_samples / block_samples;
        return 0;
    }
    if (request == ADI_RX_COUNTER_IOC_RELEASE_SCAN) {
        auto* release = static_cast<adi_rx_counter_scan_release*>(argument);
        release->frequency_hz = UINT64_C(2400000000);
        release->counter_before = device.counter;
        release->counter_after = device.counter;
        device.owned = false;
        return 0;
    }
    errno = ENOTTY;
    return -1;
}

leo_local_provider_ops provider(Device& device) {
    active_device = &device;
    leo_local_provider_ops ops{};
    ops.context = &device;
    ops.capture_open = capture_open;
    ops.capture_acquire = capture_acquire;
    ops.capture_cancel = capture_cancel;
    ops.capture_release = capture_release;
    ops.capture_close = capture_close;
    ops.counter_open = counter_open;
    ops.counter_close = counter_close;
    ops.ioctl_call = ioctl_call;
    return ops;
}

leo_local_config local_config(uint32_t target_count = 1U) {
    leo_local_config config{};
    config.sample_rate_hz = rate;
    config.analog_bandwidth_hz = rate;
    config.samples_per_block = block_samples;
    config.receiver_count = 2;
    config.kernel_buffer_count = 4;
    config.profile_count = target_count;
    for (uint32_t i = 0; i < target_count; ++i) {
        config.profiles[i].profile = i;
        config.profiles[i].frequency_hz = UINT64_C(1000000000) + i * UINT64_C(2000000);
        config.profiles[i].crc32 = 123U + i;
    }
    return config;
}

leo_scanner_config scanner_config(uint32_t visits, uint32_t target_count = 1U) {
    leo_scanner_config config{};
    config.abi_version = LEO_SCANNER_ABI_VERSION;
    config.session = 11;
    config.generation = 12;
    config.seed = 13;
    config.sample_rate_hz = rate;
    config.receiver_count = 2;
    config.duration_ms = std::max(700U, visits * 160U);
    config.maximum_visits = visits;
    struct timespec now{};
    assert(clock_gettime(CLOCK_MONOTONIC, &now) == 0);
    config.wall_deadline_monotonic_ns = static_cast<uint64_t>(now.tv_sec) *
        UINT64_C(1000000000) + static_cast<uint64_t>(now.tv_nsec) +
        UINT64_C(5000000000);
    config.dwell_ms = 120;
    config.transition_budget_ms = 20;
    config.maximum_revisit_ms = 3000;
    config.feedback_age_ms = 1000;
    config.application_delay_ms = 1000;
    config.decay_ms = 3000;
    config.maximum_boost = 3;
    config.detector_queue_capacity = 1;
    config.active_threshold_dbfs = -38.0;
    config.target_count = target_count;
    for (uint32_t i = 0; i < target_count; ++i) {
        config.targets[i].profile = i;
        config.targets[i].frequency_hz = UINT64_C(1000000000) +
            i * UINT64_C(2000000);
        config.targets[i].profile_crc32 = 123U + i;
        config.targets[i].baseline_weight = 1;
    }
    return config;
}

struct Detector {
    unsigned calls = 0;
    unsigned delay_ms = 0;
    std::vector<uint32_t> dwells;
};

int capabilities(void*, leo_native_glrt_capabilities* out) {
    *out = leo_native_glrt_capabilities{};
    out->abi_version = LEO_NATIVE_GLRT_ABI_VERSION;
    out->receiver_count = 2;
    out->probe_ms = 20;
    out->process_serialized = 1;
    out->fractional_epoch_mode_available = 1;
    out->fractional_epoch_server_parity_qualified = 0;
    return 0;
}

int analyze(void* context, const int16_t* iq, size_t times, uint32_t dwell_ms,
    uint32_t stride_ms, leo_native_glrt_result* result) {
    Detector& detector = *static_cast<Detector*>(context);
    assert(iq && times == static_cast<size_t>(rate) * dwell_ms / 1000U &&
        stride_ms == 120U);
    ++detector.calls;
    detector.dwells.push_back(dwell_ms);
    if (detector.delay_ms)
        std::this_thread::sleep_for(std::chrono::milliseconds(detector.delay_ms));
    *result = leo_native_glrt_result{};
    result->row_count = 1;
    result->rows[0].receiver_id = 0;
    result->rows[0].probe_index = 0;
    result->rows[0].candidate_count = 1;
    result->rows[0].candidates[0].epoch = 77;
    result->rows[0].candidates[0].fractional_epoch_status = 1;
    result->rows[0].candidates[0].fractional_epoch_offset_samples = 0.25;
    return 0;
}

struct Events {
    std::vector<leo_scanner_event> values;
    bool throw_on_detector_result = false;
};

struct SourceEvents { std::vector<leo_scanner_source_event> values; };
void collect_source(void* context, const leo_scanner_source_event* event) {
    static_cast<SourceEvents*>(context)->values.push_back(*event);
}

struct PortFake {
    leo_source_capabilities caps{};
    std::vector<std::vector<int16_t>> blocks;
    std::size_t next{};
    std::uint64_t coordinate{51000};
    std::uintptr_t token{};
    unsigned capability_calls{}, positions{}, selections{}, releases{}, cancels{};
    unsigned release_failures{};
    int cancel_status{};
    std::uint32_t injected_block_flags{};
    bool block_next{}, cancelled{}, waiting{};
    std::mutex mutex;
    std::condition_variable changed;
};

leo_source_capabilities port_capabilities() {
    leo_source_capabilities value{};
    value.abi_version=LEO_SOURCE_PORT_ABI_VERSION;
    value.sample_format=LEO_SOURCE_SAMPLE_FORMAT_CI16;
    value.flags=LEO_SOURCE_CAP_CANCEL|LEO_SOURCE_CAP_SELECT|
        LEO_SOURCE_CAP_SIMULTANEOUS_RX|LEO_SOURCE_CAP_COHERENT_RX|
        LEO_SOURCE_CAP_FREQUENCY_ATTESTATION|LEO_SOURCE_CAP_TARGET_ATTESTATION|
        LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION|LEO_SOURCE_CAP_EXACT_GAP|
        LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    value.sample_rate_hz=rate; value.receiver_count=2;
    value.maximum_samples_per_block=block_samples;
    value.counter_authority=LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    value.position_semantics=LEO_SOURCE_POSITION_COHERENT_CURRENT;
    return value;
}
int port_caps(void* context,leo_source_capabilities* out) {
    auto& fake=*static_cast<PortFake*>(context); ++fake.capability_calls;
    *out=fake.caps; return 0;
}
int port_position(void* context,leo_source_position* out) {
    auto& fake=*static_cast<PortFake*>(context); ++fake.positions;
    out->coordinate=fake.coordinate; out->counter_authority=fake.caps.counter_authority;
    out->semantics=fake.caps.position_semantics; return 0;
}
int port_select(void* context,const leo_source_selection* selection,
                leo_source_transition* out) {
    auto& fake=*static_cast<PortFake*>(context); ++fake.selections; *out={};
    out->flags=LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED|
        LEO_SOURCE_TRANSITION_TARGET_ATTESTED|
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    if (fake.caps.flags&LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION) {
        out->flags|=LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED;
        out->profile_crc32=124;
    }
    out->selected_target_key=selection->target_key;
    out->counter_authority=fake.caps.counter_authority;
    out->position_semantics=fake.caps.position_semantics;
    out->actual_frequency_hz=selection->requested_frequency_hz;
    out->previous_valid_end=fake.coordinate; out->valid_start=fake.coordinate;
    return 0;
}
int port_next(void* context,leo_source_block* out) {
    auto& fake=*static_cast<PortFake*>(context);
    if (fake.block_next) {
        std::unique_lock<std::mutex> lock(fake.mutex); fake.waiting=true;
        fake.changed.notify_all(); fake.changed.wait(lock,[&]{return fake.cancelled;});
        return -ECANCELED;
    }
    if (fake.next>=fake.blocks.size()) return -ENODEV;
    auto& data=fake.blocks[fake.next++]; *out={}; out->ci16=data.data();
    out->samples_per_receiver=block_samples; out->receiver_count=2;
    out->iq_bytes=data.size()*sizeof(int16_t);
    if (fake.injected_block_flags)
        out->flags=fake.injected_block_flags;
    else if (fake.caps.flags&LEO_SOURCE_CAP_EXACT_GAP)
        out->flags=LEO_SOURCE_BLOCK_GAP_EXACT;
    out->counter_authority=fake.caps.counter_authority;
    out->first_coordinate=fake.coordinate; out->end_coordinate=fake.coordinate+block_samples;
    out->buffer_sequence=fake.next; out->lease_token=++fake.token;
    fake.coordinate=out->end_coordinate; return 0;
}
int port_release(void* context,leo_source_block*) {
    auto& fake=*static_cast<PortFake*>(context); ++fake.releases;
    if (fake.release_failures) { --fake.release_failures; return -EIO; }
    return 0;
}
int port_cancel(void* context) {
    auto& fake=*static_cast<PortFake*>(context); ++fake.cancels;
    { std::lock_guard<std::mutex> lock(fake.mutex); fake.cancelled=true; }
    fake.changed.notify_all(); return fake.cancel_status;
}
const leo_source_ops port_ops{port_caps,port_position,port_select,port_next,
    port_release,port_cancel};

leo_scanner_source_requirements exact_requirements() {
    leo_scanner_source_requirements value{};
    value.abi_version=LEO_SCANNER_SOURCE_ABI_VERSION;
    value.counter_authority=LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    value.position_semantics=LEO_SOURCE_POSITION_COHERENT_CURRENT;
    value.required_capability_flags=port_capabilities().flags;
    value.required_transition_flags=LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED|
        LEO_SOURCE_TRANSITION_TARGET_ATTESTED|
        LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED|
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    value.maximum_frequency_error_hz=2; value.require_physical_counter_qualified=1;
    return value;
}
void setup_port_fake(PortFake& fake,bool blocking=false) {
    fake.caps=port_capabilities(); fake.block_next=blocking;
    if (!blocking) for (unsigned block=0;block<7;++block) {
        fake.blocks.emplace_back(static_cast<std::size_t>(block_samples)*4U);
        auto& iq=fake.blocks.back();
        for (unsigned i=0;i<block_samples;++i) {
            iq[4U*i]=1000; iq[4U*i+1]=-1000; iq[4U*i+2]=17; iq[4U*i+3]=-19;
        }
    }
}

struct ParallelCounters {
    std::atomic<unsigned> active{0};
    std::atomic<unsigned> maximum_active{0};
};

struct ParallelDetector {
    ParallelCounters* counters{};
    unsigned id{};
    unsigned delay_ms{};
    unsigned calls{};
    unsigned capability_calls{};
    int capability_status{};
    uint32_t process_serialized{};
    int analyze_status{};
};

int parallel_capabilities(void* context, leo_native_glrt_capabilities* out) {
    auto& detector=*static_cast<ParallelDetector*>(context);
    ++detector.capability_calls;
    if (detector.capability_status) return detector.capability_status;
    *out={}; out->abi_version=LEO_NATIVE_GLRT_ABI_VERSION;
    out->receiver_count=2U; out->probe_ms=20U;
    out->process_serialized=detector.process_serialized;
    out->candidate_cfo_refinement_state_available=1U;
    out->fractional_epoch_mode_available=1U;
    return 0;
}

int parallel_analyze(void* context,const int16_t* iq,size_t times,
                     uint32_t dwell_ms,uint32_t stride_ms,
                     leo_native_glrt_result* result) {
    auto& detector=*static_cast<ParallelDetector*>(context);
    assert(iq && times==static_cast<size_t>(rate)*dwell_ms/1000U &&
        stride_ms==120U);
    ++detector.calls;
    const unsigned active=detector.counters->active.fetch_add(1U)+1U;
    unsigned maximum=detector.counters->maximum_active.load();
    while (maximum<active && !detector.counters->maximum_active.compare_exchange_weak(
        maximum,active)) {}
    if (detector.delay_ms)
        std::this_thread::sleep_for(std::chrono::milliseconds(detector.delay_ms));
    detector.counters->active.fetch_sub(1U);
    if (detector.analyze_status) return detector.analyze_status;
    *result={}; result->row_count=1U;
    result->rows[0].receiver_id=0; result->rows[0].probe_index=0;
    result->rows[0].candidate_count=1;
    result->rows[0].candidates[0].epoch=static_cast<int64_t>(detector.id);
    return 0;
}

leo_scanner_detector_binding parallel_binding(ParallelDetector& detector,
                                               uint8_t digest=0x5aU) {
    leo_scanner_detector_binding binding{};
    binding.abi_version=LEO_SCANNER_EXECUTION_ABI_VERSION;
    binding.ops={&detector,parallel_analyze,parallel_capabilities};
    std::fill(std::begin(binding.configuration_digest),
        std::end(binding.configuration_digest),digest);
    return binding;
}

void add_port_blocks(PortFake& fake,unsigned count) {
    for (unsigned block=0;block<count;++block) {
        fake.blocks.emplace_back(static_cast<std::size_t>(block_samples)*4U);
        auto& iq=fake.blocks.back();
        for (unsigned i=0;i<block_samples;++i) {
            iq[4U*i]=1000; iq[4U*i+1]=-1000;
            iq[4U*i+2]=17; iq[4U*i+3]=-19;
        }
    }
}

struct TimedCounter {
    Device* device = nullptr;
    leo_local_source* source = nullptr;
    std::thread::id acquisition_thread;
    std::vector<uint32_t> values;
    unsigned calls = 0;
    unsigned fail_call = 0;
    int fail_status = -EIO;
};

int timed_snapshot(void* context, uint64_t* counter) {
    TimedCounter& timed = *static_cast<TimedCounter*>(context);
    assert(counter && timed.device && timed.source);
    assert(std::this_thread::get_id() == timed.acquisition_thread);
    assert(!timed.device->lease_outstanding);
    ++timed.calls;
    if (timed.calls == timed.fail_call) return timed.fail_status;
    if (timed.calls <= timed.values.size())
        timed.device->counter = timed.values[timed.calls - 1U];
    return leo_local_source_snapshot(timed.source, counter);
}
void collect(void* context, const leo_scanner_event* event) {
    Events& events = *static_cast<Events*>(context);
    if (events.throw_on_detector_result && event->kind == LEO_SCANNER_DETECTOR_RESULT)
        throw std::runtime_error("injected sink failure");
    events.values.push_back(*event);
}

void populate(Device& device, unsigned visits, int16_t amplitude, bool gap,
    uint32_t active_dwell_ms, uint32_t recall_latency_samples,
    uint32_t snapshot_advance_samples) {
    uint64_t first = 1000;
    const unsigned count = 1U + (visits ? 7U : 0U) +
        (visits > 1U ? (visits - 1U) * (1U + active_dwell_ms / 20U) : 0U) +
        (recall_latency_samples ? recall_latency_samples / block_samples + 2U : 0U) +
        (snapshot_advance_samples ? snapshot_advance_samples / block_samples + 1U : 0U);
    for (unsigned i = 0; i < count; ++i) {
        if (gap && i == 3U) first += block_samples;
        append_block(device, first, amplitude);
        first += block_samples;
    }
}

int run_case(unsigned visits, int16_t amplitude, bool gap, unsigned detector_delay,
    leo_scanner_stats& stats, Events& events, Detector& detector,
    uint32_t active_dwell_ms = 120U, int64_t recall_frequency_delta = 0,
    bool zero_recall_crc = false, bool block_after_prime = false,
    uint32_t deadline_ms = 5000U, int disconnect_at = -1,
    int disconnect_error = -ENODEV, uint32_t recall_latency_samples = 0U,
    unsigned* recall_count = nullptr, uint32_t target_count = 1U,
    uint32_t maximum_revisit_ms = 3000U,
    uint32_t snapshot_advance_samples = 0U,
    uint32_t detector_queue_capacity = 1U) {
    Device device;
    device.recall_frequency_delta = recall_frequency_delta;
    device.zero_recall_crc = zero_recall_crc;
    device.block_after_prime = block_after_prime;
    device.disconnect_at = disconnect_at;
    device.disconnect_error = disconnect_error;
    device.recall_latency_samples = recall_latency_samples;
    device.snapshot_advance_on_call = snapshot_advance_samples ? 3U : 0U;
    device.snapshot_advance_samples = snapshot_advance_samples;
    populate(device, visits, amplitude, gap, active_dwell_ms,
        recall_latency_samples, snapshot_advance_samples);
    leo_local_provider_ops ops = provider(device);
    leo_local_config local = local_config(target_count);
    leo_local_source* source = nullptr;
    assert(leo_local_source_open(&local, &ops, &source) == 0);
    leo_local_prime_receipt prime{};
    assert(leo_local_source_prime(source, &prime) == 0);
    detector.delay_ms = detector_delay;
    leo_scanner_detector_ops detector_ops{};
    detector_ops.context = &detector;
    detector_ops.analyze = analyze;
    detector_ops.capabilities = capabilities;
    leo_scanner_config scan = scanner_config(visits, target_count);
    scan.dwell_ms = active_dwell_ms;
    scan.maximum_revisit_ms = maximum_revisit_ms;
    scan.detector_queue_capacity = detector_queue_capacity;
    struct timespec now{};
    assert(clock_gettime(CLOCK_MONOTONIC, &now) == 0);
    scan.wall_deadline_monotonic_ns = static_cast<uint64_t>(now.tv_sec) *
        UINT64_C(1000000000) + static_cast<uint64_t>(now.tv_nsec) +
        static_cast<uint64_t>(deadline_ms) * UINT64_C(1000000);
    const int run_status = leo_scanner_run(&scan, source, &detector_ops,
        collect, &events, &stats);
    if (recall_count) *recall_count = device.recall_count;
    leo_local_restore_receipt restore{};
    assert(leo_local_source_close(source, &restore) == 0);
    return run_status;
}

int run_timed_case(unsigned visits, TimedCounter& timed, leo_scanner_stats& stats,
    Events& events, Detector& detector, unsigned& recalls,
    unsigned& source_snapshots) {
    Device device;
    /* Leave one extra block for scripted counter ports that advance between
     * the policy-origin and per-selection snapshots. */
    populate(device, visits, 100, false, 120U, 0U, block_samples / 2U);
    leo_local_provider_ops ops = provider(device);
    leo_local_config local = local_config();
    leo_local_source* source = nullptr;
    assert(leo_local_source_open(&local, &ops, &source) == 0);
    leo_local_prime_receipt prime{};
    assert(leo_local_source_prime(source, &prime) == 0);

    timed.device = &device;
    timed.source = source;
    timed.acquisition_thread = std::this_thread::get_id();
    leo_scanner_counter_ops counter_ops{};
    counter_ops.context = &timed;
    counter_ops.snapshot = timed_snapshot;
    leo_scanner_detector_ops detector_ops{};
    detector_ops.context = &detector;
    detector_ops.analyze = analyze;
    detector_ops.capabilities = capabilities;
    leo_scanner_config scan = scanner_config(visits);
    const int run_status = leo_scanner_run_timed(&scan, source, &counter_ops,
        &detector_ops, collect, &events, &stats);
    recalls = device.recall_count;
    source_snapshots = device.snapshot_count;
    assert(!device.lease_outstanding);
    leo_local_restore_receipt restore{};
    assert(leo_local_source_close(source, &restore) == 0);
    return run_status;
}

void test_complete_active_fractional_evidence() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    assert(run_case(1, 1000, false, 0, stats, events, detector) == 0);
    assert(stats.visits_started == 1 && stats.visits_intact == 1);
    assert(stats.windows_emitted == 1 && stats.feedback_active == 1);
    assert(stats.detector_accepted == 1 && stats.detector_completed == 1);
    assert(stats.detector_candidates == 1 && detector.calls == 1);
    assert(stats.stop_reason == LEO_SCANNER_STOP_MAXIMUM_VISITS);
    assert(stats.stop_status == 0);
    bool saw_visit = false, saw_candidate = false;
    for (const auto& event : events.values) {
        if (event.kind == LEO_SCANNER_VISIT) {
            saw_visit = true;
            assert(event.recalled == 1U);
            assert(event.transition_counter_before <=
                event.transition_counter_after);
            assert(event.valid_start >= event.selection_counter);
            assert(event.feedback_outcome == LEO_SCANNER_ACTIVE);
            assert(event.attested_profile_crc32 == 124U);
            assert(event.energy_sum == UINT64_C(600000000000));
            assert(event.energy_sample_count == 300000U);
            assert(fabs(event.power_dbfs - (-30.30899869919436)) < 1e-12);
        } else if (event.kind == LEO_SCANNER_CANDIDATE) {
            saw_candidate = true;
            assert(event.candidate.fractional_epoch_status == 1);
            assert(event.candidate.fractional_epoch_offset_samples == 0.25);
            assert(event.fractional_epoch_server_parity_qualified == 0);
            assert(event.detector_enqueued_monotonic_ns > 0);
            assert(event.detector_started_monotonic_ns >=
                event.detector_enqueued_monotonic_ns);
            assert(event.detector_finished_monotonic_ns >=
                event.detector_started_monotonic_ns);
            assert(event.detector_queue_ns == event.detector_started_monotonic_ns -
                event.detector_enqueued_monotonic_ns);
            assert(event.detector_runtime_ns == event.detector_finished_monotonic_ns -
                event.detector_started_monotonic_ns);
            assert(event.detector_row_count == 1U);
        }
    }
    assert(saw_visit && saw_candidate);
}

void test_gap_is_unknown_and_not_analyzed() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    assert(run_case(1, 1000, true, 0, stats, events, detector) == 0);
    assert(stats.visits_incomplete == 1 && stats.feedback_unknown == 1);
    assert(stats.detector_accepted == 0 && detector.calls == 0);
    assert(stats.missing_samples == block_samples);
}

void test_single_worker_bounded_queue_reports_drop() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    assert(run_case(3, 100, false, 150, stats, events, detector) == 0);
    assert(stats.visits_intact == 3 && stats.feedback_quiet == 3);
    assert(stats.detector_accepted == 2 && stats.detector_queue_drops == 1);
    assert(stats.detector_completed == 2 && detector.calls == 2);
    assert(stats.detector_queue_high_water == 1);
    unsigned drops = 0;
    for (const auto& event : events.values)
        drops += event.kind == LEO_SCANNER_QUEUE_DROP;
    assert(drops == 1);
}

void test_four_entry_queue_bounds_burst_at_five_outstanding() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    assert(run_case(7, 100, false, 500, stats, events, detector, 120U, 0,
        false, false, 5000U, -1, -ENODEV, 0U, nullptr, 1U, 3000U, 0U,
        4U) == 0);
    /* One running job plus four queued jobs own exactly five bounded slots. */
    assert(stats.visits_intact == 7U);
    assert(stats.detector_accepted == 5U);
    assert(stats.detector_queue_drops == 2U);
    assert(stats.detector_completed == 5U && detector.calls == 5U);
    assert(stats.detector_queue_high_water == 4U);
}

void test_active_feedback_expands_later_dwell() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    assert(run_case(2, 1000, false, 0, stats, events, detector, 240U) == 0);
    assert(stats.visits_intact == 2 && stats.feedback_active == 2);
    assert(stats.windows_emitted == 3);
    assert(detector.dwells.size() == 2);
    assert(detector.dwells[0] == 120U && detector.dwells[1] == 240U);

    stats = leo_scanner_stats{};
    events.values.clear();
    detector = Detector{};
    assert(run_case(2, 1000, false, 0, stats, events, detector, 360U) == 0);
    assert(stats.visits_intact == 2 && stats.windows_emitted == 4);
    assert(detector.dwells.size() == 2);
    assert(detector.dwells[0] == 120U && detector.dwells[1] == 360U);
}

void test_transition_timing_contract() {
    uint64_t valid = 0;
    assert(leo_scanner_valid_start(100U, 99U, 20U, true, valid) == 0);
    assert(valid == 120U);
    assert(leo_scanner_valid_start(100U, 110U, 20U, true, valid) == 0);
    assert(valid == 120U);
    assert(leo_scanner_valid_start(100U, 120U, 20U, true, valid) == 0);
    assert(valid == 120U);
    assert(leo_scanner_valid_start(100U, 121U, 20U, true, valid) == 0);
    assert(valid == 141U);
    assert(leo_scanner_valid_start(100U, 999U, 20U, false, valid) == 0);
    assert(valid == 100U);

    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    assert(run_case(1, 1000, false, 0, stats, events, detector, 120U, 0,
        false, false, 5000U, -1, -ENODEV, 25000U) == 0);
    bool saw_visit = false;
    for (const auto& event : events.values) {
        if (event.kind != LEO_SCANNER_VISIT) continue;
        saw_visit = true;
        /* Prime ends at 51,000. The 10 ms recall finishes at 76,000, but the
         * declared total 20 ms transition makes the visit valid at 101,000. */
        assert(event.valid_start == 101000U);
    }
    assert(saw_visit);

    stats = leo_scanner_stats{};
    events.values.clear();
    detector = Detector{};
    assert(run_case(1, 1000, false, 0, stats, events, detector, 120U, 0,
        false, false, 5000U, -1, -ENODEV, 60000U) == 0);
    saw_visit = false;
    for (const auto& event : events.values) {
        if (event.kind != LEO_SCANNER_VISIT) continue;
        saw_visit = true;
        /* Recall completes at 111,000, after the nominal 101,000 boundary,
         * and therefore receives the full 50,000-sample settling interval. */
        assert(event.valid_start == 161000U);
    }
    assert(saw_visit && stats.visits_intact == 1 && detector.calls == 1);
}

void test_same_profile_skips_recall_and_transition() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    unsigned recalls = 0;
    assert(run_case(2, 100, false, 0, stats, events, detector, 120U, 0,
        false, false, 5000U, -1, -ENODEV, 0U, &recalls) == 0);
    assert(recalls == 1U);
    uint64_t first_end = 0, second_start = 0;
    unsigned visits = 0;
    for (const auto& event : events.values) {
        if (event.kind != LEO_SCANNER_VISIT) continue;
        if (visits++ == 0) {
            assert(event.recalled == 1U);
            first_end = event.valid_end;
        } else {
            assert(event.recalled == 0U);
            assert(event.transition_counter_before == event.selection_counter);
            assert(event.transition_counter_after == event.selection_counter);
            second_start = event.valid_start;
        }
    }
    assert(visits == 2U);
    assert(second_start == first_end);
}

void test_four_target_hundred_ms_admission_with_twenty_ms_blocks() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    assert(run_case(16, 100, false, 0, stats, events, detector, 120U, 0,
        false, false, 5000U, -1, -ENODEV, 0U, nullptr, 4U, 880U) == 0);
    assert(stats.visits_started == 16U && stats.visits_intact == 16U);
    assert(stats.visits_incomplete == 0U && stats.missing_samples == 0U);
    assert(stats.stop_reason == LEO_SCANNER_STOP_MAXIMUM_VISITS);
    assert(detector.calls == 16U);
}

void test_selection_uses_fresh_source_snapshot() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    assert(run_case(1, 100, false, 0, stats, events, detector, 120U, 0,
        false, false, 5000U, -1, -ENODEV, 0U, nullptr, 1U, 3000U,
        25000U) == 0);
    bool saw_visit = false;
    for (const auto& event : events.values) {
        if (event.kind != LEO_SCANNER_VISIT) continue;
        saw_visit = true;
        /* Prime/initial policy snapshots end at 51,000. The source advances
         * 10 ms before selection; selection must use the fresh 76,000 value. */
        assert(event.selection_counter == 76000U);
        assert(event.transition_counter_after == 76000U);
        assert(event.valid_start == 126000U);
    }
    assert(saw_visit && stats.visits_intact == 1U);
}

void test_timed_counter_runs_on_acquisition_lane_and_drives_policy() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    TimedCounter timed;
    timed.values = {51000U, 76000U};
    unsigned recalls = 0, source_snapshots = 0;
    assert(run_timed_case(1U, timed, stats, events, detector, recalls,
        source_snapshots) == 0);
    assert(timed.calls == 2U);
    /* Prime performs one snapshot; both later snapshots came from the timed
     * port, which in this fake delegates to and updates the same source. */
    assert(source_snapshots == 3U);
    assert(recalls == 1U && stats.visits_intact == 1U);
    bool saw_visit = false;
    for (const auto& event : events.values) {
        if (event.kind != LEO_SCANNER_VISIT) continue;
        saw_visit = true;
        assert(event.selection_counter == 76000U);
        assert(event.transition_counter_before == 76000U);
        assert(event.transition_counter_after == 76000U);
        assert(event.valid_start == 126000U);
    }
    assert(saw_visit);
}

void test_timed_counter_failures_stop_before_retune() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    TimedCounter timed;
    timed.fail_call = 1U;
    unsigned recalls = 0, source_snapshots = 0;
    assert(run_timed_case(1U, timed, stats, events, detector, recalls,
        source_snapshots) == -EIO);
    assert(timed.calls == 1U && recalls == 0U && detector.calls == 0U);
    assert(stats.stop_reason == LEO_SCANNER_STOP_SOURCE_ERROR);
    assert(stats.stop_status == -EIO);

    stats = leo_scanner_stats{};
    events.values.clear();
    detector = Detector{};
    timed = TimedCounter{};
    timed.fail_call = 2U;
    timed.fail_status = 1;
    assert(run_timed_case(1U, timed, stats, events, detector, recalls,
        source_snapshots) == -EIO);
    assert(timed.calls == 2U && recalls == 0U && detector.calls == 0U);
    assert(stats.stop_reason == LEO_SCANNER_STOP_SOURCE_ERROR);
    assert(stats.stop_status == -EIO);
}

void test_legacy_counter_path_remains_source_owned() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    assert(run_case(1U, 100, false, 0U, stats, events, detector) == 0);
    assert(stats.visits_intact == 1U && detector.calls == 1U);
    bool saw_visit = false;
    for (const auto& event : events.values) {
        if (event.kind != LEO_SCANNER_VISIT) continue;
        saw_visit = true;
        assert(event.selection_counter == 51000U);
    }
    assert(saw_visit);
}

void test_json_number_serializes_nonfinite_as_null() {
    FILE* stream = tmpfile();
    assert(stream);
    leo_scanner_json_number(stream, -INFINITY);
    fputc(' ', stream);
    leo_scanner_json_number(stream, NAN);
    fputc(' ', stream);
    leo_scanner_json_number(stream, 1.25);
    assert(fflush(stream) == 0);
    assert(fseek(stream, 0, SEEK_SET) == 0);
    char value[64]{};
    assert(fread(value, 1, sizeof(value) - 1U, stream) == 14U);
    assert(strcmp(value, "null null 1.25") == 0);
    assert(fclose(stream) == 0);
}

void test_attested_tune_validation() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    assert(run_case(1, 1000, false, 0, stats, events, detector, 120U, 3) == -EPROTO);
    assert(detector.calls == 0);
    stats = leo_scanner_stats{};
    events.values.clear();
    assert(run_case(1, 1000, false, 0, stats, events, detector, 120U, 0, true) ==
        -EPROTO);
    assert(detector.calls == 0);
}

void test_deadline_cancels_blocking_source() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    const auto start = std::chrono::steady_clock::now();
    assert(run_case(1, 1000, false, 0, stats, events, detector, 120U, 0, false,
        true, 50U) == -ETIMEDOUT);
    const auto elapsed = std::chrono::steady_clock::now() - start;
    assert(elapsed < std::chrono::seconds(1));
    assert(detector.calls == 0);
    assert(stats.stop_reason == LEO_SCANNER_STOP_WALL_DEADLINE);
    assert(stats.stop_status == -ETIMEDOUT);
}

void test_worker_sink_failure_fails_run_and_releases_slot() {
    leo_scanner_stats stats{};
    Events events;
    events.throw_on_detector_result = true;
    Detector detector;
    assert(run_case(1, 1000, false, 0, stats, events, detector) == -EIO);
    assert(detector.calls == 1);
    assert(stats.stop_reason == LEO_SCANNER_STOP_DETECTOR_ERROR);
    assert(stats.stop_status == -EIO);
}

void test_disconnect_status_is_not_masked() {
    leo_scanner_stats stats{};
    Events events;
    Detector detector;
    assert(run_case(1, 1000, false, 0, stats, events, detector, 120U, 0, false,
        false, 5000U, 3) == -ENODEV);
    assert(stats.visits_incomplete == 1 && stats.feedback_unknown == 1);
    assert(stats.stop_reason == LEO_SCANNER_STOP_SOURCE_ERROR);
    assert(stats.stop_status == -ENODEV);
    assert(detector.calls == 0);
    stats = leo_scanner_stats{};
    events.values.clear();
    assert(run_case(1, 1000, false, 0, stats, events, detector, 120U, 0, false,
        false, 5000U, 3, -ENODATA) == -ENODATA);
    assert(stats.visits_incomplete == 1 && stats.feedback_unknown == 1);
    assert(detector.calls == 0);
}

bool same_event_science(const leo_scanner_event& a,const leo_scanner_event& b) {
    return a.kind==b.kind && a.visit==b.visit && a.valid_start==b.valid_start &&
        a.valid_end==b.valid_end && a.selection_counter==b.selection_counter &&
        a.transition_counter_before==b.transition_counter_before &&
        a.transition_counter_after==b.transition_counter_after && a.recalled==b.recalled &&
        a.target==b.target && a.profile==b.profile &&
        a.attested_profile_crc32==b.attested_profile_crc32 &&
        a.frequency_hz==b.frequency_hz && a.feedback_outcome==b.feedback_outcome &&
        a.energy_sum==b.energy_sum && a.energy_sample_count==b.energy_sample_count &&
        a.power_dbfs==b.power_dbfs && a.windows_emitted==b.windows_emitted &&
        a.row_index==b.row_index && a.candidate_index==b.candidate_index &&
        a.receiver_id==b.receiver_id && a.probe_index==b.probe_index &&
        a.detector_status==b.detector_status &&
        a.fractional_epoch_server_parity_qualified==
            b.fractional_epoch_server_parity_qualified &&
        a.detector_row_count==b.detector_row_count &&
        a.candidate.epoch==b.candidate.epoch &&
        a.candidate.fractional_epoch_status==b.candidate.fractional_epoch_status &&
        a.candidate.fractional_epoch_offset_samples==
            b.candidate.fractional_epoch_offset_samples;
}

void test_exact_common_port_matches_legacy_science() {
    leo_scanner_stats legacy_stats{}; Events legacy_events; Detector legacy_detector;
    assert(run_case(1,1000,false,0,legacy_stats,legacy_events,legacy_detector)==0);

    PortFake fake; setup_port_fake(fake); leo_source_port port{};
    assert(leo_source_port_init(&port,&fake,&port_ops)==0);
    Detector detector; leo_scanner_detector_ops detector_ops{&detector,analyze,capabilities};
    auto config=scanner_config(1); auto requirements=exact_requirements();
    SourceEvents events; leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source(&config,&port,&requirements,&detector_ops,
        collect_source,&events,&stats)==0);
    assert(memcmp(&legacy_stats,&stats.scanner,sizeof(legacy_stats))==0);
    assert(events.values.size()==legacy_events.values.size());
    auto generic=events.values;
    auto legacy=legacy_events.values;
    auto generic_order=[](const leo_scanner_source_event& a,const leo_scanner_source_event& b) {
        return std::tie(a.event.kind,a.event.visit,a.event.row_index,a.event.candidate_index)<
            std::tie(b.event.kind,b.event.visit,b.event.row_index,b.event.candidate_index);
    };
    auto legacy_order=[](const leo_scanner_event& a,const leo_scanner_event& b) {
        return std::tie(a.kind,a.visit,a.row_index,a.candidate_index)<
            std::tie(b.kind,b.visit,b.row_index,b.candidate_index);
    };
    std::sort(generic.begin(),generic.end(),generic_order);
    std::sort(legacy.begin(),legacy.end(),legacy_order);
    for (std::size_t i=0;i<generic.size();++i) {
        assert(same_event_science(generic[i].event,legacy[i]));
        assert(generic[i].abi_version==LEO_SCANNER_SOURCE_ABI_VERSION);
        assert(generic[i].counter_authority==LEO_SOURCE_COUNTER_PROVIDER_EXACT);
        assert(generic[i].position_semantics==LEO_SOURCE_POSITION_COHERENT_CURRENT);
        assert(generic[i].physical_counter_qualified==1U);
    }
    assert(stats.physical_counter_qualified==1U && !stats.overflow_blocks &&
        !stats.discontinuity_blocks && !stats.unknown_discontinuities);
}

void test_common_port_rejects_missing_capability_before_selection() {
    PortFake fake; setup_port_fake(fake);
    fake.caps.flags&=~LEO_SOURCE_CAP_COHERENT_RX;
    leo_source_port port{}; assert(leo_source_port_init(&port,&fake,&port_ops)==0);
    Detector detector; leo_scanner_detector_ops detector_ops{&detector,analyze,capabilities};
    auto config=scanner_config(1); auto requirements=exact_requirements();
    SourceEvents events; leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source(&config,&port,&requirements,&detector_ops,
        collect_source,&events,&stats)==-ENOTSUP);
    assert(fake.positions==0U && fake.selections==0U && detector.calls==0U &&
        events.values.empty());
    assert(stats.scanner.stop_reason==LEO_SCANNER_STOP_SOURCE_ERROR);

    PortFake attestation_fake; setup_port_fake(attestation_fake);
    attestation_fake.caps.flags&=~LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION;
    leo_source_port attestation_port{};
    assert(leo_source_port_init(&attestation_port,&attestation_fake,&port_ops)==0);
    requirements.required_capability_flags&=
        ~LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION;
    stats={};
    assert(leo_scanner_run_source(&config,&attestation_port,&requirements,
        &detector_ops,collect_source,&events,&stats)==-ENOTSUP);
    assert(attestation_fake.positions==0U && attestation_fake.selections==0U &&
        detector.calls==0U && events.values.empty());
}

void test_common_port_rejects_invalid_authority_inputs_before_selection() {
    PortFake fake; setup_port_fake(fake);
    leo_source_port port{}; assert(leo_source_port_init(&port,&fake,&port_ops)==0);
    Detector detector; leo_scanner_detector_ops detector_ops{&detector,analyze,capabilities};
    auto config=scanner_config(1); auto requirements=exact_requirements();
    SourceEvents events; leo_scanner_source_stats stats{};

    requirements.require_physical_counter_qualified=2U;
    assert(leo_scanner_run_source(&config,&port,&requirements,&detector_ops,
        collect_source,&events,&stats)==-ENOTSUP);
    assert(fake.positions==0U && fake.selections==0U && detector.calls==0U &&
        events.values.empty());

    requirements=exact_requirements();
    config.targets[0].profile=LEO_SCANNER_MAX_TARGETS;
    assert(leo_scanner_run_source(&config,&port,&requirements,&detector_ops,
        collect_source,&events,&stats)==-EINVAL);
    assert(fake.positions==0U && fake.selections==0U && detector.calls==0U &&
        events.values.empty());
}

void test_delivered_ordinal_never_claims_physical_counter_or_crc() {
    PortFake fake; setup_port_fake(fake);
    fake.caps.counter_authority=LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    fake.caps.position_semantics=LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    fake.caps.flags&=~(LEO_SOURCE_CAP_EXACT_GAP|
        LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION);
    leo_source_port port{}; assert(leo_source_port_init(&port,&fake,&port_ops)==0);
    Detector detector; leo_scanner_detector_ops detector_ops{&detector,analyze,capabilities};
    auto config=scanner_config(1); config.targets[0].profile_crc32=0;
    auto requirements=exact_requirements();
    requirements.counter_authority=LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    requirements.position_semantics=LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    requirements.required_capability_flags=fake.caps.flags;
    requirements.required_transition_flags&=
        ~LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED;
    requirements.require_physical_counter_qualified=0;
    SourceEvents events; leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source(&config,&port,&requirements,&detector_ops,
        collect_source,&events,&stats)==0);
    assert(!stats.physical_counter_qualified &&
        stats.counter_authority==LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED);
    bool saw_visit=false;
    for (const auto& envelope:events.values) if (envelope.event.kind==LEO_SCANNER_VISIT) {
        saw_visit=true;
        assert(!envelope.physical_counter_qualified);
        assert(envelope.counter_authority==LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED);
        assert(!(envelope.transition_flags&LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED));
        assert(envelope.event.attested_profile_crc32==0U);
    }
    assert(saw_visit);
}

void test_unknown_discontinuity_is_incomplete_without_numeric_gap() {
    PortFake fake; setup_port_fake(fake);
    fake.caps.counter_authority=LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    fake.caps.position_semantics=LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    fake.caps.flags&=~(LEO_SOURCE_CAP_EXACT_GAP|
        LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION);
    fake.injected_block_flags=LEO_SOURCE_BLOCK_DISCONTINUITY|
        LEO_SOURCE_BLOCK_OVERFLOW_BEFORE;
    leo_source_port port{}; assert(leo_source_port_init(&port,&fake,&port_ops)==0);
    Detector detector; leo_scanner_detector_ops detector_ops{&detector,analyze,capabilities};
    auto config=scanner_config(1); config.targets[0].profile_crc32=0;
    auto requirements=exact_requirements();
    requirements.counter_authority=LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    requirements.position_semantics=LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    requirements.required_capability_flags=fake.caps.flags;
    requirements.required_transition_flags&=
        ~LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED;
    requirements.require_physical_counter_qualified=0;
    SourceEvents events; leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source(&config,&port,&requirements,&detector_ops,
        collect_source,&events,&stats)==0);
    assert(stats.scanner.visits_incomplete==1U &&
        stats.scanner.missing_samples==0U && detector.calls==0U);
    assert(stats.overflow_blocks>=1U && stats.discontinuity_blocks>=1U &&
        stats.unknown_discontinuities>=1U && stats.exact_missing_samples==0U);
}

void test_common_port_release_failure_is_retained_for_cleanup() {
    PortFake fake; setup_port_fake(fake); fake.release_failures=1;
    leo_source_port port{}; assert(leo_source_port_init(&port,&fake,&port_ops)==0);
    Detector detector; leo_scanner_detector_ops detector_ops{&detector,analyze,capabilities};
    auto config=scanner_config(1); auto requirements=exact_requirements();
    SourceEvents events; leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source(&config,&port,&requirements,&detector_ops,
        collect_source,&events,&stats)==-EIO);
    assert(port.outstanding_lease!=0U && fake.releases==1U && detector.calls==0U);
    assert(leo_source_port_cleanup(&port)==0 && fake.releases==2U &&
        port.outstanding_lease==0U);
}

void test_common_port_deadline_cancels_blocking_next() {
    PortFake fake; setup_port_fake(fake,true); fake.cancel_status=-EIO;
    leo_source_port port{};
    assert(leo_source_port_init(&port,&fake,&port_ops)==0);
    Detector detector; leo_scanner_detector_ops detector_ops{&detector,analyze,capabilities};
    auto config=scanner_config(1); auto requirements=exact_requirements();
    timespec now{}; assert(clock_gettime(CLOCK_MONOTONIC,&now)==0);
    config.wall_deadline_monotonic_ns=static_cast<std::uint64_t>(now.tv_sec)*
        UINT64_C(1000000000)+now.tv_nsec+UINT64_C(50000000);
    SourceEvents events; leo_scanner_source_stats stats{};
    const auto begun=std::chrono::steady_clock::now();
    assert(leo_scanner_run_source(&config,&port,&requirements,&detector_ops,
        collect_source,&events,&stats)==-ETIMEDOUT);
    assert(std::chrono::steady_clock::now()-begun<std::chrono::seconds(1));
    assert(fake.cancels>=1U && detector.calls==0U);
    assert(stats.scanner.stop_reason==LEO_SCANNER_STOP_WALL_DEADLINE);
}

void test_legacy_wrapper_transfers_persistent_release_to_source_close() {
    Device device; populate(device,1U,1000,false,120U,0U,0U);
    leo_local_provider_ops ops=provider(device);
    leo_local_config local=local_config();
    leo_local_source* source=nullptr;
    assert(leo_local_source_open(&local,&ops,&source)==0);
    leo_local_prime_receipt prime{};
    assert(leo_local_source_prime(source,&prime)==0);
    device.release_failures=2U;
    Detector detector; leo_scanner_detector_ops detector_ops{&detector,analyze,capabilities};
    auto config=scanner_config(1U); Events events; leo_scanner_stats stats{};
    assert(leo_scanner_run(&config,source,&detector_ops,collect,&events,&stats)==-EIO);
    assert(stats.stop_reason==LEO_SCANNER_STOP_SOURCE_ERROR &&
        stats.stop_status==-EIO && device.lease_outstanding);
    leo_local_restore_receipt restore{};
    assert(leo_local_source_close(source,&restore)==0);
    assert(!device.lease_outstanding);
}

void test_multi_context_routes_concurrently_and_drains_callbacks() {
    PortFake fake; fake.caps=port_capabilities(); add_port_blocks(fake,64U);
    leo_source_port port{}; assert(leo_source_port_init(&port,&fake,&port_ops)==0);
    ParallelCounters counters;
    ParallelDetector detectors[2]{{&counters,101U,300U},{&counters,202U,300U}};
    leo_scanner_detector_binding bindings[2]{parallel_binding(detectors[0]),
        parallel_binding(detectors[1])};
    const leo_scanner_execution_options execution{
        LEO_SCANNER_EXECUTION_ABI_VERSION,2U,bindings};
    auto config=scanner_config(8U); config.detector_queue_capacity=4U;
    auto requirements=exact_requirements(); SourceEvents events;
    leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source_ex(&config,&port,&requirements,&execution,
        collect_source,&events,&stats)==0);
    assert(counters.active.load()==0U && counters.maximum_active.load()==2U);
    assert(detectors[0].calls && detectors[1].calls);
    assert(stats.scanner.detector_accepted==6U &&
        stats.scanner.detector_completed==6U &&
        stats.scanner.detector_queue_drops==2U &&
        stats.scanner.detector_queue_high_water==4U);
    unsigned epoch101=0,epoch202=0;
    for (std::size_t i=0;i<events.values.size();++i) {
        const auto& event=events.values[i].event;
        if (event.kind!=LEO_SCANNER_CANDIDATE) continue;
        epoch101+=event.candidate.epoch==101;
        epoch202+=event.candidate.epoch==202;
        bool result_before=false;
        for (std::size_t j=0;j<i;++j)
            result_before|=events.values[j].event.kind==LEO_SCANNER_DETECTOR_RESULT &&
                events.values[j].event.visit==event.visit;
        assert(result_before);
    }
    assert(epoch101 && epoch202 && epoch101+epoch202==6U);
    const std::size_t callbacks_at_return=events.values.size();
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    assert(events.values.size()==callbacks_at_return);
}

void test_execution_validation_precedes_source_and_fails_closed() {
    PortFake fake; fake.caps=port_capabilities(); add_port_blocks(fake,8U);
    leo_source_port port{}; assert(leo_source_port_init(&port,&fake,&port_ops)==0);
    fake.capability_calls=0U;
    ParallelCounters counters;
    ParallelDetector first{&counters,1U,0U};
    ParallelDetector second{&counters,2U,0U}; second.capability_status=-EIO;
    leo_scanner_detector_binding bindings[2]{parallel_binding(first),
        parallel_binding(second)};
    leo_scanner_execution_options execution{
        LEO_SCANNER_EXECUTION_ABI_VERSION,2U,bindings};
    auto config=scanner_config(1U); auto requirements=exact_requirements();
    SourceEvents events; leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source_ex(&config,&port,&requirements,&execution,
        collect_source,&events,&stats)==-ENOTSUP);
    assert(fake.capability_calls==0U && fake.positions==0U && fake.selections==0U &&
        fake.next==0U && events.values.empty());
    assert(first.capability_calls==1U && second.capability_calls==1U);
    assert(stats.scanner.stop_reason==LEO_SCANNER_STOP_DETECTOR_ERROR);

    second.capability_status=0; bindings[1].configuration_digest[0]^=1U;
    stats={};
    assert(leo_scanner_run_source_ex(&config,&port,&requirements,&execution,
        collect_source,&events,&stats)==-EINVAL);
    assert(fake.capability_calls==0U && fake.positions==0U && fake.selections==0U);

    bindings[1]=parallel_binding(second);
    bindings[1].ops.context=bindings[0].ops.context;
    assert(leo_scanner_run_source_ex(&config,&port,&requirements,&execution,
        collect_source,&events,&stats)==-EINVAL);
    assert(fake.capability_calls==0U);

    bindings[1]=parallel_binding(second);
    requirements.abi_version=0U;
    assert(leo_scanner_run_source_ex(&config,&port,&requirements,&execution,
        collect_source,&events,&stats)==-EINVAL);
    assert(fake.capability_calls==0U);

    requirements=exact_requirements();
    first.process_serialized=1U;
    assert(leo_scanner_run_source_ex(&config,&port,&requirements,&execution,
        collect_source,&events,&stats)==-ENOTSUP);
    assert(fake.capability_calls==0U);
}

void test_four_context_bound_and_detector_failure_drain() {
    PortFake fake; fake.caps=port_capabilities(); add_port_blocks(fake,64U);
    leo_source_port port{}; assert(leo_source_port_init(&port,&fake,&port_ops)==0);
    ParallelCounters counters;
    ParallelDetector detectors[4]{{&counters,1U,250U},{&counters,2U,250U},
        {&counters,3U,250U},{&counters,4U,250U}};
    detectors[2].analyze_status=-EIO;
    leo_scanner_detector_binding bindings[4]{parallel_binding(detectors[0]),
        parallel_binding(detectors[1]),parallel_binding(detectors[2]),
        parallel_binding(detectors[3])};
    const leo_scanner_execution_options execution{
        LEO_SCANNER_EXECUTION_ABI_VERSION,4U,bindings};
    auto config=scanner_config(8U); config.detector_queue_capacity=4U;
    auto requirements=exact_requirements(); SourceEvents events;
    leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source_ex(&config,&port,&requirements,&execution,
        collect_source,&events,&stats)==0);
    assert(counters.active.load()==0U && counters.maximum_active.load()==4U);
    for (const auto& detector:detectors) assert(detector.calls);
    assert(stats.scanner.detector_accepted==8U &&
        stats.scanner.detector_completed+stats.scanner.detector_failures==8U &&
        stats.scanner.detector_failures==detectors[2].calls &&
        !stats.scanner.detector_queue_drops &&
        stats.scanner.detector_queue_high_water==4U);
    unsigned failures=0U;
    for (const auto& event:events.values)
        failures+=event.event.kind==LEO_SCANNER_DETECTOR_FAILURE;
    assert(failures==detectors[2].calls);
    const auto callbacks=events.values.size();
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    assert(events.values.size()==callbacks);
}

void test_new_single_context_requires_versioned_nonnull_binding() {
    PortFake fake; fake.caps=port_capabilities(); add_port_blocks(fake,8U);
    leo_source_port port{}; assert(leo_source_port_init(&port,&fake,&port_ops)==0);
    fake.capability_calls=0U;
    ParallelCounters counters; ParallelDetector detector{&counters,7U,0U};
    auto binding=parallel_binding(detector);
    leo_scanner_execution_options execution{
        LEO_SCANNER_EXECUTION_ABI_VERSION,1U,&binding};
    auto config=scanner_config(1U); auto requirements=exact_requirements();
    SourceEvents events; leo_scanner_source_stats stats{};

    binding.ops.context=nullptr;
    assert(leo_scanner_run_source_ex(&config,&port,&requirements,&execution,
        collect_source,&events,&stats)==-EINVAL);
    assert(fake.capability_calls==0U);
    binding=parallel_binding(detector); binding.abi_version=0U;
    assert(leo_scanner_run_source_ex(&config,&port,&requirements,&execution,
        collect_source,&events,&stats)==-EINVAL);
    assert(fake.capability_calls==0U);
    binding=parallel_binding(detector); execution.abi_version=0U;
    assert(leo_scanner_run_source_ex(&config,&port,&requirements,&execution,
        collect_source,&events,&stats)==-EINVAL);
    assert(fake.capability_calls==0U);
}

} // namespace

int main() {
    test_complete_active_fractional_evidence();
    test_gap_is_unknown_and_not_analyzed();
    test_single_worker_bounded_queue_reports_drop();
    test_four_entry_queue_bounds_burst_at_five_outstanding();
    test_active_feedback_expands_later_dwell();
    test_transition_timing_contract();
    test_same_profile_skips_recall_and_transition();
    test_four_target_hundred_ms_admission_with_twenty_ms_blocks();
    test_selection_uses_fresh_source_snapshot();
    test_timed_counter_runs_on_acquisition_lane_and_drives_policy();
    test_timed_counter_failures_stop_before_retune();
    test_legacy_counter_path_remains_source_owned();
    test_json_number_serializes_nonfinite_as_null();
    test_attested_tune_validation();
    test_deadline_cancels_blocking_source();
    test_worker_sink_failure_fails_run_and_releases_slot();
    test_disconnect_status_is_not_masked();
    test_exact_common_port_matches_legacy_science();
    test_common_port_rejects_missing_capability_before_selection();
    test_common_port_rejects_invalid_authority_inputs_before_selection();
    test_delivered_ordinal_never_claims_physical_counter_or_crc();
    test_unknown_discontinuity_is_incomplete_without_numeric_gap();
    test_common_port_release_failure_is_retained_for_cleanup();
    test_common_port_deadline_cancels_blocking_next();
    test_legacy_wrapper_transfers_persistent_release_to_source_close();
    test_multi_context_routes_concurrently_and_drains_callbacks();
    test_execution_validation_precedes_source_and_fails_closed();
    test_four_context_bound_and_detector_failure_drain();
    test_new_single_context_requires_versioned_nonnull_binding();
    return 0;
}
