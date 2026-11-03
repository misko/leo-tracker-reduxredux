#include "scanner.h"
#include "scanner_source.h"
#include "scanner_timing.h"
#include "../device/local/local_source_port.h"

extern "C" {
#include "../policy/spf-scan-policy.h"
}
#include "../runtime/runtime.hpp"

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstring>
#include <limits>
#include <memory>
#include <mutex>
#include <new>
#include <thread>
#include <time.h>
#include <vector>

namespace {

using leo::adaptive::Executor;
using leo::adaptive::Job;
using leo::adaptive::Visit;
using leo::adaptive::WindowAssembler;

constexpr uint8_t energy_digest[32] = {
    0xea,0xd1,0xaa,0x02,0x55,0xfe,0x03,0x9f,
    0xc7,0xbc,0x74,0x9c,0xa4,0x46,0x99,0x91,
    0xdd,0x95,0xe0,0x16,0x8c,0x0c,0xc8,0x4b,
    0x3c,0x23,0x23,0xde,0x35,0xff,0xef,0x84
};

/* Measured under concurrent detector and location load: the interval from a
 * visit's valid end to the next valid start reached 95.8832 ms. Admission uses
 * a bounded 100 ms execution slot; physical Fast Lock settling remains the
 * independently applied config transition (20 ms in the qualified CLI). */
constexpr uint32_t policy_admission_transition_ms = 100U;

bool add_u64(uint64_t a, uint64_t b, uint64_t& result) {
    if (a > std::numeric_limits<uint64_t>::max() - b) return false;
    result = a + b;
    return true;
}

bool valid_config(const leo_scanner_config* c, bool require_profile_crc = true,
                  uint32_t detector_workers = 1U) {
    if (!c || c->abi_version != LEO_SCANNER_ABI_VERSION || !c->session ||
        !c->generation || !c->seed || c->sample_rate_hz != 2500000U ||
        c->receiver_count != 2U || !c->duration_ms || c->duration_ms > 1800000U ||
        !c->maximum_visits || c->maximum_visits > SPF_SCAN_MAX_VISITS ||
        !c->wall_deadline_monotonic_ns ||
        (c->dwell_ms != 120U && c->dwell_ms != 240U && c->dwell_ms != 360U) ||
        !c->transition_budget_ms || c->transition_budget_ms > 50U ||
        !c->maximum_revisit_ms ||
        !c->feedback_age_ms || !c->application_delay_ms || !c->decay_ms ||
        !c->maximum_boost || !c->detector_queue_capacity ||
        c->detector_queue_capacity > 16U ||
        c->active_threshold_dbfs != -38.0 || !c->target_count ||
        c->target_count > LEO_SCANNER_MAX_TARGETS || !detector_workers ||
        detector_workers > LEO_SCANNER_MAX_DETECTOR_WORKERS)
        return false;
    uint32_t profiles = 0;
    for (uint32_t i = 0; i < c->target_count; ++i) {
        const leo_scanner_target& t = c->targets[i];
        if (t.profile >= LEO_SCANNER_MAX_TARGETS || !t.frequency_hz ||
            (require_profile_crc && !t.profile_crc32) || !t.baseline_weight ||
            (profiles & (UINT32_C(1) << t.profile)))
            return false;
        profiles |= UINT32_C(1) << t.profile;
    }
    const uint64_t dwell_times = static_cast<uint64_t>(c->sample_rate_hz) * c->dwell_ms / 1000U;
    const uint64_t dwell_bytes = dwell_times * c->receiver_count * 4U;
    return dwell_times <= SIZE_MAX && dwell_bytes <= SIZE_MAX &&
        dwell_bytes <= UINT64_C(268435456) /
            (static_cast<uint64_t>(c->detector_queue_capacity) +
             detector_workers + 1U);
}

bool same_capabilities(const leo_native_glrt_capabilities& a,
                       const leo_native_glrt_capabilities& b) {
    return a.abi_version == b.abi_version &&
        a.receiver_count == b.receiver_count && a.probe_ms == b.probe_ms &&
        a.process_serialized == b.process_serialized &&
        a.candidate_cfo_refinement_state_available ==
            b.candidate_cfo_refinement_state_available &&
        a.fractional_epoch_mode_available == b.fractional_epoch_mode_available &&
        a.fractional_epoch_server_parity_qualified ==
            b.fractional_epoch_server_parity_qualified;
}

bool digest_nonzero(const uint8_t digest[32]) {
    uint8_t combined = 0;
    for (size_t i = 0; i < 32U; ++i) combined |= digest[i];
    return combined != 0;
}

struct DetectorExecution {
    const leo_scanner_detector_binding* bindings = nullptr;
    uint32_t count = 0;
    leo_native_glrt_capabilities capabilities{};
    bool prevalidated = false;
};

int validate_execution(const leo_scanner_config* config, bool require_crc,
                       const leo_scanner_execution_options* execution,
                       DetectorExecution& prepared) {
    if (!execution || execution->abi_version != LEO_SCANNER_EXECUTION_ABI_VERSION ||
        !execution->detectors || !execution->detector_worker_count ||
        execution->detector_worker_count > LEO_SCANNER_MAX_DETECTOR_WORKERS ||
        !valid_config(config, require_crc, execution->detector_worker_count))
        return -EINVAL;
    const uint32_t count = execution->detector_worker_count;
    for (uint32_t i = 0; i < count; ++i) {
        const leo_scanner_detector_binding& binding = execution->detectors[i];
        if (binding.abi_version != LEO_SCANNER_EXECUTION_ABI_VERSION ||
            !binding.ops.context || !binding.ops.analyze ||
            !binding.ops.capabilities ||
            !digest_nonzero(binding.configuration_digest))
            return -EINVAL;
        for (uint32_t j = 0; j < i; ++j) {
            if (binding.ops.context == execution->detectors[j].ops.context)
                return -EINVAL;
        }
        if (i && std::memcmp(binding.configuration_digest,
                execution->detectors[0].configuration_digest, 32U))
            return -EINVAL;
        leo_native_glrt_capabilities capabilities{};
        if (binding.ops.capabilities(binding.ops.context, &capabilities) ||
            capabilities.abi_version != LEO_NATIVE_GLRT_ABI_VERSION ||
            capabilities.receiver_count != 2U || capabilities.probe_ms != 20U ||
            !capabilities.fractional_epoch_mode_available ||
            (count > 1U && capabilities.process_serialized))
            return -ENOTSUP;
        if (!i) prepared.capabilities = capabilities;
        else if (!same_capabilities(prepared.capabilities, capabilities))
            return -ENOTSUP;
    }
    prepared.bindings = execution->detectors;
    prepared.count = count;
    prepared.prevalidated = true;
    return 0;
}

bool physical_counter_capabilities(const leo_source_capabilities& c) {
    constexpr uint32_t flags = LEO_SOURCE_CAP_CANCEL | LEO_SOURCE_CAP_SELECT |
        LEO_SOURCE_CAP_SIMULTANEOUS_RX | LEO_SOURCE_CAP_COHERENT_RX |
        LEO_SOURCE_CAP_EXACT_GAP | LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    return c.counter_authority == LEO_SOURCE_COUNTER_PROVIDER_EXACT &&
        c.position_semantics == LEO_SOURCE_POSITION_COHERENT_CURRENT &&
        (c.flags & flags) == flags;
}

bool valid_requirement_shape(const leo_scanner_source_requirements* r) {
    constexpr uint32_t all_capability_flags = LEO_SOURCE_CAP_CANCEL |
        LEO_SOURCE_CAP_SELECT | LEO_SOURCE_CAP_SIMULTANEOUS_RX |
        LEO_SOURCE_CAP_COHERENT_RX | LEO_SOURCE_CAP_FREQUENCY_ATTESTATION |
        LEO_SOURCE_CAP_TARGET_ATTESTATION |
        LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION | LEO_SOURCE_CAP_EXACT_GAP |
        LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    constexpr uint32_t all_transition_flags =
        LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
        LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
        LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED |
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY |
        LEO_SOURCE_TRANSITION_VALID_TIME_BOUNDARY;
    return r && r->abi_version == LEO_SCANNER_SOURCE_ABI_VERSION &&
        r->counter_authority && r->position_semantics &&
        r->maximum_frequency_error_hz &&
        r->maximum_frequency_error_hz <= 1000000U &&
        r->require_physical_counter_qualified <= 1U &&
        !(r->required_capability_flags & ~all_capability_flags) &&
        !(r->required_transition_flags & ~all_transition_flags);
}

bool valid_requirements(const leo_scanner_source_requirements* r,
                        const leo_source_capabilities& c) {
    if (!valid_requirement_shape(r) ||
        c.sample_format != LEO_SOURCE_SAMPLE_FORMAT_CI16 ||
        c.sample_rate_hz != 2500000U || c.receiver_count != 2U ||
        !(c.flags & LEO_SOURCE_CAP_SIMULTANEOUS_RX) ||
        !(c.flags & LEO_SOURCE_CAP_COHERENT_RX) ||
        c.counter_authority != r->counter_authority ||
        c.position_semantics != r->position_semantics ||
        (c.flags & r->required_capability_flags) != r->required_capability_flags)
        return false;
    uint32_t transition_capabilities = 0;
    if (r->required_transition_flags & LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED)
        transition_capabilities |= LEO_SOURCE_CAP_FREQUENCY_ATTESTATION;
    if (r->required_transition_flags & LEO_SOURCE_TRANSITION_TARGET_ATTESTED)
        transition_capabilities |= LEO_SOURCE_CAP_TARGET_ATTESTATION;
    if (r->required_transition_flags & LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED)
        transition_capabilities |= LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION;
    if (r->required_transition_flags & LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY)
        transition_capabilities |= LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    if ((c.flags & transition_capabilities) != transition_capabilities ||
        ((r->required_transition_flags & LEO_SOURCE_TRANSITION_VALID_TIME_BOUNDARY) &&
         c.time_authority == LEO_SOURCE_TIME_NONE))
        return false;
    return !r->require_physical_counter_qualified || physical_counter_capabilities(c);
}

struct State;

struct SourceAuthority {
    uint32_t counter_authority = 0;
    uint32_t position_semantics = 0;
    uint32_t time_authority = 0;
    uint32_t transition_flags = 0;
    uint32_t block_flags = 0;
    uint32_t physical_counter_qualified = 0;
};

struct Slot {
    std::atomic<bool> occupied{false};
    State* owner = nullptr;
    uint64_t visit = 0, valid_start = 0, valid_end = 0;
    uint64_t selection_counter = 0, transition_before = 0, transition_after = 0;
    uint32_t target = 0, profile = 0, profile_crc32 = 0, dwell_ms = 0;
    uint32_t recalled = 0;
    uint64_t frequency_hz = 0;
    SourceAuthority authority{};
    uint64_t detector_enqueued_monotonic_ns = 0;
    uint64_t detector_started_monotonic_ns = 0;
    uint64_t detector_finished_monotonic_ns = 0;
    uint32_t detector_row_count = 0;
    std::vector<int16_t> iq;
};

struct State {
    const leo_scanner_config& config;
    const leo_scanner_detector_binding* detectors;
    uint32_t detector_count;
    leo_scanner_event_sink sink;
    leo_scanner_source_event_sink source_sink;
    void* sink_context;
    leo_scanner_stats stats{};
    leo_native_glrt_capabilities capabilities{};
    SourceAuthority default_authority{};
    uint64_t overflow_blocks = 0;
    uint64_t discontinuity_blocks = 0;
    uint64_t unknown_discontinuities = 0;
    uint64_t exact_missing_samples = 0;
    std::mutex output;
    std::unique_ptr<Slot[]> slots;
    size_t slot_count;

