#include "scanner_single_source.h"

#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <time.h>
#include <vector>

namespace {
constexpr uint32_t rate = 2500000U;
constexpr size_t dwell_times = 300000U;
constexpr size_t block_times = 50000U;

template <typename T> std::vector<T> read_file(const char* path) {
    FILE* file = std::fopen(path, "rb");
    assert(file);
    assert(std::fseek(file, 0, SEEK_END) == 0);
    const long bytes = std::ftell(file);
    assert(bytes > 0 && bytes % sizeof(T) == 0);
    assert(std::fseek(file, 0, SEEK_SET) == 0);
    std::vector<T> value(static_cast<size_t>(bytes) / sizeof(T));
    assert(std::fread(value.data(), sizeof(T), value.size(), file) == value.size());
    assert(std::fclose(file) == 0);
    return value;
}

struct Source {
    std::vector<int16_t> iq;
    size_t offset = 0;
    uint64_t token = 0;
};

int source_capabilities(void*, leo_source_capabilities* out) {
    *out = {};
    out->abi_version = LEO_SOURCE_PORT_ABI_VERSION;
    out->sample_format = LEO_SOURCE_SAMPLE_FORMAT_CI16;
    out->flags = LEO_SOURCE_CAP_CANCEL | LEO_SOURCE_CAP_SELECT |
        LEO_SOURCE_CAP_FREQUENCY_ATTESTATION |
        LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    out->sample_rate_hz = rate;
    out->receiver_count = 1U;
    out->maximum_samples_per_block = block_times;
    out->counter_authority = LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    out->position_semantics = LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    return 0;
}

int source_position(void* context, leo_source_position* out) {
    const auto& source = *static_cast<Source*>(context);
    *out = {};
    out->coordinate = source.offset / 2U;
    out->counter_authority = LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    out->semantics = LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    return 0;
}

int source_select(void* context, const leo_source_selection* selection,
                  leo_source_transition* out) {
    const auto& source = *static_cast<Source*>(context);
    const uint64_t position = source.offset / 2U;
    *out = {};
    out->flags = LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    out->actual_frequency_hz = selection->requested_frequency_hz;
    out->previous_valid_end = position;
    out->valid_start = position;
    out->counter_authority = LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    out->position_semantics = LEO_SOURCE_POSITION_DELIVERED_WATERMARK;
    return 0;
}

int source_next(void* context, leo_source_block* out) {
    auto& source = *static_cast<Source*>(context);
    if (source.offset + block_times * 2U > source.iq.size()) return -ENODATA;
    *out = {};
    out->ci16 = source.iq.data() + source.offset;
    out->iq_bytes = block_times * 2U * sizeof(int16_t);
    out->samples_per_receiver = block_times;
    out->receiver_count = 1U;
    out->counter_authority = LEO_SOURCE_COUNTER_SOFTWARE_DELIVERED;
    out->first_coordinate = source.offset / 2U;
    out->end_coordinate = out->first_coordinate + block_times;
    out->stream_ordinal = out->first_coordinate;
    out->buffer_sequence = out->end_coordinate / block_times;
    out->lease_token = ++source.token;
    source.offset += block_times * 2U;
    return 0;
}

int source_release(void*, leo_source_block*) { return 0; }
int source_cancel(void*) { return 0; }
const leo_source_ops source_ops{source_capabilities, source_position,
    source_select, source_next, source_release, source_cancel};

int detector_analyze(void* context, const int16_t* iq, size_t times,
                     uint32_t dwell_ms, uint32_t stride_ms,
                     leo_native_glrt_result* result) {
    return leo_single_rx_glrt_analyze(
        static_cast<leo_single_rx_glrt*>(context), iq, times, dwell_ms,
        stride_ms, result);
}

int detector_capabilities(void*, leo_single_rx_glrt_capabilities* out) {
    return leo_single_rx_glrt_get_capabilities(out);
}

leo_scanner_config config() {
    leo_scanner_config value{};
    value.abi_version = LEO_SCANNER_ABI_VERSION;
    value.session = 401U;
    value.generation = 402U;
    value.seed = 403U;
    value.sample_rate_hz = rate;
    value.receiver_count = 1U;
    value.duration_ms = 500U;
    value.maximum_visits = 1U;
    timespec now{};
    assert(clock_gettime(CLOCK_MONOTONIC, &now) == 0);
    value.wall_deadline_monotonic_ns =
        static_cast<uint64_t>(now.tv_sec) * 1000000000U +
        static_cast<uint64_t>(now.tv_nsec) + 10000000000U;
    value.dwell_ms = 120U;
    value.transition_budget_ms = 20U;
    value.maximum_revisit_ms = 3000U;
    value.feedback_age_ms = 1000U;
    value.application_delay_ms = 1000U;
    value.decay_ms = 3000U;
    value.maximum_boost = 3U;
    value.detector_queue_capacity = 1U;
    value.active_threshold_dbfs = -38.0;
    value.target_count = 1U;
    value.targets[0] = {0U, UINT64_C(1090000000), 0U, 1U};
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

struct Events {
    std::vector<leo_scanner_source_event> candidates;
    uint32_t results = 0;
};

void collect(void* context, const leo_scanner_source_event* event) {
    auto& events = *static_cast<Events*>(context);
    if (event->event.kind == LEO_SCANNER_DETECTOR_RESULT) ++events.results;
    if (event->event.kind == LEO_SCANNER_CANDIDATE)
        events.candidates.push_back(*event);
}

bool same_candidate(const leo_native_glrt_candidate& a,
                    const leo_native_glrt_candidate& b) {
#define SAME(name) \
    if (std::memcmp(&a.name, &b.name, sizeof(a.name))) return false
    SAME(coarse_epoch); SAME(coarse_bin); SAME(refined_epoch);
    SAME(frame_support); SAME(glrt_complete); SAME(conditioned_fallback);
    SAME(refinement_skipped); SAME(coarse_cfo_hz); SAME(fine_cfo_hz);
    SAME(conditioned_cfo_hz); SAME(epoch); SAME(acquired_cfo_hz);
    SAME(tracking_cfo_hz); SAME(exact_score); SAME(control_score); SAME(margin);
    SAME(acquire_score); SAME(verify_score); SAME(verify_control_score);
    SAME(conditioned_score); SAME(coarse_score); SAME(fractional_epoch_status);
    SAME(fractional_epoch_offset_samples); SAME(fractional_epoch_log_curvature);
    SAME(fractional_epoch_exact_grid); SAME(fractional_epoch_control_grid);
    SAME(fractional_exact_score); SAME(fractional_control_score);
    SAME(fractional_margin); SAME(fractional_residual_cfo_hz);
    SAME(fractional_tracking_cfo_hz);
#undef SAME
    return true;
}

void run_receiver(const std::vector<leo_native_glrt_complex>& exact,
                  const std::vector<leo_native_glrt_complex>& control,
                  const std::vector<int16_t>& single) {
    leo_single_rx_glrt* direct_context = nullptr;
    leo_single_rx_glrt* scanner_context = nullptr;
    assert(leo_single_rx_glrt_create_with_mode(&direct_context, rate,
        exact.data(), control.data(), exact.size(),
        LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH) == 0);
    assert(leo_single_rx_glrt_create_with_mode(&scanner_context, rate,
        exact.data(), control.data(), exact.size(),
        LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH) == 0);
    leo_native_glrt_result expected{};
    assert(leo_single_rx_glrt_analyze(direct_context, single.data(),
        dwell_times, 120U, 120U, &expected) == 0);
    assert(expected.row_count == 1U && expected.rows[0].candidate_count > 0);

    Source source;
    source.iq.resize(block_times * 2U, 0);
    source.iq.insert(source.iq.end(), single.begin(), single.end());
    leo_source_port port{};
    assert(leo_source_port_init(&port, &source, &source_ops) == 0);
    leo_scanner_single_detector_binding binding{};
    binding.abi_version = LEO_SCANNER_SINGLE_SOURCE_ABI_VERSION;
    binding.ops = {scanner_context, detector_analyze, detector_capabilities};
    std::memset(binding.configuration_digest, 0xa7,
        sizeof(binding.configuration_digest));
    const leo_scanner_single_execution_options execution{
        LEO_SCANNER_SINGLE_SOURCE_ABI_VERSION, 1U, &binding};
    auto scan = config();
    auto needed = requirements();
    Events events;
    leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source_single_ex(&scan, &port, &needed, &execution,
        collect, &events, &stats) == 0);
    assert(stats.scanner.visits_intact == 1U &&
        stats.scanner.detector_completed == 1U && events.results == 1U);
    assert(events.candidates.size() ==
        static_cast<size_t>(expected.rows[0].candidate_count));
    for (size_t index = 0; index < events.candidates.size(); ++index) {
        const auto& event = events.candidates[index];
        assert(event.event.receiver_id == 0 && event.event.row_index == 0U &&
            event.event.candidate_index == index &&
            event.event.attested_profile_crc32 == 0U &&
            !event.physical_counter_qualified &&
            same_candidate(event.event.candidate,
                expected.rows[0].candidates[index]));
    }
    assert(leo_single_rx_glrt_destroy(scanner_context) == 0);
    assert(leo_single_rx_glrt_destroy(direct_context) == 0);
}
} // namespace

int main(int argc, char** argv) {
    assert(argc == 4);
    const auto exact = read_file<leo_native_glrt_complex>(argv[1]);
    const auto control = read_file<leo_native_glrt_complex>(argv[2]);
    const auto dual = read_file<int16_t>(argv[3]);
    assert(exact.size() == control.size() && dual.size() == dwell_times * 4U);
    std::vector<int16_t> single[2];
    single[0].resize(dwell_times * 2U);
    single[1].resize(dwell_times * 2U);
    for (size_t sample = 0; sample < dwell_times; ++sample)
        for (size_t receiver = 0; receiver < 2U; ++receiver) {
            single[receiver][2U * sample] = dual[4U * sample + 2U * receiver];
            single[receiver][2U * sample + 1U] =
                dual[4U * sample + 2U * receiver + 1U];
        }
    run_receiver(exact, control, single[0]);
    run_receiver(exact, control, single[1]);
    return 0;
}
