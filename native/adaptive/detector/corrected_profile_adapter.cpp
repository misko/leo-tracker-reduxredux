#include "corrected_profile_adapter_internal.h"

#include <atomic>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <new>

struct leo_corrected_profile_adapter {
    leo_corrected_profile_backend* backend{};
    std::atomic_flag busy = ATOMIC_FLAG_INIT;
};

namespace {
bool nonzero(const uint8_t value[32]) {
    uint8_t combined = 0;
    for (size_t i = 0; i < 32U; ++i) combined |= value[i];
    return combined != 0;
}

#define COPY_CANDIDATE_FIELD(name) to.name=from.name
void copy_candidate(leo_native_glrt_candidate& to,
                    const leo_corrected_profile_candidate_value& from) {
    COPY_CANDIDATE_FIELD(coarse_epoch); COPY_CANDIDATE_FIELD(coarse_bin);
    COPY_CANDIDATE_FIELD(refined_epoch); COPY_CANDIDATE_FIELD(frame_support);
    COPY_CANDIDATE_FIELD(glrt_complete); COPY_CANDIDATE_FIELD(conditioned_fallback);
    COPY_CANDIDATE_FIELD(refinement_skipped); COPY_CANDIDATE_FIELD(coarse_cfo_hz);
    COPY_CANDIDATE_FIELD(fine_cfo_hz); COPY_CANDIDATE_FIELD(conditioned_cfo_hz);
    COPY_CANDIDATE_FIELD(epoch); COPY_CANDIDATE_FIELD(acquired_cfo_hz);
    COPY_CANDIDATE_FIELD(tracking_cfo_hz); COPY_CANDIDATE_FIELD(exact_score);
    COPY_CANDIDATE_FIELD(control_score); COPY_CANDIDATE_FIELD(margin);
    COPY_CANDIDATE_FIELD(acquire_score); COPY_CANDIDATE_FIELD(verify_score);
    COPY_CANDIDATE_FIELD(verify_control_score); COPY_CANDIDATE_FIELD(conditioned_score);
    COPY_CANDIDATE_FIELD(coarse_score); COPY_CANDIDATE_FIELD(fractional_epoch_status);
    COPY_CANDIDATE_FIELD(fractional_epoch_offset_samples);
    COPY_CANDIDATE_FIELD(fractional_epoch_log_curvature);
    for (size_t i = 0; i < 5U; ++i) {
        to.fractional_epoch_exact_grid[i] = from.fractional_epoch_exact_grid[i];
        to.fractional_epoch_control_grid[i] = from.fractional_epoch_control_grid[i];
    }
    COPY_CANDIDATE_FIELD(fractional_exact_score);
    COPY_CANDIDATE_FIELD(fractional_control_score);
    COPY_CANDIDATE_FIELD(fractional_margin);
    COPY_CANDIDATE_FIELD(fractional_residual_cfo_hz);
    COPY_CANDIDATE_FIELD(fractional_tracking_cfo_hz);
}
#undef COPY_CANDIDATE_FIELD

#define COPY_ROW_FIELD(name) to.name=from.name
void copy_row(leo_native_glrt_row& to,
              const leo_corrected_profile_row_value& from) {
    COPY_ROW_FIELD(receiver_id); COPY_ROW_FIELD(probe_index);
    COPY_ROW_FIELD(probe_start_ms); COPY_ROW_FIELD(proposal_executed);
    COPY_ROW_FIELD(proposal_tracking_fallback); COPY_ROW_FIELD(proposal_neighbor_matches);
    COPY_ROW_FIELD(candidate_count); COPY_ROW_FIELD(retained_peak_count);
    COPY_ROW_FIELD(coarse_gate_skipped_count); COPY_ROW_FIELD(conditioned_fallback_count);
    COPY_ROW_FIELD(actual_executed_glrt_calls); COPY_ROW_FIELD(glrt_cache_hits);
    COPY_ROW_FIELD(conditioned_cache_hits); COPY_ROW_FIELD(fine_fft_cache_entries);
    COPY_ROW_FIELD(fine_fft_cache_hits); COPY_ROW_FIELD(fine_precision_calls);
    COPY_ROW_FIELD(fine_precision_guard_checks); COPY_ROW_FIELD(fine_precision_fallbacks);
    COPY_ROW_FIELD(fine_precision_nonfinite_fallbacks);
    COPY_ROW_FIELD(fine_precision_near_tie_fallbacks);
    COPY_ROW_FIELD(fine_precision_interpolation_fallbacks);
    COPY_ROW_FIELD(conditioned_bins_screened); COPY_ROW_FIELD(conditioned_bins_rechecked);
    COPY_ROW_FIELD(total_cpu_ms); COPY_ROW_FIELD(proposal_ms); COPY_ROW_FIELD(stage_sum_ms);
    COPY_ROW_FIELD(proposal_fold_ms); COPY_ROW_FIELD(proposal_correlation_ms);
    COPY_ROW_FIELD(proposal_ranking_ms); COPY_ROW_FIELD(coarse_ms);
    COPY_ROW_FIELD(acquisition_ms); COPY_ROW_FIELD(fine_fft_ms);
    COPY_ROW_FIELD(conditioned_ms); COPY_ROW_FIELD(verification_ms);
    COPY_ROW_FIELD(glrt_ms); COPY_ROW_FIELD(fractional_epoch_ms);
    for (int32_t candidate = 0; candidate < from.candidate_count; ++candidate)
        copy_candidate(to.candidates[candidate], from.candidates[candidate]);
}
#undef COPY_ROW_FIELD

int capabilities(void* context, leo_scanner_profile_capabilities* out) {
    if (!context || !out) return -EINVAL;
    *out = {LEO_SCANNER_PROFILE_ABI_VERSION, 7500000U, 2U, 20U, 120U,
        1U, 1U, 0U, 22U, 22U, UINT64_C(1600000)};
    return 0;
}

int analyze(void* context, const leo_scanner_detector_geometry* geometry,
            const int16_t* input, size_t complex_times, uint32_t dwell_ms,
            uint32_t probe_stride_ms, leo_native_glrt_result* result) {
    if (result) *result = {};
    if (!context || !geometry || !input || !result ||
        geometry->abi_version != LEO_SCANNER_PROFILE_ABI_VERSION ||
        geometry->sample_rate_hz != 7500000U || geometry->receiver_count != 2U ||
        geometry->probe_ms != 20U || geometry->probe_stride_ms != 120U ||
        probe_stride_ms != geometry->probe_stride_ms ||
        !std::isfinite(geometry->receiver_center_hz[0]) ||
        !std::isfinite(geometry->receiver_center_hz[1]) ||
        !std::isfinite(geometry->residual_cfo_min_hz) ||
        !std::isfinite(geometry->residual_cfo_max_hz) ||
        geometry->residual_cfo_min_hz >= geometry->residual_cfo_max_hz ||
        geometry->residual_cfo_max_hz - geometry->residual_cfo_min_hz > 1600000.0 ||
        !nonzero(geometry->profile_manifest_digest) ||
        !nonzero(geometry->authority_digest)) return -EINVAL;
    if (dwell_ms != 120U && dwell_ms != 240U && dwell_ms != 360U)
        return -EINVAL;
    size_t expected_times = static_cast<size_t>(geometry->sample_rate_hz) *
        dwell_ms / 1000U;
    size_t expected_rows = 2U * (1U + (dwell_ms - 20U) / probe_stride_ms);
    if (complex_times != expected_times ||
        expected_rows > LEO_NATIVE_GLRT_MAX_ROWS)
        return -EINVAL;
    auto* adapter = static_cast<leo_corrected_profile_adapter*>(context);
    if (adapter->busy.test_and_set(std::memory_order_acquire)) return -EBUSY;
    struct Release {
        std::atomic_flag& value;
        ~Release() { value.clear(std::memory_order_release); }
    } release{adapter->busy};
    leo_corrected_profile_result_value converted{};
    const int status = leo_corrected_profile_backend_analyze(adapter->backend,
        geometry->receiver_center_hz, geometry->residual_cfo_min_hz,
        geometry->residual_cfo_max_hz, input, complex_times, dwell_ms,
        probe_stride_ms, &converted);
    if (status) return status;
    return leo_corrected_profile_convert_result(&converted, expected_rows, result);
}
}  // namespace