    State(const leo_scanner_config& c, const leo_scanner_detector_binding* d,
          uint32_t detector_workers,
          leo_scanner_event_sink s, leo_scanner_source_event_sink ss,
          void* context, SourceAuthority authority,
          const leo_native_glrt_capabilities& detector_capabilities)
        : config(c), detectors(d), detector_count(detector_workers), sink(s),
          source_sink(ss), sink_context(context),
          capabilities(detector_capabilities),
          default_authority(authority),
          slots(new Slot[c.detector_queue_capacity + detector_workers]),
          slot_count(c.detector_queue_capacity + detector_workers) {
        for (size_t i = 0; i < slot_count; ++i) slots[i].owner = this;
    }

    void emit_unlocked(const leo_scanner_event& event,
                       const SourceAuthority& authority) {
        if (sink) sink(sink_context, &event);
        if (source_sink) {
            leo_scanner_source_event envelope{};
            envelope.abi_version = LEO_SCANNER_SOURCE_ABI_VERSION;
            envelope.event = event;
            envelope.counter_authority = authority.counter_authority;
            envelope.position_semantics = authority.position_semantics;
            envelope.time_authority = authority.time_authority;
            envelope.transition_flags = authority.transition_flags;
            envelope.block_flags = authority.block_flags;
            envelope.physical_counter_qualified =
                authority.physical_counter_qualified;
            source_sink(sink_context, &envelope);
        }
    }

