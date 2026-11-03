#include "scanner_recorded_plan.h"

#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include <cstdint>
#include <chrono>
#include <thread>
#include <vector>

namespace {
constexpr std::uint32_t rate = 7500000U;
constexpr std::uint64_t dwell_samples = 900000U;
constexpr std::uint32_t transition_flags =
    LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
    LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
    LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;

std::uint64_t deadline() {
    timespec value{};
    assert(clock_gettime(CLOCK_MONOTONIC, &value) == 0);
    return static_cast<std::uint64_t>(value.tv_sec) * 1000000000ULL +
        static_cast<std::uint64_t>(value.tv_nsec) + 10000000000ULL;
}

struct Source {
    const leo_scanner_recorded_plan* plan{};
    std::vector<std::int16_t> iq;
    std::uint32_t selected{};
    std::uint32_t delivered{};
    std::uint32_t capabilities_calls{};
    bool leased{};
    bool transition_mismatch{};
    bool gap_inside{};
};

int capabilities(void* context, leo_source_capabilities* out) {
    ++static_cast<Source*>(context)->capabilities_calls;
    *out = {LEO_SOURCE_PORT_ABI_VERSION, LEO_SOURCE_SAMPLE_FORMAT_CI16,
        LEO_SOURCE_CAP_CANCEL | LEO_SOURCE_CAP_SELECT |
        LEO_SOURCE_CAP_SIMULTANEOUS_RX | LEO_SOURCE_CAP_COHERENT_RX |
        LEO_SOURCE_CAP_FREQUENCY_ATTESTATION | LEO_SOURCE_CAP_TARGET_ATTESTATION |
        LEO_SOURCE_CAP_EXACT_GAP | LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY,
        rate, 2U, static_cast<std::uint32_t>(dwell_samples),
        LEO_SOURCE_COUNTER_PROVIDER_EXACT,
        LEO_SOURCE_POSITION_COHERENT_CURRENT, LEO_SOURCE_TIME_NONE, 0U};
    return 0;
}

int position(void* context, leo_source_position* out) {
    auto& source = *static_cast<Source*>(context);
    const std::uint32_t ordinal = source.selected < source.plan->visit_count ?
        source.selected : source.plan->visit_count - 1U;
    *out = {source.plan->visits[ordinal].selection_counter,
        LEO_SOURCE_COUNTER_PROVIDER_EXACT,
        LEO_SOURCE_POSITION_COHERENT_CURRENT};
    return 0;
}

int select_source(void* context, const leo_source_selection* selection,
                  leo_source_transition* out) {
    auto& source = *static_cast<Source*>(context);
    if (source.selected >= source.plan->visit_count) return -ENODATA;
    const auto& row = source.plan->visits[source.selected++];
    assert(selection->target_key == row.target_key);
    assert(selection->requested_frequency_hz == row.requested_frequency_hz);
    *out = {};
    out->flags = row.expected_transition_flags;
    out->selected_target_key = row.target_key;
    out->profile_crc32 = row.expected_profile_crc32;
    out->counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    out->position_semantics = LEO_SOURCE_POSITION_COHERENT_CURRENT;
    out->time_authority = LEO_SOURCE_TIME_NONE;
    out->actual_frequency_hz = row.expected_actual_frequency_hz +
        (source.transition_mismatch ? 1U : 0U);
    out->previous_valid_end = row.transition_previous_valid_end;
    out->valid_start = row.transition_valid_start;
    return 0;
}

int next_source(void* context, leo_source_block* out) {
    auto& source = *static_cast<Source*>(context);
    if (!source.selected || source.delivered >= source.selected || source.leased)
        return -ENODATA;
    const auto& row = source.plan->visits[source.delivered];
    const std::uint64_t shift = source.gap_inside ? 1U : 0U;
    *out = {};
    out->ci16 = source.iq.data();
    out->iq_bytes = source.iq.size() * sizeof(source.iq[0]);
    out->samples_per_receiver = dwell_samples;
    out->receiver_count = 2U;
    out->counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    out->first_coordinate = row.valid_start + shift;
    out->end_coordinate = out->first_coordinate + dwell_samples;
    out->stream_ordinal = out->first_coordinate;
    out->lease_token = ++source.delivered;
    source.leased = true;
    return 0;
}

int release_source(void* context, leo_source_block*) {
    auto& source = *static_cast<Source*>(context);
    assert(source.leased);
    source.leased = false;
    return 0;
}
int cancel_source(void*) { return 0; }
const leo_source_ops source_ops{capabilities, position, select_source,
    next_source, release_source, cancel_source};

struct Profile {
    std::vector<std::uint64_t> derived_visits;
    std::vector<std::uint32_t> derived_targets;
    std::uint32_t analyzes{};
    std::uint32_t analyze_delay_ms{};
};

int derive(void* context, const leo_scanner_visit_authority* visit,
           leo_scanner_detector_geometry* out) {
    auto& profile = *static_cast<Profile*>(context);
    profile.derived_visits.push_back(visit->visit);
    profile.derived_targets.push_back(visit->target_key);
    *out = {};
    out->abi_version = LEO_SCANNER_PROFILE_ABI_VERSION;
    out->sample_rate_hz = rate;
    out->receiver_count = 2U;
    out->probe_ms = 20U;
    out->probe_stride_ms = 120U;
    out->receiver_center_hz[0] = -312500.0;
    out->receiver_center_hz[1] = 312500.0;
    out->residual_cfo_min_hz = -800000.0;
    out->residual_cfo_max_hz = 800000.0;
    out->profile_manifest_digest[0] = 2U;
    out->authority_digest[0] = 3U;
    return 0;
}

int profile_capabilities(void*, leo_scanner_profile_capabilities* out) {
    *out = {LEO_SCANNER_PROFILE_ABI_VERSION, rate, 2U, 20U, 120U,
        1U, 1U, 0U, 22U, 22U, 1600000U};
    return 0;
}

int analyze(void* context, const leo_scanner_detector_geometry*,
            const std::int16_t*, std::size_t complex_times,
            std::uint32_t dwell_ms, std::uint32_t stride_ms,
            leo_native_glrt_result* out) {
    auto& profile = *static_cast<Profile*>(context);
    assert(complex_times == dwell_samples && dwell_ms == 120U && stride_ms == 120U);
    if (profile.analyze_delay_ms)
        std::this_thread::sleep_for(
            std::chrono::milliseconds(profile.analyze_delay_ms));
    ++profile.analyzes;
    *out = {};
    out->row_count = 2U;
    out->rows[0].receiver_id = 0U;
    out->rows[1].receiver_id = 1U;
    return 0;
}

struct Events { std::vector<leo_scanner_source_event> visits; };
void sink(void* context, const leo_scanner_source_event* event) {
    if (event->event.kind == LEO_SCANNER_VISIT)
        static_cast<Events*>(context)->visits.push_back(*event);
}

leo_scanner_recorded_config config() {
    leo_scanner_recorded_config value{};
    value.abi_version = LEO_SCANNER_RECORDED_PLAN_ABI_VERSION;
    value.session = 10U;
    value.generation = 20U;
    value.sample_rate_hz = rate;
    value.receiver_count = 2U;
    value.wall_deadline_monotonic_ns = deadline();
    value.detector_queue_capacity = 2U;
    value.target_count = 2U;
    value.targets[0] = {2U, 10750000000ULL, 0U, 1U};
    value.targets[1] = {5U, 11900000000ULL, 0U, 1U};
    return value;
}

std::vector<leo_scanner_recorded_visit> visits() {
    return {
        {41U, 0U, 2U, 120U, 1U, transition_flags, 0U,
            10750000000ULL, 10750000000ULL, 100U, 100U, 150U,
            200U, 200U + dwell_samples},
        {97U, 1U, 5U, 120U, 1U, transition_flags, 0U,
            11900000000ULL, 11900000000ULL, 2000000U, 1100000U, 2000100U,
            2100000U, 2100000U + dwell_samples}
    };
}

leo_scanner_recorded_plan plan(std::vector<leo_scanner_recorded_visit>& rows) {
    leo_scanner_recorded_plan value{};
    value.abi_version = LEO_SCANNER_RECORDED_PLAN_ABI_VERSION;
    value.visit_count = static_cast<std::uint32_t>(rows.size());
    value.visits = rows.data();
    value.plan_digest[0] = 1U;
    return value;
}

leo_scanner_source_requirements requirements() {
    leo_scanner_source_requirements value{};
    value.abi_version = LEO_SCANNER_SOURCE_ABI_VERSION;
    value.counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    value.position_semantics = LEO_SOURCE_POSITION_COHERENT_CURRENT;
    value.required_capability_flags = LEO_SOURCE_CAP_CANCEL | LEO_SOURCE_CAP_SELECT |
        LEO_SOURCE_CAP_SIMULTANEOUS_RX | LEO_SOURCE_CAP_COHERENT_RX |
        LEO_SOURCE_CAP_FREQUENCY_ATTESTATION | LEO_SOURCE_CAP_TARGET_ATTESTATION |
        LEO_SOURCE_CAP_EXACT_GAP | LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY;
    value.required_transition_flags = transition_flags;
    value.maximum_frequency_error_hz = 2U;
    value.require_physical_counter_qualified = 1U;
    return value;
}

leo_scanner_profile_execution_options execution(Profile& profile,
        leo_scanner_profile_detector_binding& binding) {
    binding = {};
    binding.abi_version = LEO_SCANNER_PROFILE_ABI_VERSION;
    binding.ops = {&profile, analyze, profile_capabilities};
    binding.configuration_digest[0] = 1U;
    leo_scanner_profile_execution_options value{};
    value.abi_version = LEO_SCANNER_PROFILE_ABI_VERSION;
    value.detector_worker_count = 1U;
    value.detectors = &binding;
    value.geometry.context = &profile;
    value.geometry.derive = derive;
    value.geometry.profile_manifest_digest[0] = 2U;
    return value;
}

void initialize(Source& source, const leo_scanner_recorded_plan& plan_value) {
    source.plan = &plan_value;
    source.iq.assign(static_cast<std::size_t>(dwell_samples) * 4U, 1);
}

int run(Source& source, leo_scanner_recorded_config& cfg,
        leo_scanner_recorded_plan& plan_value, Profile& profile,
        Events* events, leo_scanner_source_stats& stats) {
    leo_source_port port{};
    assert(leo_source_port_init(&port, &source, &source_ops) == 0);
    leo_scanner_profile_detector_binding binding{};
    auto options = execution(profile, binding);
    auto needed = requirements();
    return leo_scanner_run_source_profiled_recorded_ex(&cfg, &plan_value,
        &port, &needed, &options, events ? sink : nullptr, events, &stats);
}

void test_preserves_global_visits_and_omissions() {
    auto cfg = config(); auto rows = visits(); auto plan_value = plan(rows);
    Source source; initialize(source, plan_value); Profile profile; Events events;
    leo_scanner_source_stats stats{};
    assert(run(source, cfg, plan_value, profile, &events, stats) == 0);
    assert(events.visits.size() == 2U);
    assert(events.visits[0].event.visit == 41U &&
        events.visits[1].event.visit == 97U);
    assert(events.visits[0].event.selection_counter == 100U &&
        events.visits[1].event.selection_counter == 2000000U);
    assert(events.visits[0].event.target == 0U &&
        events.visits[1].event.target == 1U);
    assert(events.visits[0].event.profile == 2U &&
        events.visits[1].event.profile == 5U);
    assert(events.visits[0].event.frequency_hz == 10750000000ULL &&
        events.visits[1].event.frequency_hz == 11900000000ULL);
    for (const auto& event : events.visits) {
        assert(event.counter_authority == LEO_SOURCE_COUNTER_PROVIDER_EXACT);
        assert(event.position_semantics == LEO_SOURCE_POSITION_COHERENT_CURRENT);
        assert(event.time_authority == LEO_SOURCE_TIME_NONE);
        assert(event.transition_flags == transition_flags);
    }
    assert((profile.derived_visits == std::vector<std::uint64_t>{41U, 97U}));
    assert((profile.derived_targets == std::vector<std::uint32_t>{2U, 5U}));
    assert(profile.analyzes == 2U);
    assert(stats.scanner.visits_intact == 2U);
    assert(stats.scanner.missing_samples == 0U);
    assert(stats.scanner.detector_completed == 2U);
}

void test_malformed_plan_rejected_before_source() {
    for (unsigned malformed = 0; malformed < 10U; ++malformed) {
        auto cfg = config(); auto rows = visits(); auto plan_value = plan(rows);
        if (malformed == 0U) rows[1].visit = rows[0].visit;
        if (malformed == 1U) rows[1].valid_start = rows[0].valid_end - 1U;
        if (malformed == 2U) rows[0].target_key = 4U;
        if (malformed == 3U) rows[0].dwell_ms = 240U;
        if (malformed == 4U) rows[0].expected_profile_crc32 = 1U;
        if (malformed == 5U) memset(plan_value.plan_digest, 0,
            sizeof(plan_value.plan_digest));
        if (malformed == 6U)
            rows[0].transition_previous_valid_end = rows[0].selection_counter + 1U;
        if (malformed == 7U)
            rows[1].selection_counter = rows[0].valid_end - 1U;
        if (malformed == 8U)
            rows[0].expected_actual_frequency_hz += 3U;
        if (malformed == 9U)
            rows[0].expected_transition_flags |=
                LEO_SOURCE_TRANSITION_VALID_TIME_BOUNDARY;
        Source source; initialize(source, plan_value); Profile profile;
        leo_scanner_source_stats stats{};
        assert(run(source, cfg, plan_value, profile, nullptr, stats) == -EINVAL);
        /* Port initialization performs the sole capability read.  Scanner
         * preflight must not make another source call for a malformed plan. */
        assert(source.capabilities_calls == 1U && source.selected == 0U);
    }
}

void test_transition_mismatch_rejected_before_capture() {
    auto cfg = config(); auto rows = visits(); rows.resize(1U);
    auto plan_value = plan(rows); Source source; initialize(source, plan_value);
    source.transition_mismatch = true; Profile profile;
    leo_scanner_source_stats stats{};
    assert(run(source, cfg, plan_value, profile, nullptr, stats) == -EPROTO);
    assert(source.delivered == 0U && profile.derived_visits.empty());
    assert(stats.scanner.stop_reason == LEO_SCANNER_STOP_SOURCE_ERROR);
}

void test_gap_inside_dwell_is_incomplete() {
    auto cfg = config(); auto rows = visits(); rows.resize(1U);
    auto plan_value = plan(rows); Source source; initialize(source, plan_value);
    source.gap_inside = true; Profile profile;
    leo_scanner_source_stats stats{};
    assert(run(source, cfg, plan_value, profile, nullptr, stats) == 0);
    assert(stats.scanner.visits_incomplete == 1U);
    assert(stats.scanner.missing_samples == 1U);
    assert(stats.scanner.detector_accepted == 0U && profile.analyzes == 0U);
}

void test_unpaced_plan_longer_than_queue_is_lossless() {
    auto cfg = config();
    cfg.detector_queue_capacity = 1U;
    std::vector<leo_scanner_recorded_visit> rows;
    rows.reserve(20U);
    std::uint64_t selection = 100U;
    for (std::uint64_t i = 0; i < 20U; ++i) {
        const std::uint32_t target = static_cast<std::uint32_t>(i % 2U);
        const auto& configured = cfg.targets[target];
        const std::uint64_t valid_start = selection + 100U;
        rows.push_back({1000U + i, target, configured.profile, 120U, 1U,
            transition_flags, 0U, configured.frequency_hz,
            configured.frequency_hz, selection, selection, selection + 50U,
            valid_start, valid_start + dwell_samples});
        selection = valid_start + dwell_samples + 1000U;
    }
    auto plan_value = plan(rows); Source source; initialize(source, plan_value);
    Profile profile; profile.analyze_delay_ms = 20U;
    leo_scanner_source_stats stats{};
    assert(run(source, cfg, plan_value, profile, nullptr, stats) == 0);
    assert(profile.analyzes == 20U && stats.scanner.detector_completed == 20U);
    assert(stats.scanner.detector_queue_drops == 0U);
    assert(stats.scanner.detector_queue_high_water == 1U);
}
} // namespace

int main() {
    test_preserves_global_visits_and_omissions();
    test_malformed_plan_rejected_before_source();
    test_transition_mismatch_rejected_before_capture();
    test_gap_inside_dwell_is_incomplete();
    test_unpaced_plan_longer_than_queue_is_lossless();
    return 0;
}
