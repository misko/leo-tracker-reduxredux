from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis.standard.native_glrt_epoch import (
    build_standard_native_glrt_epoch_tracking_v1,
    build_standard_native_glrt_epoch_tracking_v2,
    render_standard_native_glrt_epoch_rate_png,
    render_standard_native_glrt_epoch_timing_png,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV2
from leo.contracts.standard_native_glrt_epoch import (
    StandardNativeGlrtEpochTrackingV1,
    StandardNativeGlrtEpochTrackingV2,
)
from leo.contracts.standard_native_glrt_fractional import (
    FRACTIONAL_GLRT_EPOCH_OFFSETS_V1,
    NativeGlrtFractionalEpochRefinementV1,
    StandardNativeGlrtFractionalEpochV1,
)
from leo.contracts.standard_pipeline import StreamTimingEvidenceV1
from leo.contracts.states import StarlinkEdge
from leo.contracts.validity import ContinuitySegmentV1

_DIGEST = canonical_digest({"fixture": "glrt-epoch-tracking"})
_RF_REFERENCE_HZ = 9_750_000_000 + 1_709_687_500


def _source(sample_rate_hz: int, duration_s: int = 8) -> StandardNativeSourceV2:
    samples = sample_rate_hz * duration_s
    return StandardNativeSourceV2(
        session_id="session-epoch",
        stream_id="stream-0",
        radio_id="radio-0",
        receiver_id=1,
        manifest_digest=_DIGEST,
        synchronization_inventory_digest=_DIGEST,
        path_input_binding_digest=_DIGEST,
        validity_inventory_digest=_DIGEST,
        tuned_center_frequency_hz=1_709_687_500,
        sample_rate_hz=sample_rate_hz,
        logical_sample_count=samples,
        observed_sample_count=samples,
        missing_sample_count=0,
        timing=StreamTimingEvidenceV1(
            first_estimate_utc_ns=1_000_000_000,
            first_earliest_utc_ns=999_999_999,
            first_latest_utc_ns=1_000_000_001,
            last_estimate_utc_ns=9_000_000_000,
            last_earliest_utc_ns=8_999_999_999,
            last_latest_utc_ns=9_000_000_001,
        ),
        continuity_segments=(
            ContinuitySegmentV1(
                segment_index=0,
                device_sample_start=0,
                device_sample_stop=samples,
                stored_sample_start=0,
                stored_sample_stop=samples,
            ),
        ),
    )


def _window(
    opportunity_index: int,
    time_s: float,
    *,
    sample_rate_hz: int,
    drift_s_s: float,
    curvature_s_s2: float,
    cfo_outlier: bool = False,
    epoch_outlier_s: float = 0.0,
) -> SimpleNamespace:
    phase_s = 0.00031 + drift_s_s * time_s + 0.5 * curvature_s_s2 * time_s**2 + epoch_outlier_s
    frame_index = round(time_s * 750)
    exact_epoch_sample = frame_index * sample_rate_hz / 750 + phase_s * sample_rate_hz
    epoch_sample = round(exact_epoch_sample)
    fractional_offset_samples = exact_epoch_sample - epoch_sample
    cfo_hz = 48_000.0 - 2_550.0 * time_s - 18.0 * time_s**2
    if cfo_outlier:
        cfo_hz += 40_000.0
    return SimpleNamespace(
        opportunity_index=opportunity_index,
        global_center_time_s=time_s,
        global_epoch_device_sample=epoch_sample,
        fractional_epoch_offset_samples=fractional_offset_samples,
        passed_margin_gate=True,
        continuity_segment_index=0,
        acquired_cfo_hz=cfo_hz,
        glrt_exact_score=float(np.exp(-(fractional_offset_samples**2))),
        tracking_cfo_hz=cfo_hz,
    )


def _glrt(
    *,
    sample_rate_hz: int = 2_500_000,
    gap: bool = False,
) -> SimpleNamespace:
    expected_rate_hz_s = -2_550.0
    curvature_s_s2 = -expected_rate_hz_s / _RF_REFERENCE_HZ
    times = (
        np.concatenate((np.arange(0.1, 1.1, 0.01), np.arange(4.0, 5.0, 0.01)))
        if gap
        else np.arange(0.1, 6.1, 0.01)
    )
    windows = tuple(
        _window(
            index,
            float(time_s),
            sample_rate_hz=sample_rate_hz,
            drift_s_s=10.5e-6,
            curvature_s_s2=curvature_s_s2,
            cfo_outlier=index in {31, 207},
            epoch_outlier_s=120e-6 if index == 333 else 0.0,
        )
        for index, time_s in enumerate(times)
    )
    track = SimpleNamespace(
        track_label="H1",
        observations=tuple(
            SimpleNamespace(
                opportunity_index=item.opportunity_index,
                raw_cfo_hz=(
                    item.tracking_cfo_hz + (2_500_000 / 11 if index >= len(windows) // 2 else 0)
                ),
                alias_index=1 if index >= len(windows) // 2 else 0,
            )
            for index, item in enumerate(windows)
        ),
    )
    source = _source(sample_rate_hz)
    segment = SimpleNamespace(
        continuity_segment=source.continuity_segments[0],
        windows=windows,
        hough=SimpleNamespace(tracks=(track,)),
    )
    return SimpleNamespace(
        source=source,
        result_digest=_DIGEST,
        starlink_edge=StarlinkEdge.UPPER,
        segments=(segment,),
    )


def _fractional(glrt: SimpleNamespace) -> StandardNativeGlrtFractionalEpochV1:
    refinements = []
    for segment in glrt.segments:
        for window in segment.windows:
            offset = window.fractional_epoch_offset_samples
            scores = tuple(
                float(np.exp(-((grid_offset - offset) ** 2)))
                for grid_offset in FRACTIONAL_GLRT_EPOCH_OFFSETS_V1
            )
            values = {
                "opportunity_index": window.opportunity_index,
                "continuity_segment_index": window.continuity_segment_index,
                "integer_global_epoch_device_sample": window.global_epoch_device_sample,
                "acquired_cfo_hz": window.acquired_cfo_hz,
                "integer_exact_score": scores[2],
                "status": "complete",
                "exact_score_grid": scores,
                "fractional_epoch_offset_samples": offset,
                "fractional_global_epoch_device_sample": (
                    window.global_epoch_device_sample + offset
                ),
            }
            refinements.append(
                NativeGlrtFractionalEpochRefinementV1.model_validate(
                    {
                        **values,
                        "refinement_digest": canonical_digest({"schema_version": 1, **values}),
                    }
                )
            )
    values = {
        "source": glrt.source.model_dump(mode="json"),
        "source_glrt_product_digest": _DIGEST,
        "source_glrt_result_digest": glrt.result_digest,
        "configuration_digest": _DIGEST,
        "starlink_edge": glrt.starlink_edge.value,
        "score_grid_offsets_samples": FRACTIONAL_GLRT_EPOCH_OFFSETS_V1,
        "refinement_count": len(refinements),
        "complete_count": len(refinements),
        "unbracketed_count": 0,
        "unavailable_count": 0,
        "refinements": tuple(item.model_dump(mode="json") for item in refinements),
        "limitations": ("synthetic fractional GLRT fixture",),
        "native_evidence_only": True,
        "current_eligible": False,
        "candidate_only": True,
    }
    document = {
        "schema_version": 1,
        "algorithm_version": "standard-native-glrt-fractional-epoch-v1",
        "score_definition": "conditioned-exact-glrt64-at-fixed-acquired-cfo",
        "interpolation_method": "three-cell-log-parabola-v1",
        "selection_policy": "persisted-margin-pass-windows-only",
        **values,
    }
    return StandardNativeGlrtFractionalEpochV1.model_validate(
        {**document, "result_digest": canonical_digest(document)}
    )


@pytest.mark.parametrize(
    "sample_rate_hz",
    (2_500_000, 3_000_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000, 25_000_000),
)
def test_epoch_fit_is_sample_rate_aware_and_cfo_selected(sample_rate_hz: int) -> None:
    glrt = _glrt(sample_rate_hz=sample_rate_hz)
    result = build_standard_native_glrt_epoch_tracking_v1(
        glrt,  # type: ignore[arg-type]
        source_glrt_product_digest=_DIGEST,
    )

    assert result.source.sample_rate_hz == sample_rate_hz
    assert result.source_glrt_product_digest == result.source_glrt_result_digest == _DIGEST
    assert result.rf_reference_hz == _RF_REFERENCE_HZ
    assert result.cfo_alias_spacing_hz == pytest.approx(2_500_000 / 11)
    assert result.rf_reference_provenance == "documented_lnb_lo_plus_tuned_if_center"
    assert result.cfo_selection_uses_epoch is False
    assert len(result.locklets) == 1
    locklet = result.locklets[0]
    assert locklet.status.value == "complete"
    assert locklet.cfo_selection.selected_count == len(locklet.observations) - 2
    assert locklet.quadratic_fit is not None
    assert locklet.linear_fit is not None
    assert locklet.quadratic_fit.equivalent_doppler_rate_hz_s == pytest.approx(-2_550.0, abs=100.0)
    assert locklet.quadratic_fit.residual_rms_s < locklet.linear_fit.residual_rms_s
    assert locklet.quadratic_fit.formal_equivalent_doppler_rate_sigma_hz_s < 500.0
    assert not locklet.observations[31].cfo_branch_inlier
    assert not locklet.observations[207].cfo_branch_inlier
    assert not locklet.observations[333].epoch_fit_inlier
    assert locklet.observations[-1].hough_alias_index == 1
    assert locklet.observations[-1].canonical_cfo_hz == pytest.approx(
        glrt.segments[0].windows[-1].tracking_cfo_hz
    )


def test_epoch_fit_splits_a_detection_gap_without_crossing_it() -> None:
    result = build_standard_native_glrt_epoch_tracking_v1(
        _glrt(gap=True),  # type: ignore[arg-type]
        source_glrt_product_digest=_DIGEST,
    )

    assert len(result.locklets) == 2
    assert [item.locklet_index for item in result.locklets] == [0, 1]
    assert result.locklets[0].global_end_time_s < 2.0
    assert result.locklets[1].global_start_time_s > 3.0
    assert all(item.continuity_segment_index == 0 for item in result.locklets)
    assert result.cross_continuity_fit_permitted is False


@pytest.mark.parametrize(
    "sample_rate_hz",
    (2_500_000, 3_000_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000, 25_000_000),
)
def test_fractional_epoch_v2_removes_integer_sample_quantization(sample_rate_hz: int) -> None:
    glrt = _glrt(sample_rate_hz=sample_rate_hz)
    integer = build_standard_native_glrt_epoch_tracking_v1(
        glrt,  # type: ignore[arg-type]
        source_glrt_product_digest=_DIGEST,
    )
    fractional = build_standard_native_glrt_epoch_tracking_v2(
        glrt,  # type: ignore[arg-type]
        _fractional(glrt),
        source_glrt_product_digest=_DIGEST,
        source_fractional_epoch_product_digest=_DIGEST,
    )

    assert isinstance(fractional, StandardNativeGlrtEpochTrackingV2)
    assert len(fractional.locklets) == 1
    integer_fit = integer.locklets[0].quadratic_fit
    fractional_fit = fractional.locklets[0].quadratic_fit
    assert integer_fit is not None and fractional_fit is not None
    assert fractional_fit.residual_rms_s < integer_fit.residual_rms_s / 10
    assert fractional_fit.equivalent_doppler_rate_hz_s == pytest.approx(-2_550.0, abs=1e-3)
    assert fractional.locklets[0].observations[0].fractional_epoch_offset_samples != 0.0
    assert render_standard_native_glrt_epoch_timing_png(
        fractional, path_label="radio-0 · RX1"
    ).startswith(b"\x89PNG\r\n\x1a\n")


def test_epoch_artifacts_are_deterministic_and_contract_digest_rejects_tamper() -> None:
    result = build_standard_native_glrt_epoch_tracking_v1(
        _glrt(),  # type: ignore[arg-type]
        source_glrt_product_digest=_DIGEST,
    )

    timing = render_standard_native_glrt_epoch_timing_png(result, path_label="radio-0 · RX1")
    rate = render_standard_native_glrt_epoch_rate_png(result, path_label="radio-0 · RX1")
    assert timing.startswith(b"\x89PNG\r\n\x1a\n")
    assert rate.startswith(b"\x89PNG\r\n\x1a\n")
    assert (
        render_standard_native_glrt_epoch_timing_png(result, path_label="radio-0 · RX1") == timing
    )
    assert render_standard_native_glrt_epoch_rate_png(result, path_label="radio-0 · RX1") == rate

    tampered = result.model_dump(mode="json")
    tampered["rf_reference_hz"] += 1
    with pytest.raises(ValidationError, match="equivalent Doppler"):
        StandardNativeGlrtEpochTrackingV1.model_validate(tampered)
    tampered = result.model_dump(mode="json")
    tampered["limitations"].append("tampered limitation")
    with pytest.raises(ValidationError, match="result digest"):
        StandardNativeGlrtEpochTrackingV1.model_validate(tampered)