    void emit(const leo_scanner_event& event,
              const SourceAuthority& authority) {
        std::lock_guard<std::mutex> lock(output);
        emit_unlocked(event, authority);
    }

    void change(void (*update)(leo_scanner_stats&)) {
        std::lock_guard<std::mutex> lock(output);
        update(stats);
    }
};

struct SourceStatsCommit {
    leo_scanner_source_stats* destination;
    leo_scanner_stats* scanner;
    State* state;
    leo_source_capabilities capabilities;
    ~SourceStatsCommit() {
        if (!destination) return;
        destination->abi_version = LEO_SCANNER_SOURCE_ABI_VERSION;
        destination->scanner = *scanner;
        destination->overflow_blocks = state->overflow_blocks;
        destination->discontinuity_blocks = state->discontinuity_blocks;
        destination->unknown_discontinuities = state->unknown_discontinuities;
        destination->exact_missing_samples = state->exact_missing_samples;
        destination->counter_authority = capabilities.counter_authority;
        destination->position_semantics = capabilities.position_semantics;
        destination->time_authority = capabilities.time_authority;
        destination->physical_counter_qualified =
            physical_counter_capabilities(capabilities) ? 1U : 0U;
    }
};

leo_scanner_event base_event(const Slot& slot, uint32_t kind) {
    leo_scanner_event event{};
    event.kind = kind;
    event.visit = slot.visit;
    event.valid_start = slot.valid_start;
    event.valid_end = slot.valid_end;
    event.selection_counter = slot.selection_counter;
    event.transition_counter_before = slot.transition_before;
    event.transition_counter_after = slot.transition_after;
    event.recalled = slot.recalled;
    event.target = slot.target;
    event.profile = slot.profile;
    event.attested_profile_crc32 = slot.profile_crc32;
    event.frequency_hz = slot.frequency_hz;
    event.fractional_epoch_server_parity_qualified =
        slot.owner->capabilities.fractional_epoch_server_parity_qualified;
    event.detector_enqueued_monotonic_ns = slot.detector_enqueued_monotonic_ns;
    event.detector_started_monotonic_ns = slot.detector_started_monotonic_ns;
    event.detector_finished_monotonic_ns = slot.detector_finished_monotonic_ns;
    if (slot.detector_started_monotonic_ns >= slot.detector_enqueued_monotonic_ns)
        event.detector_queue_ns = slot.detector_started_monotonic_ns -
            slot.detector_enqueued_monotonic_ns;
    if (slot.detector_finished_monotonic_ns >= slot.detector_started_monotonic_ns)
        event.detector_runtime_ns = slot.detector_finished_monotonic_ns -
            slot.detector_started_monotonic_ns;
    event.detector_row_count = slot.detector_row_count;
    return event;
}

int monotonic_ns(uint64_t& value);

void detector_job(void* context, size_t worker) {
    Slot& slot = *static_cast<Slot*>(context);
    struct SlotRelease {
        Slot& slot;
        ~SlotRelease() { slot.occupied.store(false, std::memory_order_release); }
    } release{slot};
    State& state = *slot.owner;
    leo_native_glrt_result result{};
    (void)monotonic_ns(slot.detector_started_monotonic_ns);
    const leo_scanner_detector_ops& detector = state.detectors[worker].ops;
    const int status = detector.analyze(detector.context, slot.iq.data(),
        slot.iq.size() / 4U, slot.dwell_ms, 120U, &result);
    (void)monotonic_ns(slot.detector_finished_monotonic_ns);
    slot.detector_row_count = static_cast<uint32_t>(std::min(result.row_count,
        static_cast<size_t>(UINT32_MAX)));
    if (status) {
        leo_scanner_event event = base_event(slot, LEO_SCANNER_DETECTOR_FAILURE);
        event.detector_status = status;
        {
            std::lock_guard<std::mutex> lock(state.output);
            ++state.stats.detector_failures;
            state.emit_unlocked(event, slot.authority);
        }
        return;
    }
    leo_scanner_event completed = base_event(slot, LEO_SCANNER_DETECTOR_RESULT);
    {
        std::lock_guard<std::mutex> lock(state.output);
        ++state.stats.detector_completed;
        state.stats.detector_rows += result.row_count;
        state.emit_unlocked(completed, slot.authority);
    }
    const size_t rows = std::min(result.row_count,
        static_cast<size_t>(LEO_NATIVE_GLRT_MAX_ROWS));
    for (size_t r = 0; r < rows; ++r) {
        const leo_native_glrt_row& row = result.rows[r];
        const int count = std::max(0, std::min(row.candidate_count,
            static_cast<int32_t>(LEO_NATIVE_GLRT_MAX_CANDIDATES)));
        for (int c = 0; c < count; ++c) {
            leo_scanner_event event = base_event(slot, LEO_SCANNER_CANDIDATE);
            event.row_index = static_cast<uint32_t>(r);
            event.candidate_index = static_cast<uint32_t>(c);
            event.receiver_id = row.receiver_id;
            event.probe_index = row.probe_index;
            event.candidate = row.candidates[c];
            {
                std::lock_guard<std::mutex> lock(state.output);
                ++state.stats.detector_candidates;
                state.emit_unlocked(event, slot.authority);
            }
        }
    }
}

Slot* reserve_slot(State& state) {
    for (size_t i = 0; i < state.slot_count; ++i) {
        bool expected = false;
        if (state.slots[i].occupied.compare_exchange_strong(expected, true,
                std::memory_order_acq_rel))
            return &state.slots[i];
    }
    return nullptr;
}

uint64_t energy_rx1(const int16_t* iq, size_t times) {
    uint64_t sum = 0;
    for (size_t i = 0; i < times; ++i) {
        const int64_t in_phase = iq[4U * i];
        const int64_t quadrature = iq[4U * i + 1U];
        sum += static_cast<uint64_t>(in_phase * in_phase + quadrature * quadrature);
    }
    return sum;
}

double power_dbfs(uint64_t energy, uint64_t times) {
    if (!energy || !times) return -std::numeric_limits<double>::infinity();
    const double mean_component = static_cast<double>(energy) /
        (2.0 * static_cast<double>(times));
    return 10.0 * std::log10(mean_component / (32768.0 * 32768.0));
}

void drain_acks(struct spf_scan_policy* policy, State& state) {
    spf_scan_ack ack{};
    while (spf_scan_policy_take_ack(policy, &ack) == 0) {
        leo_scanner_event event{};
        event.kind = LEO_SCANNER_POLICY_ACK;
        event.visit = ack.source_visit;
        event.target = ack.target;
        event.valid_start = ack.application_counter;
        std::lock_guard<std::mutex> lock(state.output);
        ++state.stats.policy_acks;
        state.emit_unlocked(event, state.default_authority);
    }
}

int monotonic_ns(uint64_t& value) {
    struct timespec now{};
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return -errno;
    value = static_cast<uint64_t>(now.tv_sec) * UINT64_C(1000000000) +
        static_cast<uint64_t>(now.tv_nsec);
    return 0;
}

struct DeadlineGuard {
    leo_source_port* source;
    uint64_t deadline;
    std::mutex mutex;
    std::condition_variable changed;
    bool finished = false;
    std::atomic<bool> expired{false};
    std::thread worker;

