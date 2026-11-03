#include "scanner_profile.h"

#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include <condition_variable>
#include <cstdint>
#include <limits>
#include <mutex>
#include <vector>

namespace {
constexpr std::uint32_t rate = 7500000U;
constexpr std::uint32_t dwell_samples = rate * 120U / 1000U;
constexpr std::uint32_t transition_samples = rate * 20U / 1000U;

std::uint64_t future_deadline() {
    timespec value{}; assert(clock_gettime(CLOCK_MONOTONIC, &value) == 0);
    return static_cast<std::uint64_t>(value.tv_sec) * 1000000000ULL +
        static_cast<std::uint64_t>(value.tv_nsec) + 10000000000ULL;
}

struct Source {
    std::vector<std::int16_t> iq[2];
    std::uint64_t coordinate{};
    std::uint32_t next{};
    bool leased{};
    std::int64_t frequency_delta{};
    std::uint32_t target_delta{};
};

int capabilities(void*, leo_source_capabilities* out) {
    *out = {LEO_SOURCE_PORT_ABI_VERSION, LEO_SOURCE_SAMPLE_FORMAT_CI16,
        LEO_SOURCE_CAP_CANCEL | LEO_SOURCE_CAP_SELECT |
        LEO_SOURCE_CAP_SIMULTANEOUS_RX | LEO_SOURCE_CAP_COHERENT_RX |
        LEO_SOURCE_CAP_FREQUENCY_ATTESTATION | LEO_SOURCE_CAP_TARGET_ATTESTATION |
        LEO_SOURCE_CAP_PROFILE_CRC_ATTESTATION | LEO_SOURCE_CAP_EXACT_GAP |
        LEO_SOURCE_CAP_VALID_SELECTION_BOUNDARY,
        rate, 2U, dwell_samples, LEO_SOURCE_COUNTER_PROVIDER_EXACT,
        LEO_SOURCE_POSITION_COHERENT_CURRENT, LEO_SOURCE_TIME_NONE, 0U};
    return 0;
}
int position(void* context, leo_source_position* out) {
    auto& source = *static_cast<Source*>(context);
    *out = {source.coordinate, LEO_SOURCE_COUNTER_PROVIDER_EXACT,
        LEO_SOURCE_POSITION_COHERENT_CURRENT};
    return 0;
}
int select_source(void* context, const leo_source_selection* selection,
                  leo_source_transition* out) {
    auto& source = *static_cast<Source*>(context);
    out->flags = LEO_SOURCE_TRANSITION_FREQUENCY_ATTESTED |
        LEO_SOURCE_TRANSITION_TARGET_ATTESTED |
        LEO_SOURCE_TRANSITION_PROFILE_CRC_ATTESTED |
        LEO_SOURCE_TRANSITION_VALID_COUNTER_BOUNDARY;
    out->selected_target_key = selection->target_key + source.target_delta;
    out->profile_crc32 = 0x12345678U;
    out->counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    out->position_semantics = LEO_SOURCE_POSITION_COHERENT_CURRENT;
    out->time_authority = LEO_SOURCE_TIME_NONE;
    out->actual_frequency_hz = static_cast<std::uint64_t>(
        static_cast<std::int64_t>(selection->requested_frequency_hz) +
        source.frequency_delta);
    out->previous_valid_end = source.coordinate;
    out->valid_start = source.coordinate;
    return 0;
}
int next_source(void* context, leo_source_block* out) {
    auto& source = *static_cast<Source*>(context);
    if (source.next >= 2U || source.leased) return -ENODATA;
    const auto first = source.next ? transition_samples + dwell_samples :
        transition_samples;
    auto& iq = source.iq[source.next];
    *out = {};
    out->ci16 = iq.data(); out->iq_bytes = iq.size() * sizeof(iq[0]);
    out->samples_per_receiver = dwell_samples; out->receiver_count = 2U;
    out->counter_authority = LEO_SOURCE_COUNTER_PROVIDER_EXACT;
    out->first_coordinate = first; out->end_coordinate = first + dwell_samples;
    out->stream_ordinal = first; out->lease_token = source.next + 1U;
    source.coordinate = out->end_coordinate; ++source.next; source.leased = true;
    return 0;
}
int release_source(void* context, leo_source_block*) {
    auto& source = *static_cast<Source*>(context);
    assert(source.leased); source.leased = false; return 0;
}
int cancel_source(void*) { return 0; }

const leo_source_ops source_ops{capabilities, position, select_source,
    next_source, release_source, cancel_source};

struct Profile {
    std::mutex mutex;
    std::condition_variable changed;
    unsigned derives{};
    unsigned analyzes{};
    int derive_status{};
    double residual_min{-800000.0};
    double residual_max{800000.0};
    unsigned invalid_geometry{};
    std::uint32_t serialized{1U};
    std::uint32_t parity{};
    std::vector<double> observed_centers;
};

int derive(void* context, const leo_scanner_visit_authority* visit,
           leo_scanner_detector_geometry* out) {
    auto& profile = *static_cast<Profile*>(context);
    assert(visit->abi_version == LEO_SCANNER_PROFILE_ABI_VERSION);
    assert(visit->sample_rate_hz == rate && visit->receiver_count == 2U);
    assert(visit->probe_stride_ms == 120U && visit->valid_end > visit->valid_start);
    if (profile.derive_status) return profile.derive_status;
    unsigned ordinal;
    {
        std::lock_guard<std::mutex> lock(profile.mutex);
        ordinal = ++profile.derives;
    }
    *out = {};
    out->abi_version = LEO_SCANNER_PROFILE_ABI_VERSION;
    out->sample_rate_hz = rate; out->receiver_count = 2U;
    out->probe_ms = 20U; out->probe_stride_ms = 120U;
    out->receiver_center_hz[0] = -312500.0 + ordinal;
    out->receiver_center_hz[1] = -312500.0 + ordinal;
    out->residual_cfo_min_hz = profile.residual_min;
    out->residual_cfo_max_hz = profile.residual_max;
    out->profile_manifest_digest[0] = 2U;
    out->authority_digest[0] = static_cast<std::uint8_t>(ordinal);
    if (profile.invalid_geometry == 1U)
        out->receiver_center_hz[0] = std::numeric_limits<double>::quiet_NaN();
    else if (profile.invalid_geometry == 2U) {
        out->residual_cfo_min_hz = 1.0; out->residual_cfo_max_hz = -1.0;
    } else if (profile.invalid_geometry == 3U)
        memset(out->authority_digest, 0, sizeof(out->authority_digest));
    else if (profile.invalid_geometry == 4U)
        out->probe_ms = 10U;
    else if (profile.invalid_geometry == 5U)
        out->profile_manifest_digest[0] = 3U;
    profile.changed.notify_all();
    return 0;
}

int profile_capabilities(void* context, leo_scanner_profile_capabilities* out) {
    auto& profile = *static_cast<Profile*>(context);
    *out = {LEO_SCANNER_PROFILE_ABI_VERSION, rate, 2U, 20U, 120U,
        profile.serialized, 1U, profile.parity, 22U, 22U, 1600000U};
    return 0;
}

int analyze(void* context, const leo_scanner_detector_geometry* geometry,
            const std::int16_t*, std::size_t complex_times, std::uint32_t dwell_ms,
            std::uint32_t stride_ms, leo_native_glrt_result* out) {
    auto& profile = *static_cast<Profile*>(context);
    assert(complex_times == static_cast<std::size_t>(rate) * dwell_ms / 1000U);
    assert(stride_ms == 120U);
    {
        std::unique_lock<std::mutex> lock(profile.mutex);
        profile.changed.wait(lock, [&] { return profile.derives >= 2U; });
        profile.observed_centers.push_back(geometry->receiver_center_hz[0]);
        ++profile.analyzes;
    }
    *out = {};
    out->row_count = 2U;
    for (int receiver = 0; receiver < 2; ++receiver) {
        out->rows[receiver].receiver_id = receiver;
        out->rows[receiver].probe_index = 0;
        out->rows[receiver].probe_start_ms = 0;
        out->rows[receiver].candidate_count = 1;
        out->rows[receiver].candidates[0].fractional_epoch_status = 1;
    }
    return 0;
}

struct Events { unsigned candidates{}; bool parity_seen{true}; };
void sink(void* context, const leo_scanner_source_event* event) {
    auto& seen = *static_cast<Events*>(context);
    if (event->event.kind == LEO_SCANNER_CANDIDATE) {
        ++seen.candidates;
        seen.parity_seen = event->event.fractional_epoch_server_parity_qualified;
    }
}

leo_scanner_config config(unsigned visits) {
    leo_scanner_config value{};
    value.abi_version = LEO_SCANNER_ABI_VERSION;
    value.session = 1U; value.generation = 2U; value.seed = 3U;
    value.sample_rate_hz = rate; value.receiver_count = 2U;
    value.duration_ms = 400U; value.maximum_visits = visits;
    value.wall_deadline_monotonic_ns = future_deadline(); value.dwell_ms = 120U;
    value.transition_budget_ms = 20U; value.maximum_revisit_ms = 3000U;
    value.feedback_age_ms = 1000U; value.application_delay_ms = 1000U;
    value.decay_ms = 3000U; value.maximum_boost = 3U;
    value.detector_queue_capacity = 2U; value.active_threshold_dbfs = -38.0;
    value.target_count = 1U;
    value.targets[0] = {0U, 10750000000ULL, 0x12345678U, 1U};
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

leo_scanner_profile_execution_options execution(Profile& profile,
        leo_scanner_profile_detector_binding& binding) {
    binding = {};
    binding.abi_version = LEO_SCANNER_PROFILE_ABI_VERSION;
    binding.ops = {&profile, analyze, profile_capabilities};
    binding.configuration_digest[0] = 1U;
    leo_scanner_profile_execution_options value{};
    value.abi_version = LEO_SCANNER_PROFILE_ABI_VERSION;
    value.detector_worker_count = 1U; value.detectors = &binding;
    value.geometry.context = &profile; value.geometry.derive = derive;
    value.geometry.profile_manifest_digest[0] = 2U;
    return value;
}

void initialize_source(Source& source) {
    for (auto& iq : source.iq) iq.assign(static_cast<std::size_t>(dwell_samples) * 4U, 1);
}

void test_immutable_geometry_and_false_parity() {
    Source source; initialize_source(source); leo_source_port port{};
    assert(leo_source_port_init(&port, &source, &source_ops) == 0);
    Profile profile; leo_scanner_profile_detector_binding binding{};
    auto options = execution(profile, binding); auto scanner = config(2U);
    auto needed = requirements(); Events events{}; leo_scanner_source_stats stats{};
    const int status = leo_scanner_run_source_profiled_ex(&scanner, &port, &needed,
        &options, sink, &events, &stats);
    if (status) fprintf(stderr, "profile scanner status=%d reason=%u stop=%d\n",
        status, stats.scanner.stop_reason, stats.scanner.stop_status);
    assert(status == 0);
    assert(profile.derives == 2U && profile.analyzes == 2U);
    assert(profile.observed_centers.size() == 2U);
    assert(profile.observed_centers[0] == -312499.0);
    assert(profile.observed_centers[1] == -312498.0);
    assert(events.candidates == 4U && !events.parity_seen);
    assert(stats.scanner.detector_completed == 2U);
}

void test_geometry_rejected_before_capture() {
    Source source; initialize_source(source); leo_source_port port{};
    assert(leo_source_port_init(&port, &source, &source_ops) == 0);
    Profile profile; profile.residual_max = 800001.0;
    leo_scanner_profile_detector_binding binding{}; auto options = execution(profile, binding);
    auto scanner = config(1U); auto needed = requirements();
    leo_scanner_source_stats stats{};
    assert(leo_scanner_run_source_profiled_ex(&scanner, &port, &needed, &options,
        nullptr, nullptr, &stats) == -EPROTO);
    assert(source.next == 0U && profile.analyzes == 0U);
    assert(stats.scanner.stop_reason == LEO_SCANNER_STOP_DETECTOR_ERROR);
}

void test_geometry_callback_failure_rejected_before_capture() {
    for (const int failure : {-EIO, EBUSY}) {
        Source source; initialize_source(source); leo_source_port port{};
        assert(leo_source_port_init(&port, &source, &source_ops) == 0);
        Profile profile; profile.derive_status = failure;
        leo_scanner_profile_detector_binding binding{};
        auto options = execution(profile, binding); auto scanner = config(1U);
        auto needed = requirements(); leo_scanner_source_stats stats{};
        const int expected = failure > 0 ? -EIO : failure;
        assert(leo_scanner_run_source_profiled_ex(&scanner, &port, &needed,
            &options, nullptr, nullptr, &stats) == expected);
        assert(source.next == 0U && profile.analyzes == 0U);
        assert(stats.scanner.stop_reason == LEO_SCANNER_STOP_DETECTOR_ERROR);
        assert(stats.scanner.stop_status == expected);
    }
}

void test_malformed_geometry_rejected_before_capture() {
    for (unsigned malformed = 1U; malformed <= 5U; ++malformed) {
        Source source; initialize_source(source); leo_source_port port{};
        assert(leo_source_port_init(&port, &source, &source_ops) == 0);
        Profile profile; profile.invalid_geometry = malformed;
        leo_scanner_profile_detector_binding binding{};
        auto options = execution(profile, binding); auto scanner = config(1U);
        auto needed = requirements(); leo_scanner_source_stats stats{};
        assert(leo_scanner_run_source_profiled_ex(&scanner, &port, &needed,
            &options, nullptr, nullptr, &stats) == -EPROTO);
        assert(source.next == 0U && profile.analyzes == 0U);
        assert(stats.scanner.stop_reason == LEO_SCANNER_STOP_DETECTOR_ERROR);
    }
}

void test_malformed_capabilities_rejected_preflight() {
    for (unsigned variant = 0; variant < 2U; ++variant) {
        Source source; initialize_source(source); leo_source_port port{};
        assert(leo_source_port_init(&port, &source, &source_ops) == 0);
        Profile profile;
        if (variant == 0U) profile.serialized = 0U;
        else profile.parity = 2U;
        leo_scanner_profile_detector_binding binding{};
        auto options = execution(profile, binding); auto scanner = config(1U);
        auto needed = requirements(); leo_scanner_source_stats stats{};
        assert(leo_scanner_run_source_profiled_ex(&scanner, &port, &needed,
            &options, nullptr, nullptr, &stats) == -ENOTSUP);
        assert(source.next == 0U && profile.derives == 0U && profile.analyzes == 0U);
        assert(stats.scanner.stop_reason == LEO_SCANNER_STOP_DETECTOR_ERROR);
    }
}

void test_transition_mismatch_rejected_before_geometry() {
    for (unsigned variant = 0; variant < 2U; ++variant) {
        Source source; initialize_source(source);
        if (variant == 0U) source.frequency_delta = 3;
        else source.target_delta = 1U;
        leo_source_port port{};
        assert(leo_source_port_init(&port, &source, &source_ops) == 0);
        Profile profile; leo_scanner_profile_detector_binding binding{};
        auto options = execution(profile, binding); auto scanner = config(1U);
        auto needed = requirements(); leo_scanner_source_stats stats{};
        const int status = leo_scanner_run_source_profiled_ex(&scanner, &port,
            &needed, &options, nullptr, nullptr, &stats);
        assert(status == (variant == 0U ? -ERANGE : -EPROTO));
        assert(source.next == 0U && profile.derives == 0U && profile.analyzes == 0U);
        assert(stats.scanner.stop_reason == LEO_SCANNER_STOP_SOURCE_ERROR);
    }
}

void test_profile_shape_preflight() {
    Source source; initialize_source(source); leo_source_port port{};
    assert(leo_source_port_init(&port, &source, &source_ops) == 0);
    Profile profile; leo_scanner_profile_detector_binding binding{};
    auto options = execution(profile, binding); auto scanner = config(1U);
    auto needed = requirements(); leo_scanner_source_stats stats{};
    options.detector_worker_count = 2U;
    assert(leo_scanner_run_source_profiled_ex(&scanner, &port, &needed, &options,
        nullptr, nullptr, &stats) == -EINVAL);
    options.detector_worker_count = 1U; options.geometry.profile_manifest_digest[0] = 0U;
    assert(leo_scanner_run_source_profiled_ex(&scanner, &port, &needed, &options,
        nullptr, nullptr, &stats) == -EINVAL);
}
} // namespace

int main() {
    test_immutable_geometry_and_false_parity();
    test_geometry_rejected_before_capture();
    test_geometry_callback_failure_rejected_before_capture();
    test_malformed_geometry_rejected_before_capture();
    test_malformed_capabilities_rejected_preflight();
    test_transition_mismatch_rejected_before_geometry();
    test_profile_shape_preflight();
    return 0;
}
