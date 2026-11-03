#include "corrected_profile_bridge.h"

/* This translation unit is compiled with only the frozen corrected detector
 * header on its include path.  Do not include scanner_profile.h or the public
 * native_glrt.h here: those layouts intentionally differ. */
#include <native_glrt_research.h>

#include <errno.h>
#include <stdlib.h>

struct leo_corrected_profile_backend {
    leo_native_glrt *detector;
};

static int status_to_errno(int status)
{
    switch(status){
    case LEO_NATIVE_GLRT_OK:return 0;
    case LEO_NATIVE_GLRT_INVALID:return -EINVAL;
    case LEO_NATIVE_GLRT_NOMEM:return -ENOMEM;
    case LEO_NATIVE_GLRT_BUSY:return -EBUSY;
    case LEO_NATIVE_GLRT_KERNEL:return -EIO;
    default:return -EIO;
    }
}

int leo_corrected_profile_backend_create(leo_corrected_profile_backend **out,
    uint32_t sample_rate_hz,
    const leo_corrected_profile_complex *exact_template,
    const leo_corrected_profile_complex *control_template,
    size_t template_complex_count)
{
    if(out)*out=NULL;
    if(!out||!exact_template||!control_template||sample_rate_hz!=7500000U||
       template_complex_count!=10000U)return -EINVAL;
    leo_native_glrt_capabilities capabilities={0};
    int status=leo_native_glrt_get_capabilities(&capabilities);
    if(status)return status_to_errno(status);
    if(capabilities.abi_version!=LEO_NATIVE_GLRT_ABI_VERSION||
       capabilities.receiver_count!=2U||capabilities.probe_ms!=20U||
       capabilities.process_serialized!=1U||
       capabilities.candidate_cfo_refinement_state_available!=1U||
       capabilities.fractional_epoch_mode_available!=1U||
       capabilities.deployed_server_interval_fractional_mode_available!=1U)
        return -ENOTSUP;
    leo_corrected_profile_backend *value=calloc(1,sizeof(*value));
    if(!value)return -ENOMEM;
    /* The neutral complex pair has the same value representation, but keep
     * the private ABI boundary explicit rather than aliasing caller storage. */
    leo_native_glrt_complex *exact=calloc(template_complex_count,sizeof(*exact));
    leo_native_glrt_complex *control=calloc(template_complex_count,sizeof(*control));
    if(!exact||!control){free(control);free(exact);free(value);return -ENOMEM;}
    for(size_t i=0;i<template_complex_count;++i){
        exact[i].real=exact_template[i].real;
        exact[i].imaginary=exact_template[i].imaginary;
        control[i].real=control_template[i].real;
        control[i].imaginary=control_template[i].imaginary;
    }
    status=leo_native_glrt_create_with_mode(&value->detector,sample_rate_hz,
        exact,control,template_complex_count,
        LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_INTERVAL_FRACTIONAL);
    free(control);free(exact);
    if(status){free(value);return status_to_errno(status);}
    *out=value;
    return 0;
}

int leo_corrected_profile_backend_destroy(leo_corrected_profile_backend *backend)
{
    if(!backend)return -EINVAL;
    int status=leo_native_glrt_destroy(backend->detector);
    if(status)return status_to_errno(status);
    free(backend);
    return 0;
}

#define COPY_CANDIDATE_FIELD(name) to->name=from->name
static void copy_candidate(leo_corrected_profile_candidate_value *to,
    const leo_native_glrt_candidate *from)
{
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
    for(int i=0;i<5;++i){
        to->fractional_epoch_exact_grid[i]=from->fractional_epoch_exact_grid[i];
        to->fractional_epoch_control_grid[i]=from->fractional_epoch_control_grid[i];
    }
    COPY_CANDIDATE_FIELD(fractional_exact_score);
    COPY_CANDIDATE_FIELD(fractional_control_score);
    COPY_CANDIDATE_FIELD(fractional_margin);
    COPY_CANDIDATE_FIELD(fractional_residual_cfo_hz);
    COPY_CANDIDATE_FIELD(fractional_tracking_cfo_hz);
}
#undef COPY_CANDIDATE_FIELD

#define COPY_ROW_FIELD(name) to->name=from->name
static void copy_row(leo_corrected_profile_row_value *to,
    const leo_native_glrt_row *from)
{
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
    for(int i=0;i<from->candidate_count;++i)copy_candidate(&to->candidates[i],
        &from->candidates[i]);
}
#undef COPY_ROW_FIELD

int leo_corrected_profile_backend_analyze(leo_corrected_profile_backend *backend,
    const double receiver_center_hz[2], double residual_cfo_min_hz,
    double residual_cfo_max_hz, const int16_t *dual_rx_iqiq,
    size_t complex_times, uint32_t dwell_ms, uint32_t probe_stride_ms,
    leo_corrected_profile_result_value *result)
{
    if(!backend||!receiver_center_hz||!dual_rx_iqiq||!result)return -EINVAL;
    *result=(leo_corrected_profile_result_value){0};
    size_t expected_times=0,expected_rows=0;
    int status=leo_native_glrt_layout(7500000U,dwell_ms,probe_stride_ms,
        &expected_times,&expected_rows);
    if(status||expected_times!=complex_times||
       expected_rows>LEO_CORRECTED_PROFILE_MAX_ROWS)return -EINVAL;
    status=leo_native_glrt_set_server_reference_geometry(backend->detector,
        receiver_center_hz,residual_cfo_min_hz,residual_cfo_max_hz);
    if(status)return status_to_errno(status);
    leo_native_glrt_result private_result={0};
    status=leo_native_glrt_analyze(backend->detector,dual_rx_iqiq,complex_times,
        dwell_ms,probe_stride_ms,&private_result);
    if(status)return status_to_errno(status);
    if(private_result.row_count!=expected_rows||
       private_result.row_count>LEO_CORRECTED_PROFILE_MAX_ROWS)return -EPROTO;
    for(size_t row=0;row<private_result.row_count;++row){
        const leo_native_glrt_row *value=&private_result.rows[row];
        if(value->receiver_id!=(int32_t)(row%2U)||
           value->probe_index!=(int32_t)(row/2U)||
           value->probe_start_ms!=(int32_t)(probe_stride_ms*(row/2U))||
           value->candidate_count<0||
           value->candidate_count>LEO_CORRECTED_PROFILE_MAX_CANDIDATES)
            return -EPROTO;
    }
    result->row_count=private_result.row_count;
    result->detector_cpu_ms=private_result.detector_cpu_ms;
    for(size_t row=0;row<private_result.row_count;++row)
        copy_row(&result->rows[row],&private_result.rows[row]);
    return 0;
}