    DeadlineGuard(leo_source_port* value, uint64_t deadline, uint64_t now)
        : source(value), deadline(deadline), worker([this, deadline, now] {
            std::unique_lock<std::mutex> lock(mutex);
            const auto wait = std::chrono::nanoseconds(deadline - now);
            if (!changed.wait_for(lock, wait, [this] { return finished; })) {
                expired.store(true, std::memory_order_release);
                (void)leo_source_port_cancel(source);
            }
        }) {}
    bool finish() {
        bool cancel = false;
        {
            std::lock_guard<std::mutex> lock(mutex);
            if (!finished) {
                uint64_t now = 0;
                if (monotonic_ns(now) || now >= deadline) {
                    expired.store(true, std::memory_order_release);
                    cancel = true;
                }
                finished = true;
            }
        }
        if (cancel) (void)leo_source_port_cancel(source);
        changed.notify_one();
        if (worker.joinable()) worker.join();
        return expired.load(std::memory_order_acquire);
    }
    ~DeadlineGuard() { (void)finish(); }
};

struct BlockLease {
    leo_source_port* source;
    leo_source_block* block;
    bool active = true;
    ~BlockLease() { if (active) (void)leo_source_port_release(source, block); }
    int release() {
        if (!active) return 0;
        active = false;
        return leo_source_port_release(source, block);
    }
};

int acquire_counter(leo_source_port* source,
    const leo_scanner_counter_ops* counter, uint64_t& value) {
    if (!counter) {
        leo_source_position position{};
        const int status = leo_source_port_position(source, &position);
        if (!status) value = position.coordinate;
        return status;
    }
    const int status = counter->snapshot(counter->context, &value);
    return status > 0 ? -EIO : status;
}

} // namespace

