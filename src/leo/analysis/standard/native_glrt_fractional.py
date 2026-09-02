"""Additive all-candidate fractional GLRT evidence for Standard-native paths."""

from __future__ import annotations

import math

from leo.analysis.standard.native_stateful import StandardNativeStatefulResult
from leo.analysis.starlink.pilot_methods import PilotMethod
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import StandardProbeScheduleV4
from leo.contracts.standard_native_glrt_fractional import (
    FRACTIONAL_GLRT_EPOCH_OFFSETS_V1,
    NativeGlrtFractionalEpochStatusV1,
    NativeStatefulGlrtFractionalEpochRefinementV1,
    StandardNativeGlrtFractionalEpochV1,
    StandardNativeGlrtFractionalEpochV2,
)
from leo.contracts.standard_native_stateful_v2 import StandardNativeStatefulPathV3


def build_standard_native_glrt_fractional_epoch_v2(
    *,
    stateful_result: StandardNativeStatefulResult,
    stateful_path: StandardNativeStatefulPathV3,
    stateful_path_product_digest: str,
    probe_schedule: StandardProbeScheduleV4,
    full_capture_fractional: StandardNativeGlrtFractionalEpochV1,
    full_capture_fractional_product_digest: str,
) -> StandardNativeGlrtFractionalEpochV2:
    """Seal every retained stateful GLRT basin without changing V1 products."""

    source = stateful_path.source
    if (
        stateful_result.path_input_binding_digest != source.path_input_binding_digest
        or stateful_result.validity_inventory_digest != source.validity_inventory_digest
        or stateful_result.sample_rate_hz != source.sample_rate_hz
        or full_capture_fractional.source != source
        or full_capture_fractional.starlink_edge != stateful_path.starlink_edge
    ):
        raise ValueError("fractional GLRT V2 sources do not close")

    opportunity_by_start = {
        item.probe.sample_start: (index, item)
        for index, item in enumerate(probe_schedule.opportunities)
    }
    refinements: list[NativeStatefulGlrtFractionalEpochRefinementV1] = []
    for segment_result in stateful_result.segments:
        science = segment_result.local_science
        if science is None:
            continue
        for detection in science.detections:
            global_probe_start = segment_result.device_sample_start + detection.sample_start
            resolved = opportunity_by_start.get(global_probe_start)
            if resolved is None:
                raise ValueError("stateful fractional GLRT detection escaped probe schedule")
            opportunity_index, opportunity = resolved
            if (
                opportunity.validity.continuity_segment_index
                != segment_result.continuity_segment_index
            ):
                raise ValueError("stateful fractional GLRT segment mapping changed")
            for candidate in detection.candidates:
                fractional = candidate.fractional_epoch
                if fractional is None:
                    raise ValueError("retained GLRT candidate lacks fractional refinement")
                integer_glrt = next(
                    (score for score in candidate.scores if score.method is PilotMethod.GLRT64),
                    None,
                )
                if (
                    integer_glrt is None
                    or not math.isclose(
                        fractional.exact_score_grid[len(FRACTIONAL_GLRT_EPOCH_OFFSETS_V1) // 2],
                        integer_glrt.exact_score,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                    or not math.isclose(
                        fractional.control_score_grid[len(FRACTIONAL_GLRT_EPOCH_OFFSETS_V1) // 2],
                        float(integer_glrt.control_score or 0.0),
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                ):
                    raise ValueError("fractional GLRT center changed its integer candidate")
                offset = fractional.fractional_epoch_offset_samples
                phase = fractional.fractional_frame_phase_sample
                complete = offset is not None and phase is not None
                refinement_values = {
                    "opportunity_index": opportunity_index,
                    "continuity_segment_index": segment_result.continuity_segment_index,
                    "candidate_rank": candidate.rank,
                    "integer_global_epoch_device_sample": (
                        global_probe_start + candidate.local_epoch_sample
                    ),
                    "integer_frame_phase_sample": candidate.local_epoch_sample,
                    "frame_period_samples": fractional.frame_period_samples,
                    "acquired_cfo_hz": candidate.acquired_cfo_hz,
                    "status": (
                        NativeGlrtFractionalEpochStatusV1.COMPLETE.value
                        if complete
                        else NativeGlrtFractionalEpochStatusV1.UNBRACKETED.value
                    ),
                    "wrapped_epoch_samples": fractional.wrapped_epoch_samples,
                    "exact_score_grid": fractional.exact_score_grid,
                    "control_score_grid": fractional.control_score_grid,
                    "fractional_epoch_offset_samples": offset,
                    "fractional_frame_phase_sample": phase,
                    "first_supported_global_epoch_device_sample": (
                        None if phase is None else global_probe_start + phase
                    ),
                    "log_curvature": fractional.log_curvature,
                    "fractional_exact_score": fractional.fractional_exact_score,
                    "fractional_control_score": fractional.fractional_control_score,
                }
                refinements.append(
                    NativeStatefulGlrtFractionalEpochRefinementV1.model_validate(
                        {
                            **refinement_values,
                            "refinement_digest": canonical_digest(
                                {"schema_version": 1, **refinement_values}
                            ),
                        }
                    )
                )
    ordered = tuple(
        sorted(refinements, key=lambda item: (item.opportunity_index, item.candidate_rank))
    )
    statuses = tuple(item.status for item in ordered)
    values = {
        "algorithm_version": "standard-native-glrt-fractional-epoch-v2",
        "source": source.model_dump(mode="json"),
        "source_full_capture_fractional_product_digest": (full_capture_fractional_product_digest),
        "source_full_capture_fractional_result_digest": (full_capture_fractional.result_digest),
        "source_stateful_path_product_digest": stateful_path_product_digest,
        "source_stateful_path_digest": stateful_path.stateful_path_digest,
        "configuration_digest": canonical_digest(
            {
                "algorithm_version": "standard-native-glrt-fractional-epoch-v2",
                "stateful_science_configuration_digest": (
                    stateful_path.science_configuration_digest
                ),
                "full_capture_fractional_configuration_digest": (
                    full_capture_fractional.configuration_digest
                ),
                "score_grid_offsets_samples": FRACTIONAL_GLRT_EPOCH_OFFSETS_V1,
                "interpolator": "normalized-lanczos16-v1",
            }
        ),
        "starlink_edge": stateful_path.starlink_edge.value,
        "score_definition": ("conditioned-exact-and-control-glrt64-at-fixed-acquired-cfo"),
        "interpolation_method": ("circular-five-cell-log-parabola-plus-lanczos16-v1"),
        "selection_policy": "all-retained-stateful-candidates",
        "score_grid_offsets_samples": FRACTIONAL_GLRT_EPOCH_OFFSETS_V1,
        "opportunity_count": len({item.opportunity_index for item in ordered}),
        "candidate_refinement_count": len(ordered),
        "complete_count": statuses.count(NativeGlrtFractionalEpochStatusV1.COMPLETE),
        "unbracketed_count": statuses.count(NativeGlrtFractionalEpochStatusV1.UNBRACKETED),
        "refinements": tuple(item.model_dump(mode="json") for item in ordered),
        "limitations": (
            "Integer acquisition, ranking, exact-minus-control gates, and candidate identity "
            "remain unchanged.",
            "Every retained stateful candidate is refined independently at its fixed CFO and "
            "edge hypothesis.",
            "The continuous exact/control scores use normalized 16-tap Lanczos IQ "
            "interpolation; they do not replace integer decision scores.",
            "A fractional timing basin remains candidate evidence and does not establish "
            "Starlink or satellite identity.",
        ),
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
    }
    return StandardNativeGlrtFractionalEpochV2.model_validate(
        {**values, "result_digest": canonical_digest({"schema_version": 2, **values})}
    )
