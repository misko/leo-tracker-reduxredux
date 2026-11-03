#include "scanner.h"
#include "local_radio_prepare.h"
#include "json_number.h"

#include <cerrno>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <mutex>
#include <thread>
#include <time.h>
#include <vector>

namespace {

struct Options {
    uint32_t duration_ms = 0, visits = 0, dwell_ms = 0, block_ms = 0;
    const char* exact = nullptr;
    const char* control = nullptr;
    std::vector<leo_scanner_target> targets;
};

bool number(const char* text, uint64_t maximum, uint64_t& out,
    bool allow_zero = false) {
    char* end = nullptr;
    if (!text || text[0] == '-') return false;
    errno = 0;
    const unsigned long long value = std::strtoull(text, &end, 10);
    if (errno || end == text || *end || (!allow_zero && !value) || value > maximum)
        return false;
    out = static_cast<uint64_t>(value);
    return true;
}

int monotonic_ns(uint64_t& value) {
    struct timespec now{};
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return -errno;
    value = static_cast<uint64_t>(now.tv_sec) * UINT64_C(1000000000) +
        static_cast<uint64_t>(now.tv_nsec);
    return 0;
}

struct SourceDeadline {
    leo_local_source* source;
    std::mutex mutex;
    std::condition_variable changed;
    bool finished = false;
    std::thread worker;
    SourceDeadline(leo_local_source* value, uint64_t deadline, uint64_t now)
        : source(value), worker([this, deadline, now] {
            std::unique_lock<std::mutex> lock(mutex);
            if (!changed.wait_for(lock, std::chrono::nanoseconds(deadline - now),
                    [this] { return finished; }))
                (void)leo_local_source_cancel(source);
        }) {}
    ~SourceDeadline() {
        {
            std::lock_guard<std::mutex> lock(mutex);
            finished = true;
        }
        changed.notify_one();
        if (worker.joinable()) worker.join();
    }
};

bool options(int argc, char** argv, Options& out) {
    if (argc < 12 || std::strcmp(argv[1], "--capture") ||
        std::strcmp(argv[2], "--duration-ms") ||
        std::strcmp(argv[4], "--maximum-visits") ||
        std::strcmp(argv[6], "--active-dwell-ms")) return false;
    uint64_t value = 0;
    if (!number(argv[3], 1800000U, value)) return false;
    out.duration_ms = static_cast<uint32_t>(value);
    if (!number(argv[5], 16384U, value)) return false;
    out.visits = static_cast<uint32_t>(value);
    if (!number(argv[7], 360U, value) ||
        (value != 120U && value != 240U && value != 360U)) return false;
    out.dwell_ms = static_cast<uint32_t>(value);
    int i = 8;
    if (i < argc && !std::strcmp(argv[i], "--block-ms")) {
        if (++i >= argc || !number(argv[i++], 120U, value) ||
            (value != 20U && value != 120U)) return false;
        out.block_ms = static_cast<uint32_t>(value);
    }
    if (i + 3 >= argc || std::strcmp(argv[i++], "--exact-template")) return false;
    out.exact = argv[i++];
    if (std::strcmp(argv[i++], "--control-template")) return false;
    out.control = argv[i++];
    while (i < argc) {
        if (!std::strcmp(argv[i], "--block-ms")) {
            if (out.block_ms || ++i >= argc || !number(argv[i++], 120U, value) ||
                (value != 20U && value != 120U)) return false;
            out.block_ms = static_cast<uint32_t>(value);
            continue;
        }
        if (std::strcmp(argv[i++], "--target") || i + 1 >= argc ||
            out.targets.size() == LEO_SCANNER_MAX_TARGETS) return false;
        leo_scanner_target target{};
        if (!number(argv[i++], 7U, value, true)) return false;
        target.profile = static_cast<uint32_t>(value);
        if (!number(argv[i++], std::numeric_limits<uint64_t>::max(), value)) return false;
        if (value < UINT64_C(70000000) || value > UINT64_C(6000000000)) return false;
        target.frequency_hz = value;
        target.baseline_weight = 1U;
        out.targets.push_back(target);
    }
    return out.block_ms && !out.targets.empty();
}

template<typename T>
bool read_exact(const char* path, size_t count, std::vector<T>& values) {
    values.resize(count);
    std::ifstream stream(path, std::ios::binary);
    stream.read(reinterpret_cast<char*>(values.data()),
        static_cast<std::streamsize>(count * sizeof(T)));
    return stream && stream.peek() == std::ifstream::traits_type::eof();
}

int detector_analyze(void* context, const int16_t* iq, size_t times,
    uint32_t dwell_ms, uint32_t stride_ms, leo_native_glrt_result* result) {
    return leo_native_glrt_analyze(static_cast<leo_native_glrt*>(context), iq,
        times, dwell_ms, stride_ms, result);
}

int detector_capabilities(void*, leo_native_glrt_capabilities* capabilities) {
    return leo_native_glrt_get_capabilities(capabilities);
}

const char* kind(uint32_t value) {
    switch (value) {
    case LEO_SCANNER_VISIT: return "visit";
    case LEO_SCANNER_QUEUE_DROP: return "queue_drop";
    case LEO_SCANNER_DETECTOR_FAILURE: return "detector_failure";
    case LEO_SCANNER_DETECTOR_RESULT: return "detector_result";
    case LEO_SCANNER_CANDIDATE: return "candidate";
    case LEO_SCANNER_POLICY_ACK: return "policy_ack";
    default: return "unknown";
    }
}

const char* stop_reason(uint32_t value) {
    switch (value) {
    case LEO_SCANNER_STOP_SOURCE_DURATION: return "source_duration";
    case LEO_SCANNER_STOP_MAXIMUM_VISITS: return "maximum_visits";
    case LEO_SCANNER_STOP_POLICY_COMPLETE: return "policy_complete";
    case LEO_SCANNER_STOP_WALL_DEADLINE: return "wall_deadline";
    case LEO_SCANNER_STOP_SOURCE_ERROR: return "source_error";
    case LEO_SCANNER_STOP_POLICY_ERROR: return "policy_error";
    case LEO_SCANNER_STOP_DETECTOR_ERROR: return "detector_error";
    case LEO_SCANNER_STOP_INTERNAL_ERROR: return "internal_error";
    default: return "none";
    }
}

void emit(void*, const leo_scanner_event* event) {
    std::printf("{\"schema\":\"leo-native-scanner-event/v2\",\"kind\":\"%s\","
        "\"visit\":%" PRIu64 ",\"target\":%u,\"profile\":%u,"
        "\"frequency_hz\":%" PRIu64 ",\"attested_profile_crc32\":%u,"
        "\"valid_start\":%" PRIu64
        ",\"valid_end\":%" PRIu64
        ",\"selection_counter\":%" PRIu64
        ",\"transition_counter_before\":%" PRIu64
        ",\"transition_counter_after\":%" PRIu64
        ",\"recalled\":%s,\"feedback_outcome\":%u,"
        "\"energy_sum\":%" PRIu64 ",\"energy_sample_count\":%" PRIu64
        ",\"windows_emitted\":%u,\"power_dbfs\":",
        kind(event->kind), event->visit, event->target, event->profile,
        event->frequency_hz, event->attested_profile_crc32, event->valid_start,
        event->valid_end, event->selection_counter,
        event->transition_counter_before, event->transition_counter_after,
        event->recalled ? "true" : "false", event->feedback_outcome, event->energy_sum,
        event->energy_sample_count, event->windows_emitted);
    leo_scanner_json_number(stdout, event->power_dbfs);
    std::printf(",\"detector_status\":%d,"
        "\"detector_enqueued_monotonic_ns\":%" PRIu64
        ",\"detector_started_monotonic_ns\":%" PRIu64
        ",\"detector_finished_monotonic_ns\":%" PRIu64
        ",\"detector_queue_ns\":%" PRIu64
        ",\"detector_runtime_ns\":%" PRIu64
        ",\"detector_row_count\":%u,"
        "\"fractional_server_parity_qualified\":%s",
        event->detector_status, event->detector_enqueued_monotonic_ns,
        event->detector_started_monotonic_ns,
        event->detector_finished_monotonic_ns, event->detector_queue_ns,
        event->detector_runtime_ns, event->detector_row_count,
        event->fractional_epoch_server_parity_qualified ? "true" : "false");
    if (event->kind == LEO_SCANNER_CANDIDATE) {
        std::printf(",\"receiver_id\":%d,\"probe_index\":%d,\"candidate_index\":%u,"
            "\"epoch\":%d,\"tracking_cfo_hz\":",
            event->receiver_id, event->probe_index, event->candidate_index,
            event->candidate.epoch);
        leo_scanner_json_number(stdout, event->candidate.tracking_cfo_hz);
        std::fputs(",\"margin\":", stdout);
        leo_scanner_json_number(stdout, event->candidate.margin);
        std::printf(",\"fractional_status\":%d,\"fractional_offset_samples\":",
            event->candidate.fractional_epoch_status);
        leo_scanner_json_number(stdout,
            event->candidate.fractional_epoch_offset_samples);
        std::fputs(",\"fractional_tracking_cfo_hz\":", stdout);
        leo_scanner_json_number(stdout,
            event->candidate.fractional_tracking_cfo_hz);
        std::fputs(",\"fractional_margin\":", stdout);
        leo_scanner_json_number(stdout, event->candidate.fractional_margin);
    }
    std::puts("}");
    std::fflush(stdout);
}

} // namespace