static int scanner_run_impl(const leo_scanner_config* config,
    leo_source_port* source, const leo_scanner_counter_ops* counter,
    const leo_scanner_source_requirements* requirements,
    const DetectorExecution& execution, leo_scanner_event_sink sink,
    leo_scanner_source_event_sink source_sink, void* sink_context,
    leo_scanner_stats* output, leo_scanner_source_stats* source_output) {
    if (output) std::memset(output, 0, sizeof(*output));
    if (source_output) std::memset(source_output, 0, sizeof(*source_output));
    leo_source_capabilities source_capabilities{};
    const bool require_crc = !requirements ||
        (requirements->required_transition_flags &
            LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED);
    if (!valid_config(config, require_crc, execution.count) || !source ||
        !execution.bindings || !execution.count ||
        (counter && !counter->snapshot) || !output)
        return -EINVAL;
    int capability_status = leo_source_port_capabilities(source, &source_capabilities);
    if (capability_status || (requirements &&
            !valid_requirements(requirements, source_capabilities))) {
        output->stop_reason = LEO_SCANNER_STOP_SOURCE_ERROR;
        output->stop_status = capability_status ? capability_status : -ENOTSUP;
        return output->stop_status;
    }
    SourceAuthority source_authority{};
    source_authority.counter_authority = source_capabilities.counter_authority;
    source_authority.position_semantics = source_capabilities.position_semantics;
    source_authority.time_authority = source_capabilities.time_authority;
    source_authority.physical_counter_qualified =
        physical_counter_capabilities(source_capabilities) ? 1U : 0U;
    try {
        leo_native_glrt_capabilities detector_capabilities = execution.capabilities;
        if (!execution.prevalidated) {
            const leo_scanner_detector_ops& detector = execution.bindings[0].ops;
            if (!detector.analyze || !detector.capabilities ||
                detector.capabilities(detector.context, &detector_capabilities) ||
                detector_capabilities.abi_version != LEO_NATIVE_GLRT_ABI_VERSION ||
                detector_capabilities.receiver_count != 2U ||
                detector_capabilities.probe_ms != 20U ||
                !detector_capabilities.fractional_epoch_mode_available) {
                output->stop_reason = LEO_SCANNER_STOP_DETECTOR_ERROR;
                output->stop_status = -ENOTSUP;
                return -ENOTSUP;
            }
        }
        State state(*config, execution.bindings, execution.count, sink, source_sink,
            sink_context, source_authority, detector_capabilities);
        SourceStatsCommit source_commit{source_output, output, &state,
            source_capabilities};
        uint64_t wall_now = 0;
        int ret = monotonic_ns(wall_now);
        if (ret) {
            output->stop_reason = LEO_SCANNER_STOP_INTERNAL_ERROR;
            output->stop_status = ret;
            return ret;
        }
        if (wall_now >= config->wall_deadline_monotonic_ns) {
            output->stop_reason = LEO_SCANNER_STOP_WALL_DEADLINE;
            output->stop_status = -ETIMEDOUT;
            return -ETIMEDOUT;
        }
        DeadlineGuard wall_guard(source, config->wall_deadline_monotonic_ns, wall_now);

        spf_scan_policy_config policy_config{};
        policy_config.session = config->session;
        policy_config.generation = config->generation;
        policy_config.seed = config->seed;
        policy_config.protocol_version = SPF_SCAN_RANDOM_DWELL_VERSION;
        policy_config.source_rate_hz = config->sample_rate_hz;
        policy_config.targets = config->target_count;
        /* The continuous extension retains state beyond the original policy's
         * five-minute admission maximum; the application deadline remains the
         * authoritative (and independently bounded) run duration. */
        policy_config.duration_ms = std::min(config->duration_ms, 300000U);
        policy_config.dwell_ms = config->dwell_ms;
        /* This is an execution-admission bound, not an RF settling interval. */
        policy_config.transition_budget_ms = policy_admission_transition_ms;
        policy_config.maximum_revisit_ms = config->maximum_revisit_ms;
        policy_config.feedback_age_ms = config->feedback_age_ms;
        policy_config.application_delay_ms = config->application_delay_ms;
        policy_config.decay_ms = config->decay_ms;
        policy_config.maximum_boost = config->maximum_boost;
        std::memcpy(policy_config.analysis_digest, energy_digest, sizeof(energy_digest));
        for (uint32_t i = 0; i < config->target_count; ++i)
            policy_config.baseline[i] = config->targets[i].baseline_weight;
        if (spf_scan_policy_validate(&policy_config)) {
            output->stop_reason = LEO_SCANNER_STOP_POLICY_ERROR;
            output->stop_status = -EINVAL;
            return -EINVAL;
        }

        uint64_t now = 0;
        ret = acquire_counter(source, counter, now);
        if (ret) {
            output->stop_reason = LEO_SCANNER_STOP_SOURCE_ERROR;
            output->stop_status = ret;
            return ret;
        }
        const uint64_t duration_ticks =
            static_cast<uint64_t>(config->sample_rate_hz) * config->duration_ms / 1000U;
        uint64_t deadline = 0;
        if (!add_u64(now, duration_ticks, deadline)) {
            output->stop_reason = LEO_SCANNER_STOP_INTERNAL_ERROR;
            output->stop_status = -EOVERFLOW;
            return -EOVERFLOW;
        }
        struct spf_scan_policy* policy = nullptr;
        ret = leo_scan_policy_create_continuous(&policy, &policy_config, now);
        if (ret) {
            output->stop_reason = LEO_SCANNER_STOP_POLICY_ERROR;
            output->stop_status = ret;
            return ret;
        }
        std::unique_ptr<spf_scan_policy, void(*)(spf_scan_policy*)> policy_owner(
            policy, spf_scan_policy_destroy);
        Executor executor(execution.count, config->detector_queue_capacity);

        const size_t dwell_times = static_cast<size_t>(config->sample_rate_hz) *
            config->dwell_ms / 1000U;
        std::vector<int16_t> dwell;
        dwell.reserve(dwell_times * 4U);
        const uint64_t transition_ticks = static_cast<uint64_t>(config->sample_rate_hz) *
            config->transition_budget_ms / 1000U;
        bool current_profile_valid = false;
        uint32_t current_profile = 0;
        uint32_t current_profile_crc32 = 0;
        uint64_t current_frequency_hz = 0;

        uint32_t iteration = 0;
        for (; iteration < config->maximum_visits && now < deadline; ++iteration) {
            ret = acquire_counter(source, counter, now);
            if (ret) {
                state.stats.stop_reason = LEO_SCANNER_STOP_SOURCE_ERROR;
                state.stats.stop_status = ret;
                spf_scan_policy_stop(policy, now);
                break;
            }
            uint64_t minimum_end = 0;
            if (!add_u64(now, transition_ticks + dwell_times, minimum_end) ||
                minimum_end > deadline) {
                state.stats.stop_reason = LEO_SCANNER_STOP_SOURCE_DURATION;
                break;
            }
            spf_scan_choice choice{};
            ret = spf_scan_policy_select(policy, now, &choice);
            if (ret) {
                if (ret == -ENODATA) {
                    ret = 0;
                    state.stats.stop_reason = LEO_SCANNER_STOP_POLICY_COMPLETE;
                } else {
                    state.stats.stop_reason = LEO_SCANNER_STOP_POLICY_ERROR;
                    state.stats.stop_status = ret;
                }
                break;
            }
            drain_acks(policy, state);
            const leo_scanner_target& target = config->targets[choice.target];
            leo_source_transition transition{};
            const bool recalled = !current_profile_valid ||
                current_profile != target.profile;
            if (recalled) {
                leo_source_selection selection{};
                selection.target_key = target.profile;
                selection.requested_frequency_hz = target.frequency_hz;
                selection.maximum_frequency_error_hz = requirements ?
                    requirements->maximum_frequency_error_hz : 2U;
                ret = leo_source_port_select(source, &selection, &transition);
                if (ret) {
                    state.stats.stop_reason = LEO_SCANNER_STOP_SOURCE_ERROR;
                    state.stats.stop_status = ret;
                    spf_scan_policy_stop(policy, now);
                    break;
                }
            } else {
                /* Preserve the last post-recall attestation and do not create
                 * an invalid interval when the shared LO is already correct. */
                transition.selected_target_key = current_profile;
                transition.actual_frequency_hz = current_frequency_hz;
                transition.profile_crc32 = current_profile_crc32;
                transition.previous_valid_end = now;
                transition.valid_start = now;
                transition.counter_authority = source_capabilities.counter_authority;
                transition.position_semantics = source_capabilities.position_semantics;
                transition.time_authority = source_capabilities.time_authority;
                transition.flags = source_authority.transition_flags;
            }
            const uint64_t frequency_error =
                transition.actual_frequency_hz >= target.frequency_hz ?
                transition.actual_frequency_hz - target.frequency_hz :
                target.frequency_hz - transition.actual_frequency_hz;
            const uint32_t needed_transition = requirements ?
                requirements->required_transition_flags :
                (LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
                 LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
                 LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED |
                 LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY);
            const uint64_t allowed_frequency_error = requirements ?
                requirements->maximum_frequency_error_hz : 2U;
            if (transition.selected_target_key != target.profile ||
                frequency_error > allowed_frequency_error ||
                (transition.flags & needed_transition) != needed_transition ||
                ((needed_transition & LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED) &&
                 !transition.profile_crc32)) {
                ret = -EPROTO;
                state.stats.stop_reason = LEO_SCANNER_STOP_SOURCE_ERROR;
                state.stats.stop_status = ret;
                spf_scan_policy_stop(policy, transition.valid_start);
                break;
            }
            if (recalled) {
                current_profile_valid = true;
                current_profile = transition.selected_target_key;
                current_profile_crc32 = transition.profile_crc32;
                current_frequency_hz = transition.actual_frequency_hz;
                source_authority.transition_flags = transition.flags;
            }
            uint64_t valid_start = 0, valid_end = 0;
            const uint64_t choice_times = static_cast<uint64_t>(config->sample_rate_hz) *
                choice.dwell_ms / 1000U;
            ret = leo_scanner_valid_start(choice.selection_counter,
                transition.valid_start, transition_ticks, recalled, valid_start);
            if (ret) {
                state.stats.stop_reason = LEO_SCANNER_STOP_INTERNAL_ERROR;
                state.stats.stop_status = ret;
                spf_scan_policy_stop(policy, transition.valid_start);
                break;
            }
            if (!add_u64(valid_start, choice_times, valid_end) || valid_end > deadline) {
                state.stats.stop_reason = LEO_SCANNER_STOP_SOURCE_DURATION;
                spf_scan_policy_stop(policy, transition.valid_start);
                break;
            }
            ret = spf_scan_policy_commit(policy, valid_start);
            if (ret) {
                state.stats.stop_reason = LEO_SCANNER_STOP_POLICY_ERROR;
                state.stats.stop_status = ret;
                spf_scan_policy_stop(policy, transition.valid_start);
                break;
            }

            uint32_t emitted = 0;
            WindowAssembler assembler(config->sample_rate_hz, config->receiver_count,
                [&emitted](const leo::adaptive::Window&) { ++emitted; });
            assembler.begin(Visit{config->generation, choice.visit, valid_start, valid_end,
                config->sample_rate_hz, config->receiver_count,
                static_cast<double>(transition.actual_frequency_hz)});
            dwell.clear();
            uint64_t expected = valid_start;
            uint64_t energy = 0;
            uint64_t energy_times = 0;
            bool intact = true;
            int capture_status = 0;
            SourceAuthority visit_authority = source_authority;
            visit_authority.transition_flags = transition.flags;
            while (expected < valid_end) {
                leo_source_block block{};
                ret = leo_source_port_next(source, &block);
                if (ret) { capture_status = ret; intact = false; break; }
                BlockLease lease{source, &block};
                now = std::max(now, block.end_coordinate);
                visit_authority.block_flags |= block.flags;
                if (block.flags & LEO_SOURCE_BLOCK_OVERFLOW_BEFORE) {
                    ++state.overflow_blocks;
                    intact = false;
                }
                if (block.flags & LEO_SOURCE_BLOCK_DISCONTINUITY) {
                    ++state.discontinuity_blocks;
                    if (block.flags & LEO_SOURCE_BLOCK_GAP_EXACT) {
                        state.exact_missing_samples += block.missing_samples_before;
                    } else {
                        ++state.unknown_discontinuities;
                        intact = false;
                    }
                }
                leo_source_slice slice{};
                const int clip = leo_source_block_clip(&block, valid_start, valid_end, &slice);
                if (!clip) {
                    const int16_t* iq = slice.ci16;
                    if (slice.first_coordinate != expected) {
                        intact = false;
                        if (slice.first_coordinate > expected) {
                            std::lock_guard<std::mutex> lock(state.output);
                            state.stats.missing_samples += slice.first_coordinate - expected;
                        }
                    }
                    assembler.push(slice.first_coordinate, iq, slice.samples_per_receiver);
                    if (intact) dwell.insert(dwell.end(), iq,
                        iq + static_cast<size_t>(slice.samples_per_receiver) * 4U);
                    energy += energy_rx1(iq, slice.samples_per_receiver);
                    energy_times += slice.samples_per_receiver;
                    expected = slice.first_coordinate + slice.samples_per_receiver;
                } else if (clip != -ENODATA) {
                    capture_status = clip;
                    intact = false;
                }
                const uint64_t block_end = block.end_coordinate;
                const int release = lease.release();
                if (release) { capture_status = release; intact = false; break; }
                if (capture_status) break;
                if (block_end >= valid_end) break;
            }
            assembler.finish();
            intact = intact && expected == valid_end &&
                dwell.size() == static_cast<size_t>(choice_times) * 4U;
            const int finish_status =
                spf_scan_policy_finish_visit(policy, choice.visit, intact);
            if (finish_status) {
                ret = finish_status;
                state.stats.stop_reason = LEO_SCANNER_STOP_POLICY_ERROR;
                state.stats.stop_status = ret;
                spf_scan_policy_stop(policy, now);
                break;
            }

            const double dbfs = power_dbfs(energy, energy_times);
            const uint32_t outcome = !intact ? LEO_SCANNER_UNKNOWN :
                (dbfs >= config->active_threshold_dbfs ? LEO_SCANNER_ACTIVE :
                    LEO_SCANNER_QUIET);
            leo_scanner_event visit{};
            visit.kind = LEO_SCANNER_VISIT;
            visit.visit = choice.visit;
            visit.valid_start = valid_start;
            visit.valid_end = valid_end;
            visit.selection_counter = choice.selection_counter;
            visit.transition_counter_before = transition.previous_valid_end;
            visit.transition_counter_after = transition.valid_start;
            visit.recalled = recalled ? 1U : 0U;
            visit.target = choice.target;
            visit.profile = transition.selected_target_key;
            visit.attested_profile_crc32 = transition.profile_crc32;
            visit.frequency_hz = transition.actual_frequency_hz;
            visit.feedback_outcome = outcome;
            visit.energy_sum = energy;
            visit.energy_sample_count = energy_times;
            visit.power_dbfs = dbfs;
            visit.windows_emitted = emitted;
            visit.fractional_epoch_server_parity_qualified =
                state.capabilities.fractional_epoch_server_parity_qualified;
            {
                std::lock_guard<std::mutex> lock(state.output);
                ++state.stats.visits_started;
                state.stats.windows_emitted += emitted;
                if (intact) ++state.stats.visits_intact;
                else ++state.stats.visits_incomplete;
                if (outcome == LEO_SCANNER_ACTIVE) ++state.stats.feedback_active;
                else if (outcome == LEO_SCANNER_QUIET) ++state.stats.feedback_quiet;
                else ++state.stats.feedback_unknown;
                state.emit_unlocked(visit, visit_authority);
            }

            if (intact) {
                spf_scan_feedback feedback{};
                feedback.session = config->session;
                feedback.generation = config->generation;
                feedback.sequence = choice.visit + 1U;
                feedback.visit = choice.visit;
                feedback.valid_start = valid_start;
                feedback.valid_end = valid_end;
                feedback.target = choice.target;
                feedback.outcome = outcome;
                std::memcpy(feedback.analysis_digest, energy_digest, sizeof(energy_digest));
                const enum spf_scan_feedback_result disposition =
                    spf_scan_policy_feedback(policy, &feedback, now);
                if (disposition != SPF_SCAN_ACCEPTED) {
                    std::lock_guard<std::mutex> lock(state.output);
                    ++state.stats.feedback_rejected;
                }

                Slot* slot = reserve_slot(state);
                if (!slot) {
                    leo_scanner_event dropped = visit;
                    dropped.kind = LEO_SCANNER_QUEUE_DROP;
                    std::lock_guard<std::mutex> lock(state.output);
                    ++state.stats.detector_queue_drops;
                    state.emit_unlocked(dropped, visit_authority);
                } else {
                    slot->visit = choice.visit;
                    slot->valid_start = valid_start;
                    slot->valid_end = valid_end;
                    slot->selection_counter = choice.selection_counter;
                    slot->transition_before = transition.previous_valid_end;
                    slot->transition_after = transition.valid_start;
                    slot->recalled = recalled ? 1U : 0U;
                    slot->target = choice.target;
                    slot->profile = transition.selected_target_key;
                    slot->profile_crc32 = transition.profile_crc32;
                    slot->frequency_hz = transition.actual_frequency_hz;
                    slot->authority = visit_authority;
                    slot->dwell_ms = choice.dwell_ms;
                    slot->iq = dwell;
                    slot->detector_started_monotonic_ns = 0;
                    slot->detector_finished_monotonic_ns = 0;
                    slot->detector_row_count = 0;
                    (void)monotonic_ns(slot->detector_enqueued_monotonic_ns);
                    if (!executor.submit(Job{choice.visit, detector_job, slot})) {
                        slot->occupied.store(false, std::memory_order_release);
                        leo_scanner_event dropped = visit;
                        dropped.kind = LEO_SCANNER_QUEUE_DROP;
                        std::lock_guard<std::mutex> lock(state.output);
                        ++state.stats.detector_queue_drops;
                        state.emit_unlocked(dropped, visit_authority);
                    } else {
                        std::lock_guard<std::mutex> lock(state.output);
                        ++state.stats.detector_accepted;
                    }
                }
            }
            if (capture_status) {
                ret = capture_status;
                state.stats.stop_reason = LEO_SCANNER_STOP_SOURCE_ERROR;
                state.stats.stop_status = ret;
                break;
            }
        }
        if (state.stats.stop_reason == LEO_SCANNER_STOP_NONE) {
            if (iteration >= config->maximum_visits)
                state.stats.stop_reason = LEO_SCANNER_STOP_MAXIMUM_VISITS;
            else
                state.stats.stop_reason = LEO_SCANNER_STOP_SOURCE_DURATION;
        }
        spf_scan_policy_stop(policy, now);
        drain_acks(policy, state);
        executor.drain();
        try {
            executor.rethrow_first_failure();
        } catch (...) {
            state.stats.stop_reason = LEO_SCANNER_STOP_DETECTOR_ERROR;
            state.stats.stop_status = -EIO;
            state.stats.detector_queue_high_water = executor.stats().high_water;
            *output = state.stats;
            if (wall_guard.finish()) {
                output->stop_reason = LEO_SCANNER_STOP_WALL_DEADLINE;
                output->stop_status = -ETIMEDOUT;
                return -ETIMEDOUT;
            }
            return -EIO;
        }
        const leo::adaptive::ExecutorStats executor_stats = executor.stats();
        state.stats.detector_queue_high_water = executor_stats.high_water;
        *output = state.stats;
        if (wall_guard.finish()) {
            output->stop_reason = LEO_SCANNER_STOP_WALL_DEADLINE;
            output->stop_status = -ETIMEDOUT;
            return -ETIMEDOUT;
        }
        return ret < 0 ? ret : 0;
    } catch (const std::bad_alloc&) {
        if (output) {
            output->stop_reason = LEO_SCANNER_STOP_INTERNAL_ERROR;
            output->stop_status = -ENOMEM;
        }
        return -ENOMEM;
    } catch (...) {
        if (output) {
            output->stop_reason = LEO_SCANNER_STOP_INTERNAL_ERROR;
            output->stop_status = -EIO;
        }
        return -EIO;
    }
}

