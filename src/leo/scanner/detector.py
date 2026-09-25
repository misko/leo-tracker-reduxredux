"""GLRT-64-only clustered analysis for one captured scanner dwell."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

import numpy as np

from leo.analysis.starlink import (
    ReceiverFrequencyCalibration,
    StarlinkEdge,
    SymbolwiseAcquisitionConfig,
)
from leo.analysis.starlink.acquisition import acquire_symbolwise
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_scores, refine_glrt64_epochs
from leo.scanner.models import Glrt64FirstDetection

_ZERO_CALIBRATION_SHA256 = "0" * 64
_CONFIRMATION_CFO_GATE_HZ = 8_000.0

# Keep the scanner's bounded initial acquisition aligned with the production
# Standard lane.  These distances control nonmaximum suppression before GLRT
# scoring; they do not make one probe depend on any neighboring probe or track.
STANDARD_SCANNER_RETAINED_CANDIDATE_COUNT = 10
STANDARD_SCANNER_CANDIDATE_EPOCH_SEPARATION_SAMPLES = 5
STANDARD_SCANNER_CANDIDATE_CFO_SEPARATION_HZ = 10_000.0


@dataclass(frozen=True, slots=True)
class Glrt64SearchGeometry:
    """Capture-bound frequency references for one detector invocation."""

    receiver_calibrations: tuple[ReceiverFrequencyCalibration, ...]
    residual_cfo_min_hz: float
    residual_cfo_max_hz: float
    fallback_anchor_symbols: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class _ProbeEvaluation:
    candidates: tuple[Glrt64CandidateResponse, ...]
    hits: tuple[Glrt64FirstDetection, ...]

    def has_fractional_detection(self, gate: float) -> bool:
        return any(
            item.fractional_margin is not None and item.fractional_margin >= gate
            for item in self.candidates
        )


class Glrt64DwellConfiguration(Protocol):
    """Structural acquisition geometry shared by legacy and persistent dwells."""

    @property
    def dwell_samples(self) -> int: ...

    @property
    def probe_samples(self) -> int: ...

    @property
    def probe_stride_ms(self) -> int: ...

    @property
    def probe_stride_samples(self) -> int: ...

    @property
    def scheduled_probe_count(self) -> int: ...

    @property
    def sample_rate_hz(self) -> int: ...

    @property
    def receiver_ids(self) -> tuple[int, ...]: ...

    @property
    def probe_ms(self) -> int: ...

    @property
    def glrt64_margin_gate(self) -> float: ...

    @property
    def maximum_acquisition_candidates(self) -> int: ...


@dataclass(frozen=True, slots=True)
class DwellDetection:
    first: Glrt64FirstDetection | None
    best_margin: float | None
    reason: str


@dataclass(frozen=True, slots=True)
class Glrt64CandidateResponse:
    candidate_rank: int
    epoch_sample: int
    acquired_cfo_hz: float
    residual_cfo_hz: float
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float
    passed_margin_gate: bool
    fractional_epoch_status: str = "not_evaluated"
    fractional_epoch_offset_samples: float | None = None
    fractional_frame_phase_sample: float | None = None
    fractional_exact_score: float | None = None
    fractional_control_score: float | None = None
    fractional_residual_cfo_hz: float | None = None
    fractional_tracking_cfo_hz: float | None = None
    fractional_margin: float | None = None


@dataclass(frozen=True, slots=True)
class Glrt64ProbeResponse:
    receiver_id: int
    probe_index: int
    probe_start_ms: int
    candidates: tuple[Glrt64CandidateResponse, ...]


@dataclass(frozen=True, slots=True)
class DwellGlrt64Analysis:
    first: Glrt64FirstDetection | None
    decision_best_margin: float | None
    full_best_margin: float | None
    reason: str
    probes: tuple[Glrt64ProbeResponse, ...]


def _evaluate_probe(
    probe: np.ndarray,
    configuration: Glrt64DwellConfiguration,
    calibration: ReceiverFrequencyCalibration,
    *,
    edge: StarlinkEdge | str,
    acquisition_config: SymbolwiseAcquisitionConfig,
    receiver_id: int,
    probe_index: int,
) -> _ProbeEvaluation:
    acquired = acquire_symbolwise(
        probe,
        configuration.sample_rate_hz,
        calibration,
        edge=edge,
        config=acquisition_config,
    )
    retained = acquired.candidates[: configuration.maximum_acquisition_candidates]
    epochs = tuple(candidate.refined_epoch_sample for candidate in retained)
    frequencies = tuple(candidate.absolute_cfo_hz for candidate in retained)
    integer_scores = conditioned_glrt64_scores(
        probe,
        configuration.sample_rate_hz,
        epoch_samples=epochs,
        acquired_cfo_hz=frequencies,
        edge=edge,
    )
    fractional_refinements = refine_glrt64_epochs(
        probe,
        configuration.sample_rate_hz,
        integer_epoch_samples=epochs,
        acquired_cfo_hz=frequencies,
        edge=edge,
        expected_integer_scores=integer_scores,
    )
    responses: list[Glrt64CandidateResponse] = []
    hits: list[Glrt64FirstDetection] = []
    for candidate, score, fractional in zip(
        retained, integer_scores, fractional_refinements, strict=True
    ):
        passed = score.margin >= configuration.glrt64_margin_gate
        responses.append(
            Glrt64CandidateResponse(
                candidate_rank=candidate.rank,
                epoch_sample=candidate.refined_epoch_sample,
                acquired_cfo_hz=candidate.absolute_cfo_hz,
                residual_cfo_hz=score.residual_cfo_hz,
                tracking_cfo_hz=score.tracking_cfo_hz,
                exact_score=score.exact_score,
                control_score=score.control_score or 0.0,
                margin=score.margin,
                passed_margin_gate=passed,
                fractional_epoch_status=fractional.status.value,
                fractional_epoch_offset_samples=fractional.fractional_epoch_offset_samples,
                fractional_frame_phase_sample=fractional.fractional_frame_phase_sample,
                fractional_exact_score=fractional.fractional_exact_score,
                fractional_control_score=fractional.fractional_control_score,
                fractional_residual_cfo_hz=getattr(fractional, "fractional_residual_cfo_hz", None),
                fractional_tracking_cfo_hz=getattr(fractional, "fractional_tracking_cfo_hz", None),
                fractional_margin=getattr(fractional, "fractional_margin", None),
            )
        )
        if passed:
            hits.append(
                Glrt64FirstDetection(
                    receiver_id=receiver_id,
                    probe_index=probe_index,
                    probe_start_ms=probe_index * configuration.probe_stride_ms,
                    candidate_rank=candidate.rank,
                    epoch_sample=candidate.refined_epoch_sample,
                    acquired_cfo_hz=candidate.absolute_cfo_hz,
                    residual_cfo_hz=score.residual_cfo_hz,
                    tracking_cfo_hz=score.tracking_cfo_hz,
                    exact_score=score.exact_score,
                    control_score=score.control_score or 0.0,
                    margin=score.margin,
                )
            )
    return _ProbeEvaluation(tuple(responses), tuple(hits))


def detect_first_glrt64(
    samples: np.ndarray,
    configuration: Glrt64DwellConfiguration,
    *,
    edge: StarlinkEdge | str,
) -> DwellDetection:
    """Return the first hit in a CFO-consistent non-overlapping pair."""

    analysis = analyze_glrt64_dwell(samples, configuration, edge=edge)
    return DwellDetection(
        first=analysis.first,
        best_margin=analysis.decision_best_margin,
        reason=analysis.reason,
    )


def analyze_glrt64_dwell(
    samples: np.ndarray,
    configuration: Glrt64DwellConfiguration,
    *,
    edge: StarlinkEdge | str,
    search_geometry: Glrt64SearchGeometry | None = None,
) -> DwellGlrt64Analysis:
    """Evaluate the complete scanner probe schedule and derive the live decision."""

    values = np.asarray(samples)
    expected = (configuration.dwell_samples, len(configuration.receiver_ids))
    if values.ndim != 2 or values.shape != expected:
        raise ValueError(f"scanner dwell has shape {values.shape}, expected {expected}")
    calibrations = (
        tuple(
            ReceiverFrequencyCalibration(
                receiver_id=str(receiver_id),
                center_hz=0.0,
                calibration_sha256=_ZERO_CALIBRATION_SHA256,
            )
            for receiver_id in configuration.receiver_ids
        )
        if search_geometry is None
        else search_geometry.receiver_calibrations
    )
    if tuple(item.receiver_id for item in calibrations) != tuple(
        str(item) for item in configuration.receiver_ids
    ):
        raise ValueError("GLRT search geometry receiver order differs from detector configuration")
    acquisition_config = SymbolwiseAcquisitionConfig(
        maximum_probe_samples=configuration.probe_samples,
        retained_candidate_count=configuration.maximum_acquisition_candidates,
        candidate_epoch_separation_samples=(STANDARD_SCANNER_CANDIDATE_EPOCH_SEPARATION_SAMPLES),
        candidate_cfo_separation_hz=STANDARD_SCANNER_CANDIDATE_CFO_SEPARATION_HZ,
    )
    if search_geometry is not None:
        acquisition_config = replace(
            acquisition_config,
            residual_cfo_min_hz=search_geometry.residual_cfo_min_hz,
            residual_cfo_max_hz=search_geometry.residual_cfo_max_hz,
        )
    fallback_acquisition_config = (
        replace(acquisition_config, anchor_symbols=search_geometry.fallback_anchor_symbols)
        if search_geometry is not None and search_geometry.fallback_anchor_symbols
        else None
    )
    best: float | None = None
    decision_best: float | None = None
    first_detection: Glrt64FirstDetection | None = None
    responses: list[Glrt64ProbeResponse] = []
    history: dict[int, list[Glrt64FirstDetection]] = {
        receiver_id: [] for receiver_id in configuration.receiver_ids
    }
    for probe_index in range(configuration.scheduled_probe_count):
        start = probe_index * configuration.probe_stride_samples
        stop = start + configuration.probe_samples
        evaluations: list[_ProbeEvaluation] = []
        for column, receiver_id in enumerate(configuration.receiver_ids):
            probe = np.ascontiguousarray(values[start:stop, column], dtype=np.complex128)
            calibration = calibrations[column]
            evaluations.append(
                _evaluate_probe(
                    probe,
                    configuration,
                    calibration,
                    edge=edge,
                    acquisition_config=acquisition_config,
                    receiver_id=receiver_id,
                    probe_index=probe_index,
                )
            )
        if fallback_acquisition_config is not None and any(
            item.has_fractional_detection(configuration.glrt64_margin_gate) for item in evaluations
        ):
            for column, (receiver_id, evaluation) in enumerate(
                zip(configuration.receiver_ids, evaluations, strict=True)
            ):
                if evaluation.has_fractional_detection(configuration.glrt64_margin_gate):
                    continue
                probe = np.ascontiguousarray(values[start:stop, column], dtype=np.complex128)
                evaluations[column] = _evaluate_probe(
                    probe,
                    configuration,
                    calibrations[column],
                    edge=edge,
                    acquisition_config=fallback_acquisition_config,
                    receiver_id=receiver_id,
                    probe_index=probe_index,
                )
        hits = [hit for item in evaluations for hit in item.hits]
        for receiver_id, evaluation in zip(configuration.receiver_ids, evaluations, strict=True):
            for candidate in evaluation.candidates:
                best = candidate.margin if best is None else max(best, candidate.margin)
            responses.append(
                Glrt64ProbeResponse(
                    receiver_id=receiver_id,
                    probe_index=probe_index,
                    probe_start_ms=probe_index * configuration.probe_stride_ms,
                    candidates=evaluation.candidates,
                )
            )
        for hit in sorted(hits, key=lambda item: (item.receiver_id, -item.margin)):
            compatible = tuple(
                prior
                for prior in history[hit.receiver_id]
                if hit.probe_start_ms - prior.probe_start_ms >= configuration.probe_ms
                and abs(hit.tracking_cfo_hz - prior.tracking_cfo_hz) <= _CONFIRMATION_CFO_GATE_HZ
            )
            if compatible and first_detection is None:
                first_detection = min(
                    compatible,
                    key=lambda item: (item.probe_index, -item.margin),
                )
                decision_best = best
        for hit in hits:
            history[hit.receiver_id].append(hit)
    if first_detection is not None:
        return DwellGlrt64Analysis(
            first=first_detection,
            decision_best_margin=decision_best,
            full_best_margin=best,
            reason=(
                "two same-receiver non-overlapping 20 ms GLRT-64 probes "
                "passed the margin gate within 8 kHz CFO"
            ),
            probes=tuple(responses),
        )
    return DwellGlrt64Analysis(
        first=None,
        decision_best_margin=best,
        full_best_margin=best,
        reason=(
            f"all {configuration.scheduled_probe_count} overlapping "
            f"{configuration.probe_ms} ms probes completed without a confirmed "
            "same-receiver CFO-consistent pair"
        ),
        probes=tuple(responses),
    )