int main(int argc, char** argv) {
    if (argc == 1) {
        std::puts("{\"schema\":\"leo-native-scanner/v1\",\"capture\":false,"
            "\"requires_explicit_capture_flag\":true,\"maximum_duration_ms\":1800000,"
            "\"sample_rate_hz\":2500000,\"feedback_classifier\":"
            "\"ci16-mean-complex-power-v1@-38.0dBFS\","
            "\"fractional_server_parity_qualified\":false}");
        return 0;
    }
    Options parsed;
    if (!options(argc, argv, parsed)) {
        std::fprintf(stderr, "usage: %s --capture --duration-ms 1..1800000 "
            "--maximum-visits 1..16384 --active-dwell-ms 120|240|360 "
            "--block-ms 20|120 "
            "--exact-template FILE --control-template FILE "
            "--target PROFILE FREQUENCY_HZ [--target ...]\n", argv[0]);
        return 2;
    }
    uint64_t capture_started = 0;
    if (monotonic_ns(capture_started)) return 3;
    const uint64_t wall_deadline = capture_started +
        static_cast<uint64_t>(parsed.duration_ms) * UINT64_C(1000000);
    constexpr uint32_t sample_rate = 2500000U;
    const size_t template_count = (sample_rate + 375U) / 750U;
    std::vector<leo_native_glrt_complex> exact, control;
    if (!read_exact(parsed.exact, template_count, exact) ||
        !read_exact(parsed.control, template_count, control)) {
        std::fprintf(stderr, "template size/read failure\n");
        return 3;
    }
    leo_native_glrt* glrt = nullptr;
    int ret = leo_native_glrt_create_with_mode(&glrt, sample_rate, exact.data(),
        control.data(), template_count,
        LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH);
    if (ret) { std::fprintf(stderr, "detector setup failed: %d\n", ret); return 4; }

    leo_local_radio_prepare_config prepare_config{};
    prepare_config.abi_version = LEO_LOCAL_RADIO_PREPARE_ABI_VERSION;
    prepare_config.sample_rate_hz = sample_rate;
    prepare_config.analog_bandwidth_hz = sample_rate;
    prepare_config.receiver_count = 2U;
    prepare_config.manual_gain_millidb = 40000;
    prepare_config.target_count = static_cast<uint32_t>(parsed.targets.size());
    for (size_t i = 0; i < parsed.targets.size(); ++i) {
        prepare_config.targets[i].profile = parsed.targets[i].profile;
        prepare_config.targets[i].frequency_hz = parsed.targets[i].frequency_hz;
    }
    leo_local_config local{};
    local.sample_rate_hz = sample_rate;
    local.analog_bandwidth_hz = sample_rate;
    local.samples_per_block = sample_rate * parsed.block_ms / 1000U;
    local.receiver_count = 2U;
    local.kernel_buffer_count = LEO_LOCAL_RADIO_KERNEL_BUFFERS;
    local.profile_count = static_cast<uint32_t>(parsed.targets.size());
    for (size_t i = 0; i < parsed.targets.size(); ++i) {
        local.profiles[i].profile = parsed.targets[i].profile;
        local.profiles[i].frequency_hz = parsed.targets[i].frequency_hz;
    }
    leo_local_owner* owner = nullptr;
    ret = leo_local_radio_preflight_inactive(
        leo_local_iio_radio_prepare_provider());
    if (ret) {
        leo_native_glrt_destroy(glrt);
        std::fprintf(stderr, "local radio preflight failed: %d\n", ret);
        return 5;
    }
    ret = leo_local_owner_acquire(&local, leo_local_iio_provider(), &owner);
    if (ret) {
        leo_native_glrt_destroy(glrt);
        std::fprintf(stderr, "local owner acquisition failed: %d\n", ret);
        return 5;
    }
    leo_local_radio_preparation* preparation = nullptr;
    leo_local_radio_prepare_receipt prepare_receipt{};
    ret = leo_local_radio_prepare_owned(&prepare_config,
        leo_local_iio_radio_prepare_provider(), owner, &preparation,
        &prepare_receipt);
    if (ret) {
        int preparation_restore_status = 0;
        if (preparation) {
            leo_local_radio_restore_receipt restored{};
            preparation_restore_status = leo_local_radio_restore(&preparation,
                owner, &restored);
            if (preparation_restore_status)
                preparation_restore_status = leo_local_radio_restore(&preparation,
                    owner, &restored);
        }
        leo_local_restore_receipt ignored{};
        const int owner_status = leo_local_owner_release(owner, 0U, &ignored);
        leo_native_glrt_destroy(glrt);
        std::fprintf(stderr,
            "local radio preparation failed: prepare=%d restore=%d owner=%d\n",
            ret, preparation_restore_status, owner_status);
        return 5;
    }
    for (size_t i = 0; i < parsed.targets.size(); ++i)
        parsed.targets[i].profile_crc32 =
            prepare_receipt.targets[i].profile_crc32;
    auto restore_radio = [&preparation, &owner]() {
        leo_local_radio_restore_receipt restored{};
        if (!preparation) return 0;
        int status = leo_local_radio_restore(&preparation, owner, &restored);
        if (status && preparation)
            status = leo_local_radio_restore(&preparation, owner, &restored);
        return status;
    };
    uint64_t after_prepare = 0;
    ret = monotonic_ns(after_prepare);
    if (!ret && after_prepare >= wall_deadline) ret = -ETIMEDOUT;
    if (ret) {
        leo_local_restore_receipt owner_restore{};
        const int deactivate_status = leo_local_owner_is_active(owner) ?
            leo_local_owner_deactivate(owner, 0U, &owner_restore) : 0;
        const int restore_status = restore_radio();
        leo_local_restore_receipt ignored{};
        const int owner_status = leo_local_owner_release(owner, 0U, &ignored);
        leo_native_glrt_destroy(glrt);
        std::fprintf(stderr,
            "local radio setup deadline failed: setup=%d deactivate=%d restore=%d owner=%d\n",
            ret, deactivate_status, restore_status, owner_status);
        return 5;
    }
    for (size_t i = 0; i < parsed.targets.size(); ++i) {
        local.profiles[i].crc32 = parsed.targets[i].profile_crc32;
    }
    leo_local_source* source = nullptr;
    ret = leo_local_source_open_owned(&local, leo_local_iio_provider(), owner,
        &source);
    if (ret) {
        leo_local_restore_receipt owner_restore{};
        const int deactivate_status = leo_local_owner_is_active(owner) ?
            leo_local_owner_deactivate(owner, 0U, &owner_restore) : 0;
        const int restore_status = restore_radio();
        leo_local_restore_receipt ignored{};
        const int owner_status = leo_local_owner_release(owner, 0U, &ignored);
        leo_native_glrt_destroy(glrt);
        std::fprintf(stderr,
            "local open failed: open=%d deactivate=%d restore=%d owner=%d\n",
            ret, deactivate_status, restore_status, owner_status);
        return 5;
    }
    uint64_t after_open = 0;
    ret = monotonic_ns(after_open);
    if (!ret && after_open >= wall_deadline) ret = -ETIMEDOUT;
    leo_local_prime_receipt prime{};
    if (!ret) {
        SourceDeadline setup_deadline(source, wall_deadline, after_open);
        ret = leo_local_source_prime(source, &prime);
    }
    if (ret) {
        leo_local_owner* returned_owner = nullptr;
        const int close_status = leo_local_source_close_preserve_owner(source,
            &returned_owner);
        owner = returned_owner;
        leo_local_restore_receipt owner_restore{};
        const int deactivate_status = owner && leo_local_owner_is_active(owner) ?
            leo_local_owner_deactivate(owner, 0U, &owner_restore) : 0;
        const int restore_status = restore_radio();
        leo_local_restore_receipt ignored{};
        const int owner_status = owner ? leo_local_owner_release(owner, 0U,
            &ignored) : -EIO;
        leo_native_glrt_destroy(glrt);
        std::fprintf(stderr,
            "local prime failed: prime=%d close=%d deactivate=%d restore=%d owner=%d\n",
            ret, close_status, deactivate_status, restore_status, owner_status);
        return 6;
    }
    leo_scanner_config config{};
    config.abi_version = LEO_SCANNER_ABI_VERSION;
    config.session = prime.coherent_counter ? prime.coherent_counter : 1U;
    config.generation = 1U;
    config.seed = config.session ^ UINT64_C(0x9e3779b97f4a7c15);
    config.sample_rate_hz = sample_rate;
    config.receiver_count = 2U;
    config.duration_ms = parsed.duration_ms;
    config.maximum_visits = parsed.visits;
    config.wall_deadline_monotonic_ns = wall_deadline;
    config.dwell_ms = parsed.dwell_ms;
    config.transition_budget_ms = 20U;
    config.maximum_revisit_ms = 3000U;
    config.feedback_age_ms = 1000U;
    config.application_delay_ms = 1000U;
    config.decay_ms = 3000U;
    config.maximum_boost = 3U;
    config.detector_queue_capacity = 4U;
    config.active_threshold_dbfs = -38.0;
    config.target_count = static_cast<uint32_t>(parsed.targets.size());
    for (size_t i = 0; i < parsed.targets.size(); ++i) config.targets[i] = parsed.targets[i];
    leo_scanner_detector_ops detector{glrt, detector_analyze, detector_capabilities};
    leo_scanner_stats stats{};
    ret = leo_scanner_run(&config, source, &detector, emit, nullptr, &stats);
    leo_local_owner* returned_owner = nullptr;
    const int close_status = leo_local_source_close_preserve_owner(source,
        &returned_owner);
    owner = returned_owner;
    leo_local_restore_receipt owner_restore{};
    const int deactivate_status = owner && leo_local_owner_is_active(owner) ?
        leo_local_owner_deactivate(owner, 0U, &owner_restore) : 0;
    const int radio_restore_status = restore_radio();
    leo_local_restore_receipt restore{};
    const int owner_status = owner ? leo_local_owner_release(owner, 0U, &restore) : -EIO;
    const int detector_status = leo_native_glrt_destroy(glrt);
    const char* final_reason = close_status ? "source_close_error" :
        deactivate_status ? "owner_deactivate_error" :
        radio_restore_status ? "radio_restore_error" :
        owner_status ? "owner_release_error" :
        detector_status ? "detector_destroy_error" : stop_reason(stats.stop_reason);
    std::printf("{\"schema\":\"leo-native-scanner-summary/v2\","
        "\"visits\":%" PRIu64 ",\"intact\":%" PRIu64
        ",\"incomplete\":%" PRIu64 ",\"detector_completed\":%" PRIu64
        ",\"queue_drops\":%" PRIu64 ",\"candidates\":%" PRIu64
        ",\"windows_emitted\":%" PRIu64
        ",\"detector_accepted\":%" PRIu64
        ",\"detector_failures\":%" PRIu64
        ",\"detector_rows\":%" PRIu64
        ",\"detector_queue_high_water\":%zu"
        ",\"feedback_active\":%" PRIu64
        ",\"feedback_quiet\":%" PRIu64
        ",\"feedback_unknown\":%" PRIu64
        ",\"feedback_rejected\":%" PRIu64
        ",\"policy_acks\":%" PRIu64
        ",\"missing_samples\":%" PRIu64
        ",\"stop_reason\":\"%s\",\"stop_status\":%d"
        ",\"final_reason\":\"%s\",\"run_status\":%d"
        ",\"source_close_status\":%d,\"owner_deactivate_status\":%d"
        ",\"radio_restore_status\":%d,\"owner_release_status\":%d"
        ",\"detector_destroy_status\":%d"
        ",\"block_ms\":%u"
        ",\"fractional_server_parity_qualified\":false}\n",
        stats.visits_started, stats.visits_intact, stats.visits_incomplete,
        stats.detector_completed, stats.detector_queue_drops,
        stats.detector_candidates, stats.windows_emitted, stats.detector_accepted,
        stats.detector_failures, stats.detector_rows,
        stats.detector_queue_high_water, stats.feedback_active,
        stats.feedback_quiet, stats.feedback_unknown, stats.feedback_rejected,
        stats.policy_acks, stats.missing_samples, stop_reason(stats.stop_reason),
        stats.stop_status, final_reason, ret, close_status, deactivate_status,
        radio_restore_status, owner_status, detector_status, parsed.block_ms);
    if (ret || close_status || deactivate_status || radio_restore_status ||
        owner_status || detector_status) {
        std::fprintf(stderr,
            "scanner failed: run=%d close=%d deactivate=%d radio_restore=%d owner=%d detector=%d\n",
            ret, close_status, deactivate_status, radio_restore_status,
            owner_status, detector_status);
        return 7;
    }
    return 0;
}