namespace {
leo_scanner_source_requirements strict_local_requirements() {
    leo_scanner_source_requirements value{};
    value.abi_version = LEO_SCANNER_SOURCE_ABI_VERSION;
    value.counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    value.position_semantics = LEO_SOURCE_POSITION_COHERENT_CURRENT;
    value.required_capability_flags = LEO_SOURCE_CAP_CANCEL |
        LEO_SOURCE_CAP_SELECT | LEO_SOURCE_CAP_SIMULTANEOUS_RX |
        LEO_SOURCE_CAP_COHERENT_RX | LEO_SOURCE_CAP_FREQUENCY_ATTESTATION |
        LEO_SOURCE_CAP_TARGET_ATTESTATION |
        LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION | LEO_SOURCE_CAP_EXACT_GAP |
        LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    value.required_transition_flags = LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
        LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
        LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED |
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    value.maximum_frequency_error_hz = 2U;
    value.require_physical_counter_qualified = 1U;
    return value;
}

int scanner_run_local(const leo_scanner_config* config, leo_local_source* source,
    const leo_scanner_counter_ops* counter,
    const DetectorExecution& execution, leo_scanner_event_sink sink,
    void* sink_context, leo_scanner_stats* output) {
    if (output) std::memset(output, 0, sizeof(*output));
    if (!source || (counter && !counter->snapshot)) {
        return -EINVAL;
    }
    leo_local_config local{};
    int status = leo_local_source_describe(source, &local);
    if (status) return status;
    leo_local_source_port* adapter = nullptr;
    status = leo_local_source_port_create(source, &local, &adapter);
    if (status) return status;
    const auto requirements = strict_local_requirements();
    int result = scanner_run_impl(config, leo_local_source_port_get(adapter), counter,
        &requirements, execution, sink, nullptr, sink_context, output, nullptr);
    const int cleanup = leo_source_port_cleanup(leo_local_source_port_get(adapter));
    const int disposal = cleanup ? leo_local_source_port_abandon_lease(adapter) :
        leo_local_source_port_destroy(adapter);
    const int cleanup_status = cleanup ? cleanup : disposal;
    if (cleanup_status && !result) {
        result = cleanup_status;
        if (output) {
            output->stop_reason = LEO_SCANNER_STOP_SOURCE_ERROR;
            output->stop_status = cleanup_status;
        }
    }
    return result;
}
} // namespace

