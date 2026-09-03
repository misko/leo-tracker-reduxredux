from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import numpy as np
import pytest

from leo.analysis.qam.pilot import PilotQamMetrics, PilotQamResult
from leo.analysis.standard.native_qam import (
    NativePrimaryQamCapture,
    build_native_qam_probe_evidence,
    merge_native_qam_sufficient_statistics,
    native_qam_sufficient_statistics,
)
from leo.analysis.starlink.acquisition import (
    NumericalStatus,
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.pilot_methods import PilotProbeDetection, detect_pilot_method_candidates
from leo.analysis.starlink.templates import StarlinkEdge, qin_edge_pilot_frame
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import (
    NativeProbeWindowV3,
    NativeWindowDisposition,
    NativeWindowEvidenceV1,
)
from leo.contracts.standard_pipeline import ProbeWindowV2


def _qam_result(frames: np.ndarray) -> PilotQamResult:
    expected = np.exp(0.5j * np.pi * (np.arange(300 * 8) % 4 + 0.5)).reshape(300, 8)
    equalized = expected.copy()
    equalized[0, 0] *= -1
    error = equalized - expected
    return PilotQamResult(
        status=NumericalStatus.COMPLETE,
        metrics=PilotQamMetrics(
            hard_symbol_accuracy=(300 * 8 - 1) / (300 * 8),
            rms_evm=float(np.sqrt(np.mean(np.abs(error) ** 2))),
            noise_variance=1e-6,
            soft_mean_confidence=1.0,
            soft_mean_expected_probability=1.0,
            frame_count=frames.shape[0],
            effective_frame_count=float(frames.shape[0]),
        ),
        absolute_cfo_hz=0.0,
        residual_cfo_refinement_hz=0.0,
        reason="test same-call primary QAM",
        expected=expected,
        equalized=equalized,
        frame_equalized=frames,
    )


def _frames(count: int) -> np.ndarray:
    expected = np.exp(0.5j * np.pi * (np.arange(300 * 8) % 4 + 0.5)).reshape(300, 8)
    frames = np.broadcast_to(expected, (count, 300, 8)).copy()
    for index in range(count):
        frames[index, index, 0] *= -1
    return frames


def _opportunity(disposition: NativeWindowDisposition) -> NativeProbeWindowV3:
    validity = NativeWindowEvidenceV1(
        device_sample_start=100,
        sample_count=50_000,
        disposition=disposition,
        missing_sample_count=(1 if disposition is NativeWindowDisposition.GAP_OVERLAP else 0),
        continuity_segment_index=(0 if disposition is NativeWindowDisposition.VALID else None),
    )
    return NativeProbeWindowV3(
        probe=ProbeWindowV2(
            probe_id=canonical_digest({"probe": 0}),
            coarse_window_index=0,
            subwindow_index=0,
            probe_offset_ms=0,
            sample_start=100,
            sample_count=50_000,
            time_s=100 / 2_500_000,
        ),
        validity=validity,
    )


def test_qam_statistics_count_frames_and_symbols_without_averaging_ratios() -> None:
    statistics = native_qam_sufficient_statistics(_qam_result(_frames(3)))

    assert statistics.qam_result_count == 1
    assert statistics.frame_count == 3
    assert statistics.symbol_count == 300 * 8
    assert statistics.correct_symbol_count == statistics.symbol_count - 1
    assert statistics.hard_symbol_accuracy == (
        Decimal(statistics.correct_symbol_count) / Decimal(statistics.symbol_count)
    )
    assert statistics.rms_evm is not None
    assert statistics.reference_energy_sum > 0
    assert statistics.invalid_device_axis_samples_included is False


def test_qam_merge_is_partition_and_order_invariant() -> None:
    left = native_qam_sufficient_statistics(_qam_result(_frames(1)))
    right = native_qam_sufficient_statistics(_qam_result(_frames(2)))

    merged = merge_native_qam_sufficient_statistics((left, right))
    reversed_merge = merge_native_qam_sufficient_statistics((right, left))
    repartitioned = merge_native_qam_sufficient_statistics(
        (
            merge_native_qam_sufficient_statistics((left,)),
            merge_native_qam_sufficient_statistics((right,)),
        )
    )

    assert merged == reversed_merge == repartitioned
    assert merged.qam_result_count == 2
    assert merged.frame_count == 3
    assert merged.symbol_count == 2 * 300 * 8
    assert merged.hard_symbol_accuracy == (
        Decimal(merged.correct_symbol_count) / Decimal(merged.symbol_count)
    )


def test_noncomplete_qam_is_empty_and_invalid_probe_zeros_are_never_admitted() -> None:
    no_result = PilotQamResult(
        status=NumericalStatus.NO_RESULT,
        metrics=None,
        absolute_cfo_hz=None,
        residual_cfo_refinement_hz=None,
        reason="no primary QAM result",
    )
    statistics = native_qam_sufficient_statistics(no_result)
    assert statistics.qam_result_count == statistics.symbol_count == statistics.frame_count == 0

    detection = PilotProbeDetection(
        NumericalStatus.COMPLETE,
        100,
        100 / 2_500_000,
        1,
        0.0,
        (),
        None,
        None,
        "test candidate",
    )
    with pytest.raises(ValueError, match="wholly-valid"):
        build_native_qam_probe_evidence(
            opportunity_index=0,
            opportunity=_opportunity(NativeWindowDisposition.GAP_OVERLAP),
            continuity_segment_device_sample_start=0,
            detection=detection,
            qam_result=no_result,
        )


def test_probe_evidence_preserves_candidate_but_nulls_noncomplete_qam() -> None:
    detection = PilotProbeDetection(
        NumericalStatus.COMPLETE,
        100,
        100 / 2_500_000,
        1,
        0.0,
        (),
        None,
        None,
        "test candidate with no QAM result",
    )
    no_result = PilotQamResult(
        status=NumericalStatus.NO_RESULT,
        metrics=None,
        absolute_cfo_hz=None,
        residual_cfo_refinement_hz=None,
        reason="no primary QAM result",
    )

    evidence = build_native_qam_probe_evidence(
        opportunity_index=0,
        opportunity=_opportunity(NativeWindowDisposition.VALID),
        continuity_segment_device_sample_start=0,
        detection=detection,
        qam_result=no_result,
    )

    assert evidence.detection_status == "complete"
    assert evidence.primary_candidate_rank == 0
    assert evidence.primary_local_epoch_sample == 1
    assert evidence.primary_acquired_cfo_hz == 0.0
    assert evidence.qam_status.value == "no_result"
    assert evidence.qam_absolute_cfo_hz is None
    assert evidence.qam_residual_cfo_refinement_hz is None
    assert evidence.statistics.qam_result_count == 0


def test_probe_evidence_rejects_same_call_qam_cfo_tamper() -> None:
    qam_result = _qam_result(_frames(1))
    assert qam_result.metrics is not None
    detection = PilotProbeDetection(
        NumericalStatus.COMPLETE,
        100,
        100 / 2_500_000,
        1,
        0.0,
        (),
        qam_result.metrics.hard_symbol_accuracy,
        qam_result.metrics.rms_evm,
        "test candidate",
    )
    qam_result = replace(qam_result, absolute_cfo_hz=1.0)

    with pytest.raises(ValueError, match="primary CFO plus refinement"):
        build_native_qam_probe_evidence(
            opportunity_index=0,
            opportunity=_opportunity(NativeWindowDisposition.VALID),
            continuity_segment_device_sample_start=0,
            detection=detection,
            qam_result=qam_result,
        )


def test_primary_qam_observer_preserves_legacy_detection_output() -> None:
    sample_rate_hz = 2_500_000
    samples = np.tile(qin_edge_pilot_frame(sample_rate_hz, StarlinkEdge.LOWER), 20)[:50_000]
    calibration = ReceiverFrequencyCalibration("rx", 0.0, "1" * 64)
    acquisition = SymbolwiseAcquisitionConfig(maximum_probe_samples=50_000)
    baseline = detect_pilot_method_candidates(
        samples,
        sample_rate_hz,
        sample_start=0,
        calibration=calibration,
        acquisition_config=acquisition,
        maximum_scored_candidates=2,
        edge=StarlinkEdge.LOWER,
    )
    capture = NativePrimaryQamCapture()
    observed = detect_pilot_method_candidates(
        samples,
        sample_rate_hz,
        sample_start=0,
        calibration=calibration,
        acquisition_config=acquisition,
        maximum_scored_candidates=2,
        edge=StarlinkEdge.LOWER,
        primary_qam_observer=capture,
    )

    assert observed == baseline
    assert capture.result is not None
    assert capture.result.metrics is not None
    assert observed.fractional_epoch_status != "not_evaluated"
    assert observed.qam_accuracy == capture.result.metrics.hard_symbol_accuracy
    assert observed.qam_evm == capture.result.metrics.rms_evm
    captured_statistics = native_qam_sufficient_statistics(capture.result)
    assert captured_statistics.hard_symbol_accuracy is not None
    assert captured_statistics.rms_evm is not None
    assert float(captured_statistics.hard_symbol_accuracy) == pytest.approx(
        capture.result.metrics.hard_symbol_accuracy,
        abs=1e-15,
    )
    assert float(captured_statistics.rms_evm) == pytest.approx(
        capture.result.metrics.rms_evm,
        rel=1e-6,
        abs=1e-12,
    )

    with pytest.raises(ValueError, match="more than once"):
        capture(replace(capture.result, reason="unexpected duplicate"))
