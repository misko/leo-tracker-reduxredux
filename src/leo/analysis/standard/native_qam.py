"""Validity-bound QAM sufficient statistics for Standard-native.

This module consumes the exact :class:`PilotQamResult` produced while scoring
the primary acquisition candidate.  It never re-runs QAM and never receives IQ;
the caller must bind the result to a probe already admitted as wholly valid.
"""

from __future__ import annotations

import math
from decimal import Decimal, localcontext

import numpy as np

from leo.analysis.qam.pilot import PilotQamResult
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import PilotProbeDetection
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import NativeProbeWindowV3, NativeWindowDisposition
from leo.contracts.standard_native_path_report import (
    NativeQamComputationStatusV1,
    NativeQamProbeEvidenceV1,
    NativeQamSufficientStatisticsV1,
)

_QIN_SHAPE = (300, 8)


class NativePrimaryQamCapture:
    """Single-use observer for the primary QAM call inside one probe detector."""

    def __init__(self) -> None:
        self._result: PilotQamResult | None = None

    def __call__(self, result: PilotQamResult) -> None:
        if self._result is not None:
            raise ValueError("primary native QAM observer was called more than once")
        self._result = result

    @property
    def result(self) -> PilotQamResult | None:
        return self._result


def empty_native_qam_statistics() -> NativeQamSufficientStatisticsV1:
    """Return the canonical identity element for QAM aggregation."""

    return NativeQamSufficientStatisticsV1(
        qam_result_count=0,
        correct_symbol_count=0,
        symbol_count=0,
        frame_count=0,
        squared_error_sum=Decimal(0),
        reference_energy_sum=Decimal(0),
        hard_symbol_accuracy=None,
        rms_evm=None,
    )


def native_qam_sufficient_statistics(
    result: PilotQamResult,
) -> NativeQamSufficientStatisticsV1:
    """Derive mergeable counts and energies from one exact QAM computation."""

    if result.status is not NumericalStatus.COMPLETE:
        if (
            result.metrics is not None
            or result.expected.size
            or result.equalized.size
            or result.frame_equalized.size
        ):
            raise ValueError("noncomplete primary QAM result carries measured arrays")
        return empty_native_qam_statistics()
    metrics = result.metrics
    if metrics is None:
        raise ValueError("complete primary QAM result lacks metrics")
    expected = np.asarray(result.expected, dtype=np.complex128)
    equalized = np.asarray(result.equalized, dtype=np.complex128)
    frames = np.asarray(result.frame_equalized, dtype=np.complex128)
    if (
        expected.shape != _QIN_SHAPE
        or equalized.shape != _QIN_SHAPE
        or frames.ndim != 3
        or frames.shape[1:] != _QIN_SHAPE
        or frames.shape[0] != metrics.frame_count
        or not frames.shape[0]
    ):
        raise ValueError("complete primary QAM arrays do not close frame support")
    if not (
        np.all(np.isfinite(expected))
        and np.all(np.isfinite(equalized))
        and np.all(np.isfinite(frames))
    ):
        raise ValueError("primary QAM arrays must be finite")

    constellation = np.exp(0.5j * np.pi * (np.arange(4, dtype=float) + 0.5))
    expected_states = np.mod(
        np.rint(np.angle(expected) / (np.pi / 2) - 0.5).astype(int),
        4,
    )
    hard = np.argmin(np.abs(equalized[..., None] - constellation) ** 2, axis=-1)
    known = np.broadcast_to(expected_states, hard.shape)
    squared_errors = np.abs(equalized - expected) ** 2
    reference_energies = np.abs(expected) ** 2

    correct_count = int(np.count_nonzero(hard == known))
    symbol_count = int(equalized.size)
    squared_error = Decimal(str(math.fsum(float(item) for item in squared_errors.flat)))
    reference_energy = Decimal(str(math.fsum(float(item) for item in reference_energies.flat)))
    accuracy = Decimal(correct_count) / Decimal(symbol_count)
    with localcontext() as context:
        context.prec = 34
        evm = (squared_error / reference_energy).sqrt()
    if not math.isclose(
        float(accuracy),
        metrics.hard_symbol_accuracy,
        abs_tol=1e-15,
    ) or not math.isclose(float(evm), metrics.rms_evm, rel_tol=1e-6, abs_tol=1e-12):
        raise ValueError("primary QAM metrics disagree with their sufficient statistics")
    return NativeQamSufficientStatisticsV1(
        qam_result_count=1,
        correct_symbol_count=correct_count,
        symbol_count=symbol_count,
        frame_count=metrics.frame_count,
        squared_error_sum=squared_error,
        reference_energy_sum=reference_energy,
        hard_symbol_accuracy=accuracy,
        rms_evm=evm,
    )