extern "C" int leo_scanner_run(const leo_scanner_config* config,
    leo_local_source* source, const leo_scanner_detector_ops* detector,
    leo_scanner_event_sink sink, void* sink_context, leo_scanner_stats* output) {
    leo_scanner_detector_binding binding{};
    if (detector) binding.ops = *detector;
    const DetectorExecution execution{&binding, 1U, {}, false};
    return scanner_run_local(config, source, nullptr, execution, sink,
        sink_context, output);
}

extern "C" int leo_scanner_run_timed(const leo_scanner_config* config,
    leo_local_source* source, const leo_scanner_counter_ops* counter,
    const leo_scanner_detector_ops* detector, leo_scanner_event_sink sink,
    void* sink_context, leo_scanner_stats* output) {
    if (!counter) {
        if (output) std::memset(output, 0, sizeof(*output));
        return -EINVAL;
    }
    leo_scanner_detector_binding binding{};
    if (detector) binding.ops = *detector;
    const DetectorExecution execution{&binding, 1U, {}, false};
    return scanner_run_local(config, source, counter, execution, sink,
        sink_context, output);
}

extern "C" int leo_scanner_run_source(const leo_scanner_config* config,
    leo_source_port* source, const leo_scanner_source_requirements* requirements,
    const leo_scanner_detector_ops* detector, leo_scanner_source_event_sink sink,
    void* sink_context, leo_scanner_source_stats* output) {
    if (output) std::memset(output, 0, sizeof(*output));
    if (!output || !requirements) return -EINVAL;
    leo_scanner_stats scanner{};
    leo_scanner_detector_binding binding{};
    if (detector) binding.ops = *detector;
    const DetectorExecution execution{&binding, 1U, {}, false};
    const int status = scanner_run_impl(config, source, nullptr, requirements,
        execution, nullptr, sink, sink_context, &scanner, output);
    output->abi_version = LEO_SCANNER_SOURCE_ABI_VERSION;
    output->scanner = scanner;
    return status;
}

