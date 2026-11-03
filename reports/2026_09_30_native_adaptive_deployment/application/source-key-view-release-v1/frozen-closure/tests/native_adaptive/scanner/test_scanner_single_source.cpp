#include "scanner_single_source.h"

#include <atomic>
#include <cassert>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <thread>
#include <time.h>
#include <vector>

namespace {
constexpr uint32_t rate = 2500000U;
constexpr uint32_t block_times = 50000U;

struct Source {
    std::vector<int16_t> block;
    uint64_t coordinate = 0;
    uint64_t token = 0;
    uint32_t selects = 0;
    uint32_t nexts = 0;
    uint32_t releases = 0;
    uint32_t cancels = 0;
    uint32_t discontinuity_block = UINT32_MAX;
    bool extra_attestations = false;
};

int source_capabilities(void* context, leo_source_capabilities* out) {
    const auto& source = *static_cast<Source*>(context);
    *out = {};
    out->abi_version = LEO_SOURCE_PORT_ABI_VERSION;
    out->sample_format = LEO_SOURCE_SAMPLE_FORMAT_CI16;
    out->flags = LEO_SOURCE_CAP_CANCEL | LEO_SOURCE_CAP_SELECT |
        LEO_SOURCE_CAP_FREQUENCY_ATTESTATION |
        LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    if (source.extra_attestations)
        out->flags |= LEO_SOURCE_CAP_TARGET_ATTESTATION |
            LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION;
    out->sample_rate_hz = rate;
    out->receiver_count = 1U;
    out->maximum_samples_per_block = block_times;
    out->counter_authority = LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    out->position_semantics = LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    out->time_authority = LEO_SOURCE_TIME_NONE;
    return 0;
}

int source_position(void* context, leo_source_position* out) {
    const auto& source = *static_cast<Source*>(context);
    *out = {};
    out->coordinate = source.coordinate;
    out->counter_authority = LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    out->semantics = LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    return 0;
}

int source_select(void* context, const leo_source_selection* selection,
                  leo_source_transition* out) {
    auto& source = *static_cast<Source*>(context);
    ++source.selects;
    *out = {};
    out->flags = LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    if (source.extra_attestations) {
        out->flags |= LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
            LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED;
        out->selected_target_key = selection->target_key;
        out->profile_crc32 = 0x12345678U;
    }
    out->actual_frequency_hz = selection->requested_frequency_hz;
    out->previous_valid_end = source.coordinate;
    out->valid_start = source.coordinate;
    out->counter_authority = LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    out->position_semantics = LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    return 0;
}

int source_next(void* context, leo_source_block* out) {
    auto& source = *static_cast<Source*>(context);
    *out = {};
    out->ci16 = source.block.data();
    out->iq_bytes = source.block.size() * sizeof(int16_t);
    out->samples_per_receiver = block_times;
    out->receiver_count = 1U;
    out->counter_authority = LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    out->time_authority = LEO_SOURCE_TIME_NONE;
    out->first_coordinate = source.coordinate;
    out->end_coordinate = source.coordinate + block_times;
    out->stream_ordinal = source.coordinate;
    out->buffer_sequence = ++source.nexts;
    out->lease_token = ++source.token;
    if (source.nexts - 1U == source.discontinuity_block)
        out->flags = LEO_SOURCE_BLOCK_DISCONTINUITY |
            LEO_SOURCE_BLOCK_OVERFLOW_BEFORE;
    source.coordinate = out->end_coordinate;
    return 0;
}

int source_release(void* context, leo_source_block*) {
    ++static_cast<Source*>(context)->releases;
    return 0;
}

int source_cancel(void* context) {
    ++static_cast<Source*>(context)->cancels;
    return 0;
}

const leo_source_ops source_ops{source_capabilities, source_position,
    source_select, source_next, source_release, source_cancel};

struct Detector {
    std::atomic<uint32_t> calls{0};
    std::vector<uint32_t> dwells;
    uint32_t delay_ms = 0;
    bool bad_peer = false;
    uint32_t malformation = 0;
};

int detector_capabilities(void* context,
                          leo_single_rx_glrt_capabilities* out) {
    const auto& detector = *static_cast<Detector*>(context);
    *out = {};
    out->abi_version = LEO_SINGLE_RX_GLRT_ABI_VERSION;
    out->receiver_count = 1U;
    out->input_scalar_stride = 2U;
    out->probe_ms = 20U;
    out->maximum_candidates_per_row = LEO_NATIVE_GLRT_MAX_CANDIDATES;
    out->native_per_receiver_semantics = 1U;
    out->peer_recovery_available = detector.bad_peer ? 1U : 0U;
    out->fractional_epoch_mode_available = 1U;
    return 0;
}

int detector_analyze(void* context, const int16_t* iq, size_t times,
                     uint32_t dwell_ms, uint32_t stride_ms,
                     leo_native_glrt_result* out) {
    auto& detector = *static_cast<Detector*>(context);
    assert(iq && times == static_cast<size_t>(rate) * dwell_ms / 1000U);
    assert(stride_ms == 120U);
    ++detector.calls;
    detector.dwells.push_back(dwell_ms);
    if (detector.delay_ms)
        std::this_thread::sleep_for(
            std::chrono::milliseconds(detector.delay_ms));
    *out = {};
    out->row_count = dwell_ms / 120U;
    if (detector.malformation == 4U) ++out->row_count;
    for (size_t row = 0; row < out->row_count; ++row) {
        out->rows[row].receiver_id = detector.malformation == 1U ? 1 : 0;
        out->rows[row].probe_index = static_cast<int32_t>(row) +
            (detector.malformation == 2U ? 1 : 0);
        out->rows[row].probe_start_ms = static_cast<int32_t>(120U * row);
        out->rows[row].candidate_count = detector.malformation == 3U ?
            LEO_NATIVE_GLRT_MAX_CANDIDATES + 1 : 1;
        out->rows[row].candidates[0].epoch = 17;
        out->rows[row].candidates[0].exact_score = 3.5;
    }
    return 0;
}

leo_scanner_single_detector_binding binding(Detector& detector,
                                            uint8_t digest = 0x5a) {
    leo_scanner_single_detector_binding value{};
    value.abi_version = LEO_SCANNER_SINGLE_SOURCE_ABI_VERSION;
    value.ops = {&detector, detector_analyze, detector_capabilities};
    std::memset(value.configuration_digest, digest,
        sizeof(value.configuration_digest));
    return value;
}

leo_scanner_source_requirements requirements() {
    leo_scanner_source_requirements value{};
    value.abi_version = LEO_SCANNER_SOURCE_ABI_VERSION;
    value.counter_authority = LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    value.position_semantics = LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    value.required_capability_flags = LEO_SOURCE_CAP_CANCEL |
        LEO_SOURCE_CAP_SELECT | LEO_SOURCE_CAP_FREQUENCY_ATTESTATION |
        LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    value.required_transition_flags =
        LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    value.maximum_frequency_error_hz = 1000U;
    return value;
}

leo_scanner_config config(uint32_t visits, uint32_t active_dwell = 240U) {
    leo_scanner_config value{};
    value.abi_version = LEO_SCANNER_ABI_VERSION;
    value.session = 101U;
    value.generation = 102U;
    value.seed = 103U;
    value.sample_rate_hz = rate;
    value.receiver_count = 1U;
    value.duration_ms = 1500U;
    value.maximum_visits = visits;
    timespec now{};
    assert(clock_gettime(CLOCK_MONOTONIC, &now) == 0);
    value.wall_deadline_monotonic_ns =
        static_cast<uint64_t>(now.tv_sec) * 1000000000U +
        static_cast<uint64_t>(now.tv_nsec) + 10000000000U;
    value.dwell_ms = active_dwell;
    value.transition_budget_ms = 20U;
    value.maximum_revisit_ms = 3000U;
    value.feedback_age_ms = 1000U;
    value.application_delay_ms = 1000U;
    value.decay_ms = 3000U;
    value.maximum_boost = 3U;
    value.detector_queue_capacity = 4U;
    value.active_threshold_dbfs = -38.0;
    value.target_count = 1U;
    value.targets[0] = {0U, UINT64_C(1090000000), 0U, 1U};
    return value;
}

struct Events {
    std::vector<leo_scanner_source_event> values;
};

void collect(void* context, const leo_scanner_source_event* event) {
    static_cast<Events*>(context)->values.push_back(*event);
}

void initialize(Source& source, int16_t amplitude) {
    source.block.resize(static_cast<size_t>(block_times) * 2U);
    for (size_t i = 0; i < source.block.size(); i += 2U) {
        source.block[i] = amplitude;
        source.block[i + 1U] = amplitude;
    }
}

void test_active_feedback_and_single_authority(uint32_t active_dwell) {
    Source source;
    initialize(source, 32767);
    source.extra_attestations = true;
    leo_source_port port{};
    assert(leo_source_port_init(&port, &source, &source_ops) == 0);
    Detector detector;
    auto detector_binding = binding(detector);
    const leo_scanner_single_execution_options execution{
        LEO_SCANNER_SINGLE_SOURCE_ABI_VERSION, 1U, &detector_binding};
    auto scan = config(2U, active_dwell);
    auto needed = requirements();
    Events events;
    leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source_single_ex(&scan, &port, &needed, &execution,
        collect, &events, &stats) == 0);
    assert(stats.scanner.visits_intact == 2U &&
        stats.scanner.feedback_active == 2U &&
        stats.scanner.detector_completed == 2U && !stats.physical_counter_qualified);
    assert(stats.counter_authority == LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED &&
        stats.position_semantics == LEO_SOURCE_POSITION_DELIVERED_WATERMARK &&
        stats.time_authority == LEO_SOURCE_TIME_NONE);
    assert(detector.dwells.size() == 2U && detector.dwells[0] == 120U &&
        detector.dwells[1] == active_dwell);
    assert(source.selects == 1U && source.nexts == source.releases &&
        port.outstanding_lease == 0U);
    uint32_t visits = 0;
    uint32_t candidates = 0;
    for (const auto& envelope : events.values) {
        assert(envelope.abi_version == LEO_SCANNER_SOURCE_ABI_VERSION);
        assert(envelope.counter_authority ==
            LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED);
        assert(envelope.position_semantics ==
            LEO_SOURCE_POSITION_DELIVERED_WATERMARK);
        assert(!envelope.physical_counter_qualified);
        assert(envelope.event.profile == 0U &&
            envelope.event.attested_profile_crc32 == 0U);
        assert(!(envelope.transition_flags &
            (LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
             LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED)));
        if (envelope.event.kind == LEO_SCANNER_VISIT) {
            ++visits;
            const uint64_t duration = envelope.event.valid_end -
                envelope.event.valid_start;
            const uint64_t expected = visits == 1U ? 300000U :
                static_cast<uint64_t>(rate) * active_dwell / 1000U;
            assert(duration == expected);
            assert(envelope.event.feedback_outcome == LEO_SCANNER_ACTIVE);
            assert(envelope.event.windows_emitted ==
                (visits == 1U ? 1U : active_dwell / 120U));
            assert(envelope.event.energy_sample_count == duration);
            assert(envelope.transition_flags ==
                (LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
                 LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY));
        }
        if (envelope.event.kind == LEO_SCANNER_CANDIDATE) {
            ++candidates;
            assert(envelope.event.receiver_id == 0 &&
                envelope.event.candidate.exact_score == 3.5);
        }
    }
    assert(visits == 2U && candidates == 1U + active_dwell / 120U);
    assert(leo_source_port_cleanup(&port) == 0);
}