def merge_native_qam_sufficient_statistics(
    values: tuple[NativeQamSufficientStatisticsV1, ...],
) -> NativeQamSufficientStatisticsV1:
    """Merge partitions by counts and energies, never by averaging ratios."""

    result_count = sum(item.qam_result_count for item in values)
    correct_count = sum(item.correct_symbol_count for item in values)
    symbol_count = sum(item.symbol_count for item in values)
    frame_count = sum(item.frame_count for item in values)
    squared_error = sum((item.squared_error_sum for item in values), Decimal(0))
    reference_energy = sum((item.reference_energy_sum for item in values), Decimal(0))
    if not result_count:
        return empty_native_qam_statistics()
    accuracy = Decimal(correct_count) / Decimal(symbol_count)
    with localcontext() as context:
        context.prec = 34
        evm = (squared_error / reference_energy).sqrt()
    return NativeQamSufficientStatisticsV1(
        qam_result_count=result_count,
        correct_symbol_count=correct_count,
        symbol_count=symbol_count,
        frame_count=frame_count,
        squared_error_sum=squared_error,
        reference_energy_sum=reference_energy,
        hard_symbol_accuracy=accuracy,
        rms_evm=evm,
    )


def build_native_qam_probe_evidence(
    *,
    opportunity_index: int,
    opportunity: NativeProbeWindowV3,
    continuity_segment_device_sample_start: int,
    detection: PilotProbeDetection,
    qam_result: PilotQamResult | None,
) -> NativeQamProbeEvidenceV1:
    """Bind a same-call primary QAM outcome to one valid global opportunity."""

    validity = opportunity.validity
    segment_index = validity.continuity_segment_index
    if validity.disposition is not NativeWindowDisposition.VALID or segment_index is None:
        raise ValueError("native QAM evidence requires a wholly-valid probe")
    local_start = opportunity.probe.sample_start - continuity_segment_device_sample_start
    if local_start < 0 or detection.sample_start != local_start:
        raise ValueError("native QAM detection changed segment-local probe coordinates")

    detection_status = detection.status.value
    if detection.status is NumericalStatus.COMPLETE:
        if qam_result is None:
            raise ValueError("complete primary detection lacks its same-call QAM result")
        qam_status = NativeQamComputationStatusV1(qam_result.status.value)
        statistics = native_qam_sufficient_statistics(qam_result)
        reason = qam_result.reason
        primary_rank = 0
        primary_epoch = detection.local_epoch_sample
        primary_cfo = detection.acquired_cfo_hz
        qam_absolute_cfo = qam_result.absolute_cfo_hz
        qam_residual_cfo = qam_result.residual_cfo_refinement_hz
    else:
        if qam_result is not None:
            raise ValueError("candidate-free primary detection unexpectedly ran QAM")
        qam_status = NativeQamComputationStatusV1.NOT_EVALUATED
        statistics = empty_native_qam_statistics()
        reason = "QAM was not evaluated because primary acquisition produced no candidate"
        primary_rank = None
        primary_epoch = None
        primary_cfo = None
        qam_absolute_cfo = None
        qam_residual_cfo = None
    values = {
        "schema_version": 1,
        "opportunity_index": opportunity_index,
        "continuity_segment_index": segment_index,
        "global_device_sample_start": opportunity.probe.sample_start,
        "detection_status": detection_status,
        "primary_candidate_rank": primary_rank,
        "primary_local_epoch_sample": primary_epoch,
        "primary_acquired_cfo_hz": primary_cfo,
        "qam_status": qam_status.value,
        "qam_absolute_cfo_hz": qam_absolute_cfo,
        "qam_residual_cfo_refinement_hz": qam_residual_cfo,
        "statistics": statistics.model_dump(mode="json"),
        "reason": reason,
    }
    return NativeQamProbeEvidenceV1.model_validate(
        {**values, "evidence_digest": canonical_digest(values)}
    )
