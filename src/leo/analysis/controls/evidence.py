"""Held-out, null, and surrogate controls for known-pilot candidates."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from leo.analysis.doppler import DopplerFitResult, MotionClass
from leo.analysis.qam import PilotQamMetrics
from leo.analysis.starlink import (
    NumericalStatus,
    normalized_frame_score,
    qin_edge_pilot_frame,
)
from leo.analysis.starlink.acquisition import DEFAULT_VERIFY_SYMBOLS
from leo.analysis.starlink.long_dwell import (
    DenseRefinementResult,
    DenseRefinementWindow,
    QamHandoffResult,
    ScientificConfidence,
)
from leo.contracts.digests import canonical_digest


@dataclass(frozen=True, slots=True)
class ControlConfig:
    surrogate_symbol_rolls: tuple[int, ...] = (17, 53, 101)
    minimum_held_out_margin: float = 0.05
    minimum_surrogate_margin: float = 0.03
    minimum_qam_accuracy: float = 0.6
    maximum_qam_evm: float = 1.25
    thresholds_calibrated: bool = False

    def __post_init__(self) -> None:
        if not self.surrogate_symbol_rolls or len(set(self.surrogate_symbol_rolls)) != len(
            self.surrogate_symbol_rolls
        ):
            raise ValueError("surrogate rolls must be non-empty and unique")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in self.surrogate_symbol_rolls
        ):
            raise ValueError("surrogate rolls must be integers")
        if not 0 <= self.minimum_qam_accuracy <= 1:
            raise ValueError("minimum_qam_accuracy must lie in zero to one")
        if not math.isfinite(self.minimum_held_out_margin) or not math.isfinite(
            self.minimum_surrogate_margin
        ):
            raise ValueError("control margins must be finite")
        if self.maximum_qam_evm <= 0 or not math.isfinite(self.maximum_qam_evm):
            raise ValueError("maximum_qam_evm must be finite and positive")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class CandidateControlEvidence:
    candidate_id: str
    receiver_id: int
    held_out_exact_score: float
    precommitted_null_score: float
    surrogate_scores: tuple[float, ...]
    held_out_margin: float
    surrogate_margin: float
    qam_accuracy: float | None
    qam_evm: float | None
    dynamic_track: bool
    passed_research_gate: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ControlResult:
    status: NumericalStatus
    config_digest: str
    evidence: tuple[CandidateControlEvidence, ...]
    confidence: ScientificConfidence
    thresholds_calibrated: bool
    specificity_claimed: bool
    reason: str


def evaluate_candidate_controls(
    windows: tuple[DenseRefinementWindow, ...],
    refined: DenseRefinementResult,
    qam: QamHandoffResult,
    doppler: DopplerFitResult,
    sample_rate_hz: float,
    config: ControlConfig,
) -> ControlResult:
    """Evaluate controls at preselected timing/CFO; never reacquire a surrogate."""

    source = {item.candidate_id: item for item in windows}
    qam_by_receiver = _qam_metrics(
        qam,
        qam.receiver_ids or tuple(dict.fromkeys(item.receiver_id for item in windows)),
    )
    output = []
    for candidate in refined.refined:
        window = source.get(candidate.candidate_id)
        if window is None:
            raise ValueError("control candidate has no source window")
        scores = []
        for roll in config.surrogate_symbol_rolls:
            template = qin_edge_pilot_frame(sample_rate_hz, symbol_roll=roll)
            score, _ = normalized_frame_score(
                window.samples,
                template,
                sample_rate_hz,
                candidate.local_epoch_sample,
                candidate.absolute_cfo_hz,
                DEFAULT_VERIFY_SYMBOLS,
            )
            scores.append(score)
        null_score = (
            scores[config.surrogate_symbol_rolls.index(17)]
            if 17 in config.surrogate_symbol_rolls
            else max(scores)
        )
        surrogate_max = max(scores)
        held_out_margin = candidate.verify_score - null_score
        surrogate_margin = candidate.verify_score - surrogate_max
        metrics = qam_by_receiver.get(candidate.receiver_id)
        reasons = []
        if held_out_margin < config.minimum_held_out_margin:
            reasons.append("held-out exact-minus-null margin below gate")
        if surrogate_margin < config.minimum_surrogate_margin:
            reasons.append("exact-minus-surrogate margin below gate")
        if metrics is None:
            reasons.append("QAM evidence unavailable")
        else:
            if metrics.hard_symbol_accuracy < config.minimum_qam_accuracy:
                reasons.append("known-pilot QAM accuracy below gate")
            if metrics.rms_evm > config.maximum_qam_evm:
                reasons.append("known-pilot QAM EVM above gate")
        dynamic = doppler.motion_class is MotionClass.DYNAMIC
        if not dynamic:
            reasons.append("Doppler track is not dynamic")
        output.append(
            CandidateControlEvidence(
                candidate.candidate_id,
                candidate.receiver_id,
                candidate.verify_score,
                null_score,
                tuple(scores),
                held_out_margin,
                surrogate_margin,
                None if metrics is None else metrics.hard_symbol_accuracy,
                None if metrics is None else metrics.rms_evm,
                dynamic,
                not reasons,
                tuple(reasons),
            )
        )
    passed = any(item.passed_research_gate for item in output)
    if not output:
        status = NumericalStatus.INSUFFICIENT
        confidence = ScientificConfidence.INSUFFICIENT
        reason = "no refined candidate was available for controls"
    elif passed and config.thresholds_calibrated:
        status = NumericalStatus.COMPLETE
        confidence = ScientificConfidence.QUALIFIED
        reason = "candidate passed calibrated controls"
    elif passed:
        status = NumericalStatus.COMPLETE
        confidence = ScientificConfidence.CANDIDATE
        reason = "candidate passed research gates; specificity is not calibrated"
    else:
        status = NumericalStatus.NO_RESULT
        confidence = ScientificConfidence.REJECTED
        reason = "every candidate failed at least one precommitted control"
    return ControlResult(
        status,
        config.digest,
        tuple(output),
        confidence,
        config.thresholds_calibrated,
        config.thresholds_calibrated,
        reason,
    )


def _qam_metrics(
    qam: QamHandoffResult, receiver_ids: tuple[int, ...]
) -> dict[int, PilotQamMetrics]:
    complete = [item.metrics for item in qam.receiver_results if item.metrics is not None]
    result = {
        receiver_id: metrics for receiver_id, metrics in zip(receiver_ids, complete, strict=False)
    }
    if qam.combined is not None and qam.combined.metrics is not None:
        for receiver_id in receiver_ids:
            result.setdefault(receiver_id, qam.combined.metrics)
    return result