void test_unknown_discontinuity_suppresses_analysis() {
    Source source;
    initialize(source, 32767);
    source.discontinuity_block = 1U;
    leo_source_port port{};
    assert(leo_source_port_init(&port, &source, &source_ops) == 0);
    Detector detector;
    auto detector_binding = binding(detector);
    const leo_scanner_single_execution_options execution{
        LEO_SCANNER_SINGLE_SOURCE_ABI_VERSION, 1U, &detector_binding};
    auto scan = config(1U);
    auto needed = requirements();
    Events events;
    leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source_single_ex(&scan, &port, &needed, &execution,
        collect, &events, &stats) == 0);
    assert(stats.scanner.visits_incomplete == 1U &&
        stats.scanner.feedback_unknown == 1U && !stats.scanner.detector_accepted &&
        !detector.calls && stats.overflow_blocks == 1U &&
        stats.discontinuity_blocks == 1U &&
        stats.unknown_discontinuities == 1U && !stats.exact_missing_samples);
    assert(source.nexts == source.releases && !port.outstanding_lease);
}

void test_discontinuity_before_valid_start_is_discarded() {
    Source source;
    initialize(source, 32767);
    source.discontinuity_block = 0U;
    leo_source_port port{};
    assert(leo_source_port_init(&port, &source, &source_ops) == 0);
    Detector detector;
    auto detector_binding = binding(detector);
    const leo_scanner_single_execution_options execution{
        LEO_SCANNER_SINGLE_SOURCE_ABI_VERSION, 1U, &detector_binding};
    auto scan = config(1U);
    auto needed = requirements();
    Events events;
    leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source_single_ex(&scan, &port, &needed, &execution,
        collect, &events, &stats) == 0);
    assert(stats.scanner.visits_intact == 1U &&
        stats.scanner.feedback_active == 1U &&
        stats.scanner.detector_completed == 1U && detector.calls == 1U);
    assert(!stats.overflow_blocks && !stats.discontinuity_blocks &&
        !stats.unknown_discontinuities);
    for (const auto& event : events.values)
        assert(!(event.block_flags & (LEO_SOURCE_BLOCK_DISCONTINUITY |
            LEO_SOURCE_BLOCK_OVERFLOW_BEFORE)));
    assert(source.nexts == source.releases && !port.outstanding_lease);
}