int leo_corrected_profile_convert_result(
    const leo_corrected_profile_result_value* from, size_t expected_rows,
    leo_native_glrt_result* to) {
    if (to) *to = {};
    if (!from || !to || from->row_count != expected_rows ||
        from->row_count > LEO_NATIVE_GLRT_MAX_ROWS ||
        !std::isfinite(from->detector_cpu_ms)) return -EPROTO;
    for (size_t row = 0; row < from->row_count; ++row) {
        const auto& value = from->rows[row];
        if (value.receiver_id != static_cast<int32_t>(row % 2U) ||
            value.probe_index != static_cast<int32_t>(row / 2U) ||
            value.probe_start_ms != static_cast<int32_t>(120U * (row / 2U)) ||
            value.candidate_count < 0 ||
            value.candidate_count > LEO_NATIVE_GLRT_MAX_CANDIDATES)
            return -EPROTO;
    }
    to->row_count = from->row_count;
    to->detector_cpu_ms = from->detector_cpu_ms;
    for (size_t row = 0; row < from->row_count; ++row)
        copy_row(to->rows[row], from->rows[row]);
    return 0;
}

extern "C" int leo_corrected_profile_adapter_create(
    leo_corrected_profile_adapter** out, uint32_t sample_rate_hz,
    const leo_native_glrt_complex* exact_template,
    const leo_native_glrt_complex* control_template,
    size_t template_complex_count) {
    if (out) *out = nullptr;
    if (!out || !exact_template || !control_template || sample_rate_hz != 7500000U ||
        template_complex_count != 10000U)
        return -EINVAL;
    auto* value = new (std::nothrow) leo_corrected_profile_adapter;
    if (!value) return -ENOMEM;
    auto* exact = new (std::nothrow) leo_corrected_profile_complex[template_complex_count];
    auto* control = new (std::nothrow) leo_corrected_profile_complex[template_complex_count];
    if (!exact || !control) {
        delete[] control; delete[] exact; delete value; return -ENOMEM;
    }
    for (size_t i = 0; i < template_complex_count; ++i) {
        exact[i] = {exact_template[i].real, exact_template[i].imaginary};
        control[i] = {control_template[i].real, control_template[i].imaginary};
    }
    const int status = leo_corrected_profile_backend_create(&value->backend,
        sample_rate_hz, exact, control, template_complex_count);
    delete[] control; delete[] exact;
    if (status) { delete value; return status; }
    *out = value;
    return 0;
}

extern "C" int leo_corrected_profile_adapter_destroy(
    leo_corrected_profile_adapter* adapter) {
    if (!adapter) return -EINVAL;
    if (adapter->busy.test_and_set(std::memory_order_acquire)) return -EBUSY;
    const int status = leo_corrected_profile_backend_destroy(adapter->backend);
    if (status) {
        adapter->busy.clear(std::memory_order_release);
        return status;
    }
    delete adapter;
    return 0;
}

extern "C" int leo_corrected_profile_adapter_binding(
    leo_corrected_profile_adapter* adapter,
    const uint8_t configuration_digest[32],
    leo_scanner_profile_detector_binding* binding) {
    if (!adapter || !configuration_digest || !binding ||
        !nonzero(configuration_digest)) return -EINVAL;
    *binding = {};
    binding->abi_version = LEO_SCANNER_PROFILE_ABI_VERSION;
    binding->ops = {adapter, analyze, capabilities};
    std::memcpy(binding->configuration_digest, configuration_digest, 32U);
    return 0;
}
