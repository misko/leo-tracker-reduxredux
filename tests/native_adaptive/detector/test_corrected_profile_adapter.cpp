#include "corrected_profile_adapter_internal.h"

#include <algorithm>
#include <atomic>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <thread>
#include <vector>

namespace {
template <typename T> std::vector<T> read_values(const char* path) {
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    assert(input);
    const auto bytes = input.tellg();
    assert(bytes >= 0 && static_cast<uint64_t>(bytes) % sizeof(T) == 0U);
    std::vector<T> values(static_cast<size_t>(bytes) / sizeof(T));
    input.seekg(0);
    input.read(reinterpret_cast<char*>(values.data()), bytes);
    assert(input);
    return values;
}

void conversion_is_explicit_and_fail_closed() {
    leo_corrected_profile_result_value source{};
    source.row_count = 2U;
    source.detector_cpu_ms = 1.25;
    for (size_t row = 0; row < 2U; ++row) {
        auto& r = source.rows[row];
        r.receiver_id = static_cast<int32_t>(row);
        r.probe_index = 0;
        r.probe_start_ms = 0;
        r.proposal_executed = 1; r.proposal_tracking_fallback = 2;
        r.proposal_neighbor_matches = 3; r.candidate_count = 1;
        r.retained_peak_count = 4; r.coarse_gate_skipped_count = 5;
        r.conditioned_fallback_count = 6; r.actual_executed_glrt_calls = 7;
        r.glrt_cache_hits = 8; r.conditioned_cache_hits = 9;
        r.fine_fft_cache_entries = 10; r.fine_fft_cache_hits = 11;
        r.fine_precision_calls = 12; r.fine_precision_guard_checks = 13;
        r.fine_precision_fallbacks = 14; r.fine_precision_nonfinite_fallbacks = 15;
        r.fine_precision_near_tie_fallbacks = 16;
        r.fine_precision_interpolation_fallbacks = 17;
        r.conditioned_bins_screened = 18; r.conditioned_bins_rechecked = 19;
        double* timings[] = {&r.total_cpu_ms, &r.proposal_ms, &r.stage_sum_ms,
            &r.proposal_fold_ms, &r.proposal_correlation_ms,
            &r.proposal_ranking_ms, &r.coarse_ms, &r.acquisition_ms,
            &r.fine_fft_ms, &r.conditioned_ms, &r.verification_ms, &r.glrt_ms,
            &r.fractional_epoch_ms};
        for (size_t i = 0; i < std::size(timings); ++i) *timings[i] = 20.0 + i;
        auto& c = r.candidates[0];
        c.coarse_epoch = 31; c.coarse_bin = 32; c.refined_epoch = 33;
        c.frame_support = 34; c.glrt_complete = 35;
        c.conditioned_fallback = 36; c.refinement_skipped = 37;
        double* first[] = {&c.coarse_cfo_hz, &c.fine_cfo_hz,
            &c.conditioned_cfo_hz};
        for (size_t i = 0; i < std::size(first); ++i) *first[i] = 40.0 + i;
        c.epoch = 43;
        double* scores[] = {&c.acquired_cfo_hz, &c.tracking_cfo_hz,
            &c.exact_score, &c.control_score, &c.margin, &c.acquire_score,
            &c.verify_score, &c.verify_control_score, &c.conditioned_score,
            &c.coarse_score};
        for (size_t i = 0; i < std::size(scores); ++i) *scores[i] = 44.0 + i;
        c.fractional_epoch_status = 1;
        c.fractional_epoch_offset_samples = 54.0;
        c.fractional_epoch_log_curvature = 55.0;
        for (size_t i = 0; i < 5U; ++i) {
            c.fractional_epoch_exact_grid[i] = 56.0 + i;
            c.fractional_epoch_control_grid[i] = 61.0 + i;
        }
        c.fractional_exact_score = 66.0; c.fractional_control_score = 67.0;
        c.fractional_margin = 68.0; c.fractional_residual_cfo_hz = 69.0;
        c.fractional_tracking_cfo_hz = 70.0;
    }
    leo_native_glrt_result output{};
    assert(leo_corrected_profile_convert_result(&source, 2U, &output) == 0);
    assert(output.row_count == 2U && output.detector_cpu_ms == 1.25);
#define SAME_ROW(name) assert(output.rows[0].name == source.rows[0].name)
    SAME_ROW(receiver_id); SAME_ROW(probe_index); SAME_ROW(probe_start_ms);
    SAME_ROW(proposal_executed); SAME_ROW(proposal_tracking_fallback);
    SAME_ROW(proposal_neighbor_matches); SAME_ROW(candidate_count);
    SAME_ROW(retained_peak_count); SAME_ROW(coarse_gate_skipped_count);
    SAME_ROW(conditioned_fallback_count); SAME_ROW(actual_executed_glrt_calls);
    SAME_ROW(glrt_cache_hits); SAME_ROW(conditioned_cache_hits);
    SAME_ROW(fine_fft_cache_entries); SAME_ROW(fine_fft_cache_hits);
    SAME_ROW(fine_precision_calls); SAME_ROW(fine_precision_guard_checks);
    SAME_ROW(fine_precision_fallbacks); SAME_ROW(fine_precision_nonfinite_fallbacks);
    SAME_ROW(fine_precision_near_tie_fallbacks);
    SAME_ROW(fine_precision_interpolation_fallbacks);
    SAME_ROW(conditioned_bins_screened); SAME_ROW(conditioned_bins_rechecked);
    SAME_ROW(total_cpu_ms); SAME_ROW(proposal_ms); SAME_ROW(stage_sum_ms);
    SAME_ROW(proposal_fold_ms); SAME_ROW(proposal_correlation_ms);
    SAME_ROW(proposal_ranking_ms); SAME_ROW(coarse_ms); SAME_ROW(acquisition_ms);
    SAME_ROW(fine_fft_ms); SAME_ROW(conditioned_ms); SAME_ROW(verification_ms);
    SAME_ROW(glrt_ms); SAME_ROW(fractional_epoch_ms);
#undef SAME_ROW
#define SAME_CANDIDATE(name) \
    assert(output.rows[0].candidates[0].name == source.rows[0].candidates[0].name)
    SAME_CANDIDATE(coarse_epoch); SAME_CANDIDATE(coarse_bin);
    SAME_CANDIDATE(refined_epoch); SAME_CANDIDATE(frame_support);
    SAME_CANDIDATE(glrt_complete); SAME_CANDIDATE(conditioned_fallback);
    SAME_CANDIDATE(refinement_skipped); SAME_CANDIDATE(coarse_cfo_hz);
    SAME_CANDIDATE(fine_cfo_hz); SAME_CANDIDATE(conditioned_cfo_hz);
    SAME_CANDIDATE(epoch); SAME_CANDIDATE(acquired_cfo_hz);
    SAME_CANDIDATE(tracking_cfo_hz); SAME_CANDIDATE(exact_score);
    SAME_CANDIDATE(control_score); SAME_CANDIDATE(margin);
    SAME_CANDIDATE(acquire_score); SAME_CANDIDATE(verify_score);
    SAME_CANDIDATE(verify_control_score); SAME_CANDIDATE(conditioned_score);
    SAME_CANDIDATE(coarse_score); SAME_CANDIDATE(fractional_epoch_status);
    SAME_CANDIDATE(fractional_epoch_offset_samples);
    SAME_CANDIDATE(fractional_epoch_log_curvature);
    SAME_CANDIDATE(fractional_exact_score);
    SAME_CANDIDATE(fractional_control_score); SAME_CANDIDATE(fractional_margin);
    SAME_CANDIDATE(fractional_residual_cfo_hz);
    SAME_CANDIDATE(fractional_tracking_cfo_hz);
#undef SAME_CANDIDATE
    for (size_t i = 0; i < 5U; ++i) {
        assert(output.rows[0].candidates[0].fractional_epoch_exact_grid[i] ==
            source.rows[0].candidates[0].fractional_epoch_exact_grid[i]);
        assert(output.rows[0].candidates[0].fractional_epoch_control_grid[i] ==
            source.rows[0].candidates[0].fractional_epoch_control_grid[i]);
    }
    auto malformed = source;
    malformed.row_count = LEO_CORRECTED_PROFILE_MAX_ROWS + 1U;
    output.row_count = 7U;
    assert(leo_corrected_profile_convert_result(&malformed, malformed.row_count,
        &output) == -EPROTO && output.row_count == 0U);
    malformed = source; malformed.rows[0].candidate_count = 9;
    assert(leo_corrected_profile_convert_result(&malformed, 2U, &output) ==
        -EPROTO && output.row_count == 0U);
    malformed = source; malformed.rows[1].receiver_id = 0;
    assert(leo_corrected_profile_convert_result(&malformed, 2U, &output) ==
        -EPROTO && output.row_count == 0U);
    malformed = source; malformed.rows[1].probe_start_ms = 120;
    assert(leo_corrected_profile_convert_result(&malformed, 2U, &output) ==
        -EPROTO && output.row_count == 0U);
}

void compare_candidate(const leo_native_glrt_candidate& a,
                       const leo_corrected_profile_candidate_value& b) {
#define SAME(name) assert(a.name == b.name)
    SAME(coarse_epoch); SAME(coarse_bin); SAME(refined_epoch); SAME(frame_support);
    SAME(glrt_complete); SAME(conditioned_fallback); SAME(refinement_skipped);
    SAME(coarse_cfo_hz); SAME(fine_cfo_hz); SAME(conditioned_cfo_hz); SAME(epoch);
    SAME(acquired_cfo_hz); SAME(tracking_cfo_hz); SAME(exact_score);
    SAME(control_score); SAME(margin); SAME(acquire_score); SAME(verify_score);
    SAME(verify_control_score); SAME(conditioned_score); SAME(coarse_score);
    SAME(fractional_epoch_status); SAME(fractional_epoch_offset_samples);
    SAME(fractional_epoch_log_curvature); SAME(fractional_exact_score);
    SAME(fractional_control_score); SAME(fractional_margin);
    SAME(fractional_residual_cfo_hz); SAME(fractional_tracking_cfo_hz);
#undef SAME
    for (size_t i = 0; i < 5U; ++i) {
        assert(a.fractional_epoch_exact_grid[i] == b.fractional_epoch_exact_grid[i]);
        assert(a.fractional_epoch_control_grid[i] == b.fractional_epoch_control_grid[i]);
    }
}

void real_corrected_closure(const char* exact_path, const char* control_path,
                            const char* iq_path) {
    auto exact = read_values<leo_native_glrt_complex>(exact_path);
    auto control = read_values<leo_native_glrt_complex>(control_path);
    auto iq = read_values<int16_t>(iq_path);
    assert(exact.size() == control.size() && exact.size() == 10000U);
    assert(iq.size() == 4U * 900000U);
    leo_corrected_profile_adapter* adapter = nullptr;
    adapter = reinterpret_cast<leo_corrected_profile_adapter*>(uintptr_t{1});
    assert(leo_corrected_profile_adapter_create(&adapter, 7500000U, exact.data(),
        control.data(), 0U) == -EINVAL && adapter == nullptr);
    adapter = reinterpret_cast<leo_corrected_profile_adapter*>(uintptr_t{1});
    assert(leo_corrected_profile_adapter_create(&adapter, 7500000U, exact.data(),
        control.data(), 9999U) == -EINVAL && adapter == nullptr);
    adapter = reinterpret_cast<leo_corrected_profile_adapter*>(uintptr_t{1});
    assert(leo_corrected_profile_adapter_create(&adapter, 7500000U, exact.data(),
        control.data(), SIZE_MAX) == -EINVAL && adapter == nullptr);
    assert(leo_corrected_profile_adapter_create(nullptr, 7500000U, exact.data(),
        control.data(), exact.size()) == -EINVAL);
    assert(leo_corrected_profile_adapter_create(&adapter, 7500000U, exact.data(),
        control.data(), exact.size()) == 0 && adapter);
    uint8_t configuration_digest[32];
    std::fill(std::begin(configuration_digest), std::end(configuration_digest), 0x31);
    leo_scanner_profile_detector_binding binding{};
    assert(leo_corrected_profile_adapter_binding(adapter, configuration_digest,
        &binding) == 0);
    leo_scanner_profile_capabilities caps{};
    assert(binding.ops.capabilities(binding.ops.context, &caps) == 0);
    assert(caps.abi_version == LEO_SCANNER_PROFILE_ABI_VERSION &&
        caps.sample_rate_hz == 7500000U && caps.receiver_count == 2U &&
        caps.probe_ms == 20U && caps.probe_stride_ms == 120U &&
        caps.process_serialized == 1U && caps.fractional_epoch_mode_available == 1U &&
        caps.fractional_epoch_server_parity_qualified == 0U &&
        caps.coarse_cfo_storage_slots == 22U &&
        caps.peer_fallback_anchor_symbols == 22U &&
        caps.maximum_residual_span_hz == 1600000U);
    leo_scanner_detector_geometry geometry{};
    geometry.abi_version = LEO_SCANNER_PROFILE_ABI_VERSION;
    geometry.sample_rate_hz = 7500000U; geometry.receiver_count = 2U;
    geometry.probe_ms = 20U; geometry.probe_stride_ms = 120U;
    geometry.receiver_center_hz[0] = geometry.receiver_center_hz[1] = -312500.0;
    geometry.residual_cfo_min_hz = -800000.0;
    geometry.residual_cfo_max_hz = 800000.0;
    std::fill(std::begin(geometry.profile_manifest_digest),
        std::end(geometry.profile_manifest_digest), 0x41);
    std::fill(std::begin(geometry.authority_digest),
        std::end(geometry.authority_digest), 0x51);

    leo_native_glrt_result public_result{};
    auto bad = geometry; bad.profile_manifest_digest[0] = 0;
    std::fill(std::begin(bad.profile_manifest_digest),
        std::end(bad.profile_manifest_digest), 0);
    public_result.row_count = 9U;
    assert(binding.ops.analyze(binding.ops.context, &bad, iq.data(), 900000U,
        120U, 120U, &public_result) == -EINVAL && public_result.row_count == 0U);
    assert(binding.ops.analyze(binding.ops.context, &geometry, iq.data(), 899999U,
        120U, 120U, &public_result) == -EINVAL && public_result.row_count == 0U);
    assert(binding.ops.analyze(binding.ops.context, &geometry, iq.data(), 900000U,
        120U, 120U, &public_result) == 0);
    assert(public_result.row_count == 2U);
    for (size_t row = 0; row < 2U; ++row)
        assert(public_result.rows[row].candidate_count == 8);

    std::vector<leo_corrected_profile_complex> neutral_exact(exact.size());
    std::vector<leo_corrected_profile_complex> neutral_control(control.size());
    for (size_t i = 0; i < exact.size(); ++i) {
        neutral_exact[i] = {exact[i].real, exact[i].imaginary};
        neutral_control[i] = {control[i].real, control[i].imaginary};
    }
    leo_corrected_profile_backend* backend = nullptr;
    assert(leo_corrected_profile_backend_create(&backend, 7500000U,
        neutral_exact.data(), neutral_control.data(), neutral_exact.size()) == 0);
    leo_corrected_profile_result_value private_result{};
    assert(leo_corrected_profile_backend_analyze(backend,
        geometry.receiver_center_hz, geometry.residual_cfo_min_hz,
        geometry.residual_cfo_max_hz, iq.data(), 900000U, 120U, 120U,
        &private_result) == 0);
    assert(private_result.row_count == public_result.row_count);
    for (size_t row = 0; row < public_result.row_count; ++row) {
        assert(public_result.rows[row].receiver_id == private_result.rows[row].receiver_id);
        assert(public_result.rows[row].probe_index == private_result.rows[row].probe_index);
        assert(public_result.rows[row].candidate_count == private_result.rows[row].candidate_count);
        for (int candidate = 0; candidate < public_result.rows[row].candidate_count;
             ++candidate)
            compare_candidate(public_result.rows[row].candidates[candidate],
                private_result.rows[row].candidates[candidate]);
    }
    assert(leo_corrected_profile_backend_destroy(backend) == 0);

    std::atomic<bool> go{false};
    int statuses[2]{};
    leo_native_glrt_result concurrent[2]{};
    std::thread threads[2];
    for (size_t i = 0; i < 2U; ++i) threads[i] = std::thread([&, i] {
        while (!go.load(std::memory_order_acquire)) std::this_thread::yield();
        statuses[i] = binding.ops.analyze(binding.ops.context, &geometry, iq.data(),
            900000U, 120U, 120U, &concurrent[i]);
    });
    go.store(true, std::memory_order_release);
    for (auto& thread : threads) thread.join();
    std::sort(std::begin(statuses), std::end(statuses));
    assert(statuses[0] == -EBUSY && statuses[1] == 0);
    assert(leo_corrected_profile_adapter_destroy(adapter) == 0);
}
}  // namespace

int main(int argc, char** argv) {
    conversion_is_explicit_and_fail_closed();
    if (argc == 1) {
        std::cout << "corrected profile adapter conversion tests passed\n";
        return 0;
    }
    assert(argc == 4);
    real_corrected_closure(argv[1], argv[2], argv[3]);
    std::cout << "corrected profile adapter tests passed\n";
}