void test_preflight_rejects_false_authority_and_peer() {
    Source source;
    initialize(source, 0);
    leo_source_port port{};
    assert(leo_source_port_init(&port, &source, &source_ops) == 0);
    Detector detector;
    auto detector_binding = binding(detector);
    const leo_scanner_single_execution_options execution{
        LEO_SCANNER_SINGLE_SOURCE_ABI_VERSION, 1U, &detector_binding};
    auto scan = config(1U);
    auto needed = requirements();
    leo_scanner_source_stats stats{};

    needed.require_physical_counter_qualified = 1U;
    assert(leo_scanner_run_source_single_ex(&scan, &port, &needed, &execution,
        nullptr, nullptr, &stats) == -EINVAL);
    assert(!detector.calls && !source.selects && !source.nexts);

    needed = requirements();
    detector.bad_peer = true;
    assert(leo_scanner_run_source_single_ex(&scan, &port, &needed, &execution,
        nullptr, nullptr, &stats) == -ENOTSUP);
    assert(stats.scanner.stop_reason == LEO_SCANNER_STOP_DETECTOR_ERROR &&
        !source.selects && !source.nexts);
    detector.bad_peer = false;

    scan.targets[0].profile_crc32 = 1U;
    assert(leo_scanner_run_source_single_ex(&scan, &port, &needed, &execution,
        nullptr, nullptr, &stats) == -EINVAL);
    assert(!source.selects && !source.nexts);
}