extern "C" int leo_scanner_run_ex(const leo_scanner_config* config,
    leo_local_source* source, const leo_scanner_execution_options* options,
    leo_scanner_event_sink sink, void* sink_context, leo_scanner_stats* output) {
    if (output) std::memset(output, 0, sizeof(*output));
    if (!output || !source) return -EINVAL;
    DetectorExecution execution{};
    const int status = validate_execution(config, true, options, execution);
    if (status) {
        if (output && status == -ENOTSUP) {
            output->stop_reason = LEO_SCANNER_STOP_DETECTOR_ERROR;
            output->stop_status = status;
        }
        return status;
    }
    return scanner_run_local(config, source, nullptr, execution, sink,
        sink_context, output);
}

extern "C" int leo_scanner_run_timed_ex(const leo_scanner_config* config,
    leo_local_source* source, const leo_scanner_counter_ops* counter,
    const leo_scanner_execution_options* options, leo_scanner_event_sink sink,
    void* sink_context, leo_scanner_stats* output) {
    if (output) std::memset(output, 0, sizeof(*output));
    if (!output || !source || !counter || !counter->snapshot) return -EINVAL;
    DetectorExecution execution{};
    const int status = validate_execution(config, true, options, execution);
    if (status) {
        if (output && status == -ENOTSUP) {
            output->stop_reason = LEO_SCANNER_STOP_DETECTOR_ERROR;
            output->stop_status = status;
        }
        return status;
    }
    return scanner_run_local(config, source, counter, execution, sink,
        sink_context, output);
}

extern "C" int leo_scanner_run_source_ex(const leo_scanner_config* config,
    leo_source_port* source, const leo_scanner_source_requirements* requirements,
    const leo_scanner_execution_options* options,
    leo_scanner_source_event_sink sink, void* sink_context,
    leo_scanner_source_stats* output) {
    if (output) std::memset(output, 0, sizeof(*output));
    if (!output || !source || !valid_requirement_shape(requirements)) return -EINVAL;
    const bool require_crc = requirements->required_transition_flags &
        LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED;
    DetectorExecution execution{};
    const int preflight = validate_execution(config, require_crc, options, execution);
    if (preflight) {
        output->abi_version = LEO_SCANNER_SOURCE_ABI_VERSION;
        if (preflight == -ENOTSUP) {
            output->scanner.stop_reason = LEO_SCANNER_STOP_DETECTOR_ERROR;
            output->scanner.stop_status = preflight;
        }
        return preflight;
    }
    leo_scanner_stats scanner{};
    const int status = scanner_run_impl(config, source, nullptr, requirements,
        execution, nullptr, sink, sink_context, &scanner, output);
    output->abi_version = LEO_SCANNER_SOURCE_ABI_VERSION;
    output->scanner = scanner;
    return status;
}