void test_two_worker_routing_and_drain() {
    Source source;
    initialize(source, 0);
    leo_source_port port{};
    assert(leo_source_port_init(&port, &source, &source_ops) == 0);
    Detector detectors[2];
    detectors[0].delay_ms = 50U;
    detectors[1].delay_ms = 50U;
    leo_scanner_single_detector_binding bindings[2]{
        binding(detectors[0]), binding(detectors[1])};
    const leo_scanner_single_execution_options execution{
        LEO_SCANNER_SINGLE_SOURCE_ABI_VERSION, 2U, bindings};
    auto scan = config(4U, 120U);
    auto needed = requirements();
    leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source_single_ex(&scan, &port, &needed, &execution,
        nullptr, nullptr, &stats) == 0);
    assert(detectors[0].calls && detectors[1].calls);
    assert(detectors[0].calls + detectors[1].calls == 4U);
    assert(stats.scanner.detector_completed == 4U &&
        !stats.scanner.detector_queue_drops &&
        source.nexts == source.releases && !port.outstanding_lease);
}

void test_malformed_single_results_never_emit() {
    for (uint32_t malformation = 1U; malformation <= 4U; ++malformation) {
        Source source;
        initialize(source, 0);
        leo_source_port port{};
        assert(leo_source_port_init(&port, &source, &source_ops) == 0);
        Detector detector;
        detector.malformation = malformation;
        auto detector_binding = binding(detector);
        const leo_scanner_single_execution_options execution{
            LEO_SCANNER_SINGLE_SOURCE_ABI_VERSION, 1U, &detector_binding};
        auto scan = config(1U);
        auto needed = requirements();
        Events events;
        leo_scanner_source_stats stats{};
        assert(leo_scanner_run_source_single_ex(&scan, &port, &needed,
            &execution, collect, &events, &stats) == 0);
        assert(stats.scanner.detector_failures == 1U &&
            !stats.scanner.detector_completed &&
            !stats.scanner.detector_candidates);
        uint32_t failures = 0;
        for (const auto& event : events.values) {
            assert(event.event.kind != LEO_SCANNER_CANDIDATE);
            assert(event.event.kind != LEO_SCANNER_DETECTOR_RESULT);
            if (event.event.kind == LEO_SCANNER_DETECTOR_FAILURE) {
                ++failures;
                assert(event.event.detector_status == -EPROTO);
            }
        }
        assert(failures == 1U);
    }
}
} // namespace

int main() {
    test_active_feedback_and_single_authority(240U);
    test_active_feedback_and_single_authority(360U);
    test_unknown_discontinuity_suppresses_analysis();
    test_discontinuity_before_valid_start_is_discarded();
    test_preflight_rejects_false_authority_and_peer();
    test_two_worker_routing_and_drain();
    test_malformed_single_results_never_emit();
    return 0;
}
