"""Infrastructure-blind, multi-basin Qin pilot acquisition primitives.

The numerical stages are a narrow rewrite of the historical symbolwise v3 and
Redux v0.3 oracle implementations. No source repository is imported at runtime.
All search frequencies are receiver-relative; an immutable calibration supplies
the center and the reported absolute CFO is always ``center + residual``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

try:
    from leo.analysis.starlink import _native_acquisition  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - exercised by the explicit fallback test
    _native_acquisition = None

from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    StarlinkEdge,
    qin_edge_pilot_frame,
)

DEFAULT_ANCHOR_SYMBOLS = tuple(range(2, 302, 26))
DEFAULT_ACQUIRE_SYMBOLS = tuple(range(2, 302, 2))
DEFAULT_VERIFY_SYMBOLS = tuple(range(3, 302, 2))


class NumericalStatus(StrEnum):
    COMPLETE = "complete"
    NO_RESULT = "no_result"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True, slots=True)
class ReceiverFrequencyCalibration:
    receiver_id: str
    center_hz: float
    calibration_sha256: str

    def __post_init__(self) -> None:
        if not self.receiver_id or not math.isfinite(self.center_hz):
            raise ValueError("receiver calibration requires an ID and finite center")
        if not re.fullmatch(r"[0-9a-f]{64}", self.calibration_sha256):
            raise ValueError("calibration_sha256 must be a lowercase SHA-256 digest")

    def absolute_cfo_hz(self, residual_cfo_hz: float) -> float:
        if not math.isfinite(residual_cfo_hz):
            raise ValueError("residual CFO must be finite")
        return self.center_hz + residual_cfo_hz


@dataclass(frozen=True, slots=True)
class SymbolwiseAcquisitionConfig:
    residual_cfo_min_hz: float = -400_000.0
    residual_cfo_max_hz: float = 400_000.0
    coarse_cfo_step_hz: float = 80_000.0
    fine_cfo_radius_hz: float = 80_000.0
    fine_cfo_step_hz: float = 500.0
    conditioned_cfo_radius_hz: float = 2_000.0
    conditioned_cfo_step_hz: float = 100.0
    retained_candidate_count: int = 8
    candidate_epoch_separation_samples: int = 20
    candidate_cfo_separation_hz: float = 80_000.0
    minimum_frame_support: int = 2
    maximum_probe_samples: int = 50_000
    anchor_symbols: tuple[int, ...] = DEFAULT_ANCHOR_SYMBOLS
    acquire_symbols: tuple[int, ...] = DEFAULT_ACQUIRE_SYMBOLS
    verify_symbols: tuple[int, ...] = DEFAULT_VERIFY_SYMBOLS

    def __post_init__(self) -> None:
        finite = (
            self.residual_cfo_min_hz,
            self.residual_cfo_max_hz,
            self.coarse_cfo_step_hz,
            self.fine_cfo_radius_hz,
            self.fine_cfo_step_hz,
            self.conditioned_cfo_radius_hz,
            self.conditioned_cfo_step_hz,
            self.candidate_cfo_separation_hz,
        )
        if not all(math.isfinite(value) for value in finite):
            raise ValueError("CFO configuration values must be finite")
        if self.residual_cfo_min_hz >= self.residual_cfo_max_hz:
            raise ValueError("residual CFO domain must be non-empty")
        if min(finite[2:]) <= 0:
            raise ValueError("CFO steps, radii, and separation must be positive")
        integer_values = (
            self.retained_candidate_count,
            self.candidate_epoch_separation_samples,
            self.minimum_frame_support,
            self.maximum_probe_samples,
        )
        if any(isinstance(value, bool) or value <= 0 for value in integer_values):
            raise ValueError("candidate, support, and sample bounds must be positive")
        for symbols, name in (
            (self.anchor_symbols, "anchor_symbols"),
            (self.acquire_symbols, "acquire_symbols"),
            (self.verify_symbols, "verify_symbols"),
        ):
            _validate_symbols(symbols, name)
        if set(self.acquire_symbols) & set(self.verify_symbols):
            raise ValueError("acquire and verify symbols must be disjoint")
        if not set(self.anchor_symbols) <= set(self.acquire_symbols):
            raise ValueError("anchor symbols must be a subset of acquire symbols")


@dataclass(frozen=True, slots=True)
class AcquisitionCandidate:
    rank: int
    coarse_epoch_sample: int
    coarse_residual_cfo_hz: float
    refined_epoch_sample: int
    residual_cfo_hz: float
    absolute_cfo_hz: float
    coarse_score: float
    acquire_score: float
    verify_score: float
    conditioned_exact_score: float
    conditioned_control_score: float
    verify_minus_control_margin: float
    frame_support: int


@dataclass(frozen=True, slots=True)
class SymbolwiseAcquisitionResult:
    status: NumericalStatus
    receiver_calibration: ReceiverFrequencyCalibration
    edge: StarlinkEdge
    sample_rate_hz: float
    sample_count: int
    candidates: tuple[AcquisitionCandidate, ...]
    reason: str
    candidate_only: bool = True

    @property
    def winner(self) -> AcquisitionCandidate | None:
        return self.candidates[0] if self.candidates else None


@dataclass(frozen=True, slots=True)
class KnownPilotFrameAlignment:
    """Phase-invariant full-frame alignment around a bounded CFO seed.

    The epoch is a discrete hypothesis over one 750 Hz frame period.  It is
    deliberately separate from the small residual timing/SFO state used by a
    tracking loop: a full-frame ambiguity is circular and generally
    multimodal, so it must not be represented by widening one Gaussian timing
    covariance.
    """

    status: NumericalStatus
    epoch_sample: int | None
    absolute_cfo_hz: float | None
    nominal_epoch_sample: int | None
    nominal_absolute_cfo_hz: float
    expected_symbol_roll: int
    raw_offset_from_nominal_samples: int | None
    circular_offset_from_nominal_samples: float | None
    cfo_offset_from_nominal_hz: float | None
    frame_period_samples: float
    searched_epoch_count: int
    searched_cfo_count: int
    adjudicated_candidate_count: int
    coarse_score: float | None
    exact_score: float | None
    control_score: float | None
    control_epoch_sample: int | None
    control_absolute_cfo_hz: float | None
    control_frame_support: int
    exact_minus_control_margin: float | None
    frame_support: int
    reason: str
    phase_invariant: bool = True
    absolute_carrier_phase_resolved: bool = False
    candidate_only: bool = True


@dataclass(frozen=True, slots=True)
class _AdjudicatedAlignmentCandidate:
    epoch_sample: int
    absolute_cfo_hz: float
    anchor_score: float
    exact_score: float
    control_score: float
    frame_support: int

    @property
    def margin(self) -> float:
        return self.exact_score - self.control_score


@dataclass(frozen=True, slots=True)
class _ScoredAlignmentCandidate:
    epoch_sample: int
    absolute_cfo_hz: float
    anchor_score: float
    verify_score: float
    frame_support: int


def align_known_pilot_frames(
    samples: np.ndarray,
    sample_rate_hz: float,
    *,
    absolute_cfo_hz: float,
    edge: StarlinkEdge | str,
    nominal_epoch_sample: int | None = None,
    expected_symbol_roll: int = 0,
    minimum_exact_score: float = 0.02,
    minimum_exact_minus_control_margin: float = 0.0,
    minimum_frame_support: int = 2,
    retained_candidate_count: int = 8,
    candidate_epoch_separation_samples: int = 20,
    cfo_search_radius_hz: float = 0.0,
    cfo_search_step_hz: float = 250.0,
    candidate_cfo_separation_hz: float = 500.0,
) -> KnownPilotFrameAlignment:
    """Search one complete frame period while treating prompt phase as nuisance.

    Callers supply a GLRT/trajectory CFO seed and may search a bounded local CFO
    interval jointly with epoch.  Even Qin symbols select candidate basins;
    disjoint odd Qin symbols adjudicate them.  The expected and rolled-control
    hypotheses each maximize over the same epoch/CFO domain before their scores
    are compared, so a symbol roll cannot win merely by shifting the epoch.
    Scores combine magnitudes per frame, so arbitrary common or frame-local
    carrier phase cannot select the timing branch.
    """

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if not math.isfinite(absolute_cfo_hz):
        raise ValueError("absolute CFO must be finite")
    if (
        not math.isfinite(cfo_search_radius_hz)
        or cfo_search_radius_hz < 0.0
        or not math.isfinite(cfo_search_step_hz)
        or cfo_search_step_hz <= 0.0
        or not math.isfinite(candidate_cfo_separation_hz)
        or candidate_cfo_separation_hz <= 0.0
    ):
        raise ValueError("alignment CFO radius must be nonnegative and steps positive")
    if nominal_epoch_sample is not None and (
        isinstance(nominal_epoch_sample, bool)
        or not isinstance(nominal_epoch_sample, (int, np.integer))
        or nominal_epoch_sample < 0
    ):
        raise ValueError("nominal epoch must be a nonnegative integer")
    if expected_symbol_roll not in (0, CONTROL_SYMBOL_ROLL):
        raise ValueError("alignment symbol roll must select the exact or declared control pilot")
    if (
        not math.isfinite(minimum_exact_score)
        or not 0 <= minimum_exact_score <= 1
        or not math.isfinite(minimum_exact_minus_control_margin)
        or not -1 <= minimum_exact_minus_control_margin <= 1
    ):
        raise ValueError("alignment score gates must lie in their finite unit domains")
    integer_settings = (
        minimum_frame_support,
        retained_candidate_count,
        candidate_epoch_separation_samples,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1
        for value in integer_settings
    ):
        raise ValueError("alignment support, candidate count, and separation must be positive")

    period = sample_rate_hz / FRAME_RATE_HZ
    # Integer start samples in the half-open interval [0, T_frame) include
    # floor(T_frame) when the sampled period is non-integral.  At 2.5 MS/s,
    # this is 0..3333 (3334 hypotheses), not 0..3332.
    epoch_count = math.ceil(period)
    cfo_grid = (
        (float(absolute_cfo_hz),)
        if cfo_search_radius_hz == 0.0
        else _bounded_grid(
            absolute_cfo_hz - cfo_search_radius_hz,
            absolute_cfo_hz + cfo_search_radius_hz,
            cfo_search_step_hz,
        )
    )
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    if values.size < frame_content + epoch_count:
        return KnownPilotFrameAlignment(
            status=NumericalStatus.INSUFFICIENT,
            epoch_sample=None,
            absolute_cfo_hz=None,
            nominal_epoch_sample=nominal_epoch_sample,
            nominal_absolute_cfo_hz=float(absolute_cfo_hz),
            expected_symbol_roll=expected_symbol_roll,
            raw_offset_from_nominal_samples=None,
            circular_offset_from_nominal_samples=None,
            cfo_offset_from_nominal_hz=None,
            frame_period_samples=float(period),
            searched_epoch_count=epoch_count,
            searched_cfo_count=len(cfo_grid),
            adjudicated_candidate_count=0,
            coarse_score=None,
            exact_score=None,
            control_score=None,
            control_epoch_sample=None,
            control_absolute_cfo_hz=None,
            control_frame_support=0,
            exact_minus_control_margin=None,
            frame_support=0,
            reason="full-frame alignment requires at least two supported frames",
        )
    if not np.all(np.isfinite(values)):
        raise ValueError("alignment samples must be finite")
    if float(np.vdot(values, values).real) <= np.finfo(float).tiny:
        return KnownPilotFrameAlignment(
            status=NumericalStatus.NO_RESULT,
            epoch_sample=None,
            absolute_cfo_hz=None,
            nominal_epoch_sample=nominal_epoch_sample,
            nominal_absolute_cfo_hz=float(absolute_cfo_hz),
            expected_symbol_roll=expected_symbol_roll,
            raw_offset_from_nominal_samples=None,
            circular_offset_from_nominal_samples=None,
            cfo_offset_from_nominal_hz=None,
            frame_period_samples=float(period),
            searched_epoch_count=epoch_count,
            searched_cfo_count=len(cfo_grid),
            adjudicated_candidate_count=0,
            coarse_score=0.0,
            exact_score=0.0,
            control_score=0.0,
            control_epoch_sample=None,
            control_absolute_cfo_hz=None,
            control_frame_support=0,
            exact_minus_control_margin=0.0,
            frame_support=0,
            reason="full-frame alignment found no signal energy",
        )

    exact = np.asarray(
        qin_edge_pilot_frame(
            sample_rate_hz,
            selected_edge,
            symbol_roll=expected_symbol_roll,
        ),
        np.complex128,
    )
    control_roll = CONTROL_SYMBOL_ROLL if expected_symbol_roll == 0 else 0
    control = np.asarray(
        qin_edge_pilot_frame(
            sample_rate_hz,
            selected_edge,
            symbol_roll=control_roll,
        ),
        np.complex128,
    )
    exact_candidates = _scored_alignment_candidates(
        values,
        exact,
        sample_rate_hz,
        cfo_grid,
        epoch_count,
        float(absolute_cfo_hz),
        cfo_search_step_hz,
        minimum_frame_support,
        retained_candidate_count,
        candidate_epoch_separation_samples,
        candidate_cfo_separation_hz,
    )
    control_candidates = _scored_alignment_candidates(
        values,
        control,
        sample_rate_hz,
        cfo_grid,
        epoch_count,
        float(absolute_cfo_hz),
        cfo_search_step_hz,
        minimum_frame_support,
        retained_candidate_count,
        candidate_epoch_separation_samples,
        candidate_cfo_separation_hz,
    )
    control_winner = max(
        control_candidates,
        key=lambda item: (
            item.verify_score,
            item.anchor_score,
            -abs(item.absolute_cfo_hz - absolute_cfo_hz),
            -item.epoch_sample,
        ),
        default=None,
    )
    control_score = 0.0 if control_winner is None else control_winner.verify_score
    adjudicated = [
        _AdjudicatedAlignmentCandidate(
            epoch_sample=item.epoch_sample,
            absolute_cfo_hz=item.absolute_cfo_hz,
            anchor_score=item.anchor_score,
            exact_score=item.verify_score,
            control_score=float(control_score),
            frame_support=item.frame_support,
        )
        for item in exact_candidates
    ]
    if not adjudicated:
        return KnownPilotFrameAlignment(
            status=NumericalStatus.NO_RESULT,
            epoch_sample=None,
            absolute_cfo_hz=None,
            nominal_epoch_sample=nominal_epoch_sample,
            nominal_absolute_cfo_hz=float(absolute_cfo_hz),
            expected_symbol_roll=expected_symbol_roll,
            raw_offset_from_nominal_samples=None,
            circular_offset_from_nominal_samples=None,
            cfo_offset_from_nominal_hz=None,
            frame_period_samples=float(period),
            searched_epoch_count=epoch_count,
            searched_cfo_count=len(cfo_grid),
            adjudicated_candidate_count=0,
            coarse_score=0.0,
            exact_score=0.0,
            control_score=0.0,
            control_epoch_sample=(None if control_winner is None else control_winner.epoch_sample),
            control_absolute_cfo_hz=(
                None if control_winner is None else control_winner.absolute_cfo_hz
            ),
            control_frame_support=(0 if control_winner is None else control_winner.frame_support),
            exact_minus_control_margin=0.0,
            frame_support=0,
            reason="full-frame anchor search found no supported candidate basin",
        )
    passing = [
        item
        for item in adjudicated
        if item.frame_support >= minimum_frame_support
        and item.exact_score >= minimum_exact_score
        and item.margin >= minimum_exact_minus_control_margin
    ]
    winner = max(
        passing or adjudicated,
        key=lambda item: (
            item.margin,
            item.exact_score,
            item.anchor_score,
            -abs(item.absolute_cfo_hz - absolute_cfo_hz),
            -item.epoch_sample,
        ),
    )
    margin = winner.margin
    exact_score = winner.exact_score
    coarse_score = winner.anchor_score
    epoch = winner.epoch_sample
    support = winner.frame_support
    control_score = winner.control_score
    failures = []
    if support < minimum_frame_support:
        failures.append("aligned epoch has insufficient complete-frame support")
    if exact_score < minimum_exact_score:
        failures.append("held-out exact-pilot score is below threshold")
    if margin < minimum_exact_minus_control_margin:
        failures.append("held-out exact-minus-control margin is below threshold")

    nominal = None if nominal_epoch_sample is None else nominal_epoch_sample % epoch_count
    raw_offset = None if nominal is None else epoch - nominal
    circular_offset = None
    if raw_offset is not None:
        circular_offset = float(raw_offset - round(raw_offset / period) * period)
    status = NumericalStatus.NO_RESULT if failures else NumericalStatus.COMPLETE
    return KnownPilotFrameAlignment(
        status=status,
        epoch_sample=epoch,
        absolute_cfo_hz=winner.absolute_cfo_hz,
        nominal_epoch_sample=nominal_epoch_sample,
        nominal_absolute_cfo_hz=float(absolute_cfo_hz),
        expected_symbol_roll=expected_symbol_roll,
        raw_offset_from_nominal_samples=raw_offset,
        circular_offset_from_nominal_samples=circular_offset,
        cfo_offset_from_nominal_hz=winner.absolute_cfo_hz - absolute_cfo_hz,
        frame_period_samples=float(period),
        searched_epoch_count=epoch_count,
        searched_cfo_count=len(cfo_grid),
        adjudicated_candidate_count=len(adjudicated),
        coarse_score=float(coarse_score),
        exact_score=float(exact_score),
        control_score=float(control_score),
        control_epoch_sample=(None if control_winner is None else control_winner.epoch_sample),
        control_absolute_cfo_hz=(
            None if control_winner is None else control_winner.absolute_cfo_hz
        ),
        control_frame_support=(0 if control_winner is None else control_winner.frame_support),
        exact_minus_control_margin=float(margin),
        frame_support=support,
        reason=(
            "phase-invariant full-frame candidate evidence completed on held-out known pilots"
            if not failures
            else "; ".join(failures)
        ),
    )


def _scored_alignment_candidates(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    cfo_grid: tuple[float, ...],
    epoch_count: int,
    nominal_absolute_cfo_hz: float,
    cfo_search_step_hz: float,
    minimum_frame_support: int,
    retained_candidate_count: int,
    candidate_epoch_separation_samples: int,
    candidate_cfo_separation_hz: float,
) -> list[_ScoredAlignmentCandidate]:
    """Retain and score candidate basins for one symmetric pilot hypothesis."""

    score_rows = _folded_anchor_score_grid(
        values,
        template,
        sample_rate_hz,
        cfo_grid,
        DEFAULT_ANCHOR_SYMBOLS,
        epoch_count,
    )
    score_maps = dict(zip(cfo_grid, score_rows, strict=True))
    epoch_support = tuple(
        _complete_alignment_frame_support(
            values.size,
            template.size,
            sample_rate_hz,
            epoch,
        )
        for epoch in range(epoch_count)
    )
    support_mask = np.asarray(epoch_support) >= minimum_frame_support
    search_score_maps = {
        cfo_hz: np.where(support_mask, scores, -np.inf) for cfo_hz, scores in score_maps.items()
    }
    peaks = sorted(
        (
            (float(scores[index]), index, float(candidate_cfo_hz))
            for candidate_cfo_hz, scores in search_score_maps.items()
            for index in _circular_local_peak_indexes(scores)
            if scores[index] > 0.0
        ),
        key=lambda item: (
            item[0],
            -abs(item[2] - nominal_absolute_cfo_hz),
            -item[1],
            -item[2],
        ),
        reverse=True,
    )
    retained = _retain_separated(
        peaks,
        retained_candidate_count,
        candidate_epoch_separation_samples,
        candidate_cfo_separation_hz,
        epoch_count,
    )
    search_min_hz = cfo_grid[0]
    search_max_hz = cfo_grid[-1]
    candidates = []
    for anchor_score, coarse_epoch, coarse_cfo_hz in retained:
        candidate_epoch = _refine_circular_epoch(search_score_maps[coarse_cfo_hz], coarse_epoch)
        if len(cfo_grid) == 1:
            candidate_cfo_hz = coarse_cfo_hz
        else:
            fine_step_hz = min(50.0, cfo_search_step_hz)
            fine_grid = _bounded_grid(
                max(search_min_hz, coarse_cfo_hz - cfo_search_step_hz),
                min(search_max_hz, coarse_cfo_hz + cfo_search_step_hz),
                fine_step_hz,
            )
            fine_scores = _normalized_frame_scores(
                values,
                template,
                sample_rate_hz,
                candidate_epoch,
                fine_grid,
                DEFAULT_ACQUIRE_SYMBOLS,
            )
            fine_index = max(
                range(len(fine_grid)),
                key=lambda index: (
                    fine_scores[index],
                    -abs(fine_grid[index] - nominal_absolute_cfo_hz),
                    -fine_grid[index],
                ),
            )
            candidate_cfo_hz = fine_grid[fine_index]
        verify_score, support = normalized_frame_score(
            values,
            template,
            sample_rate_hz,
            candidate_epoch,
            candidate_cfo_hz,
            DEFAULT_VERIFY_SYMBOLS,
        )
        candidates.append(
            _ScoredAlignmentCandidate(
                epoch_sample=candidate_epoch,
                absolute_cfo_hz=float(candidate_cfo_hz),
                anchor_score=float(anchor_score),
                verify_score=float(verify_score),
                frame_support=support,
            )
        )
    return candidates


def _complete_alignment_frame_support(
    sample_count: int,
    template_size: int,
    sample_rate_hz: float,
    epoch_sample: int,
) -> int:
    period = sample_rate_hz / FRAME_RATE_HZ
    frame = 0
    while epoch_sample + round(frame * period) + template_size <= sample_count:
        frame += 1
    return frame


def acquire_symbolwise(
    samples: np.ndarray,
    sample_rate_hz: float,
    calibration: ReceiverFrequencyCalibration,
    *,
    edge: StarlinkEdge | str,
    config: SymbolwiseAcquisitionConfig | None = None,
) -> SymbolwiseAcquisitionResult:
    """Retain timing/CFO basins and adjudicate them on held-out pilots.

    ``complete`` means the bounded numerical analysis completed and returned
    candidate evidence. It is deliberately not a calibrated detection verdict.
    """

    values = np.asarray(samples, dtype=np.complex128)
    selected_edge = StarlinkEdge(edge)
    config = config or SymbolwiseAcquisitionConfig()
    if values.ndim != 1:
        raise ValueError("samples must be one dimensional")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if values.size > config.maximum_probe_samples:
        raise ValueError("acquisition probe exceeds maximum_probe_samples")
    if not np.all(np.isfinite(values)):
        raise ValueError("acquisition samples must be finite")
    epoch_count = round(sample_rate_hz / FRAME_RATE_HZ)
    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    if values.size < frame_content + epoch_count:
        return _empty_result(
            NumericalStatus.INSUFFICIENT,
            calibration,
            selected_edge,
            sample_rate_hz,
            values.size,
            "at least two supported frames are required",
        )

    exact = np.asarray(qin_edge_pilot_frame(sample_rate_hz, selected_edge), np.complex128)
    control = np.asarray(
        qin_edge_pilot_frame(
            sample_rate_hz,
            selected_edge,
            symbol_roll=CONTROL_SYMBOL_ROLL,
        ),
        np.complex128,
    )
    coarse_residuals = _bounded_grid(
        config.residual_cfo_min_hz,
        config.residual_cfo_max_hz,
        config.coarse_cfo_step_hz,
    )
    score_maps: dict[float, np.ndarray] = {}
    peaks: list[tuple[float, int, float]] = []
    coarse_absolute = tuple(calibration.absolute_cfo_hz(residual) for residual in coarse_residuals)
    coarse_scores = _folded_anchor_score_grid(
        values,
        exact,
        sample_rate_hz,
        coarse_absolute,
        config.anchor_symbols,
        epoch_count,
    )
    for residual, scores in zip(coarse_residuals, coarse_scores, strict=True):
        score_maps[residual] = scores
        for epoch in _local_peak_indexes(scores):
            peaks.append((float(scores[epoch]), epoch, residual))
    peaks.sort(key=lambda item: (item[0], -abs(item[2]), -item[1]), reverse=True)
    retained = _retain_separated(
        peaks,
        config.retained_candidate_count,
        config.candidate_epoch_separation_samples,
        config.candidate_cfo_separation_hz,
        epoch_count,
    )
    if not retained or retained[0][0] <= 0:
        return _empty_result(
            NumericalStatus.NO_RESULT,
            calibration,
            selected_edge,
            sample_rate_hz,
            values.size,
            "coarse acquisition found no nonzero supported basin",
        )

    candidates: list[AcquisitionCandidate] = []
    for coarse_score, coarse_epoch, coarse_residual in retained:
        refined_epoch = _refine_epoch(score_maps[coarse_residual], coarse_epoch, epoch_count)
        fine_grid = _bounded_grid(
            max(config.residual_cfo_min_hz, coarse_residual - config.fine_cfo_radius_hz),
            min(config.residual_cfo_max_hz, coarse_residual + config.fine_cfo_radius_hz),
            config.fine_cfo_step_hz,
        )
        fine_scores = _normalized_frame_scores(
            values,
            exact,
            sample_rate_hz,
            refined_epoch,
            tuple(calibration.absolute_cfo_hz(residual) for residual in fine_grid),
            config.acquire_symbols,
        )
        best_index = max(
            range(len(fine_grid)),
            key=lambda index: (fine_scores[index], -abs(fine_grid[index]), -fine_grid[index]),
        )
        interpolated = _quadratic_peak(fine_grid, fine_scores, best_index)
        conditioned_grid = _bounded_grid(
            max(config.residual_cfo_min_hz, interpolated - config.conditioned_cfo_radius_hz),
            min(config.residual_cfo_max_hz, interpolated + config.conditioned_cfo_radius_hz),
            config.conditioned_cfo_step_hz,
        )
        conditioned_scores = _conditioned_frame_scores(
            values,
            exact,
            sample_rate_hz,
            refined_epoch,
            tuple(calibration.absolute_cfo_hz(residual) for residual in conditioned_grid),
        )
        conditioned_index = max(
            range(len(conditioned_grid)),
            key=lambda index: (
                conditioned_scores[index],
                -abs(conditioned_grid[index]),
                -conditioned_grid[index],
            ),
        )
        residual = conditioned_grid[conditioned_index]
        absolute = calibration.absolute_cfo_hz(residual)
        acquire_score, _ = normalized_frame_score(
            values,
            exact,
            sample_rate_hz,
            refined_epoch,
            absolute,
            config.acquire_symbols,
        )
        verify_score, support = normalized_frame_score(
            values,
            exact,
            sample_rate_hz,
            refined_epoch,
            absolute,
            config.verify_symbols,
        )
        control_score, control_support = normalized_frame_score(
            values,
            control,
            sample_rate_hz,
            refined_epoch,
            absolute,
            config.verify_symbols,
        )
        frame_support = min(support, control_support)
        if frame_support < config.minimum_frame_support:
            continue
        candidates.append(
            AcquisitionCandidate(
                rank=0,
                coarse_epoch_sample=coarse_epoch,
                coarse_residual_cfo_hz=coarse_residual,
                refined_epoch_sample=refined_epoch,
                residual_cfo_hz=residual,
                absolute_cfo_hz=absolute,
                coarse_score=coarse_score,
                acquire_score=acquire_score,
                verify_score=verify_score,
                conditioned_exact_score=conditioned_scores[conditioned_index],
                conditioned_control_score=control_score,
                verify_minus_control_margin=verify_score - control_score,
                frame_support=frame_support,
            )
        )
    if not candidates:
        return _empty_result(
            NumericalStatus.INSUFFICIENT,
            calibration,
            selected_edge,
            sample_rate_hz,
            values.size,
            "retained basins did not have minimum frame support",
        )
    ordered = sorted(
        candidates,
        key=lambda item: (
            item.verify_minus_control_margin,
            item.verify_score,
            item.conditioned_exact_score,
            item.acquire_score,
            -abs(item.residual_cfo_hz),
            -item.refined_epoch_sample,
        ),
        reverse=True,
    )
    ranked = tuple(
        AcquisitionCandidate(
            rank=rank,
            coarse_epoch_sample=item.coarse_epoch_sample,
            coarse_residual_cfo_hz=item.coarse_residual_cfo_hz,
            refined_epoch_sample=item.refined_epoch_sample,
            residual_cfo_hz=item.residual_cfo_hz,
            absolute_cfo_hz=item.absolute_cfo_hz,
            coarse_score=item.coarse_score,
            acquire_score=item.acquire_score,
            verify_score=item.verify_score,
            conditioned_exact_score=item.conditioned_exact_score,
            conditioned_control_score=item.conditioned_control_score,
            verify_minus_control_margin=item.verify_minus_control_margin,
            frame_support=item.frame_support,
        )
        for rank, item in enumerate(ordered)
    )
    return SymbolwiseAcquisitionResult(
        NumericalStatus.COMPLETE,
        calibration,
        selected_edge,
        float(sample_rate_hz),
        values.size,
        ranked,
        "candidate evidence only; whole-search calibration is not established",
    )


def normalized_frame_score(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    epoch_sample: int,
    absolute_cfo_hz: float,
    symbols: tuple[int, ...],
) -> tuple[float, int]:
    """Historical v0.3 normalized noncoherent frame statistic."""

    sample_indexes = _pilot_sample_indexes(sample_rate_hz, symbols)
    references = template[sample_indexes]
    template_energy = float(np.vdot(references, references).real)
    rotation = np.exp(-2j * np.pi * absolute_cfo_hz * sample_indexes / sample_rate_hz)
    period = sample_rate_hz / FRAME_RATE_HZ
    per_frame: list[float] = []
    frame = 0
    while True:
        start = epoch_sample + round(frame * period)
        absolute = start + sample_indexes
        if absolute[-1] >= values.size:
            break
        received = values[absolute]
        denominator = math.sqrt(template_energy * float(np.vdot(received, received).real))
        per_frame.append(
            float(abs(np.vdot(references, received * rotation)) / denominator)
            if denominator
            else 0.0
        )
        frame += 1
    return (float(np.mean(per_frame)) if per_frame else 0.0, len(per_frame))


def _normalized_frame_scores(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    epoch_sample: int,
    absolute_cfo_hz: tuple[float, ...],
    symbols: tuple[int, ...],
) -> tuple[float, ...]:
    """Evaluate one CFO grid with an exact transform or the direct oracle."""

    if not absolute_cfo_hz:
        return ()
    sample_indexes = _pilot_sample_indexes(sample_rate_hz, symbols)
    transform_size = _fine_cfo_transform_size(
        sample_rate_hz,
        absolute_cfo_hz,
        sample_indexes,
    )
    if transform_size is not None:
        return _normalized_frame_scores_fft(
            values,
            template,
            sample_rate_hz,
            epoch_sample,
            absolute_cfo_hz,
            symbols,
            transform_size=transform_size,
        )
    return _normalized_frame_scores_direct(
        values,
        template,
        sample_rate_hz,
        epoch_sample,
        absolute_cfo_hz,
        symbols,
    )


def _normalized_frame_scores_direct(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    epoch_sample: int,
    absolute_cfo_hz: tuple[float, ...],
    symbols: tuple[int, ...],
) -> tuple[float, ...]:
    """Direct matrix oracle for one CFO grid."""

    if not absolute_cfo_hz:
        return ()
    sample_indexes = _pilot_sample_indexes(sample_rate_hz, symbols)
    references = template[sample_indexes]
    template_energy = float(np.vdot(references, references).real)
    received_frames: list[np.ndarray] = []
    period = sample_rate_hz / FRAME_RATE_HZ
    frame = 0
    while True:
        start = epoch_sample + round(frame * period)
        absolute = start + sample_indexes
        if absolute[-1] >= values.size:
            break
        received = values[absolute]
        received_frames.append(received)
        frame += 1
    if not received_frames:
        return tuple(0.0 for _ in absolute_cfo_hz)
    received = np.stack(received_frames, axis=0)
    denominator = np.sqrt(template_energy * np.sum(np.abs(received) ** 2, axis=1))
    weighted = received * np.conj(references)[None, :]
    step = _constant_grid_step(absolute_cfo_hz)
    if step is None:
        rotation = _normalized_rotation_bank(
            sample_rate_hz,
            symbols,
            absolute_cfo_hz,
            sample_indexes,
        )
        correlations = rotation @ weighted.T
    else:
        # A uniform grid consists of one arbitrary base CFO followed by cached
        # fixed offsets. Apply the base once per received sample instead of
        # materializing a complete base-rotated bank for every call.
        base = np.exp(-2j * np.pi * absolute_cfo_hz[0] * sample_indexes / sample_rate_hz)
        offsets = _cached_normalized_offset_rotation(
            float(sample_rate_hz), symbols, len(absolute_cfo_hz), step
        )
        correlations = offsets @ (weighted * base).T
    scores = np.divide(
        np.abs(correlations),
        denominator[None, :],
        out=np.zeros_like(correlations.real),
        where=denominator[None, :] > 0,
    )
    return tuple(float(value) for value in np.mean(scores, axis=1))


def _normalized_frame_scores_fft(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    epoch_sample: int,
    absolute_cfo_hz: tuple[float, ...],
    symbols: tuple[int, ...],
    *,
    transform_size: int,
) -> tuple[float, ...]:
    """Exact sparse-DFT evaluation for one commensurate uniform CFO grid."""

    if not absolute_cfo_hz:
        return ()
    sample_indexes = _pilot_sample_indexes(sample_rate_hz, symbols)
    if (
        transform_size < 2
        or len(absolute_cfo_hz) > transform_size
        or int(sample_indexes[-1]) >= transform_size
    ):
        raise ValueError("fine-CFO transform does not contain the requested geometry")
    sample_step_hz = sample_rate_hz / transform_size
    grid_step_hz = _constant_grid_step(absolute_cfo_hz)
    if grid_step_hz is None or not math.isclose(
        grid_step_hz,
        sample_step_hz,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("fine-CFO grid is not represented by the requested transform")

    references = template[sample_indexes]
    template_energy = float(np.vdot(references, references).real)
    received_frames: list[np.ndarray] = []
    period = sample_rate_hz / FRAME_RATE_HZ
    frame = 0
    while True:
        start = epoch_sample + round(frame * period)
        absolute = start + sample_indexes
        if absolute[-1] >= values.size:
            break
        received = values[absolute]
        received_frames.append(received)
        frame += 1
    if not received_frames:
        return tuple(0.0 for _ in absolute_cfo_hz)

    # Shift the arbitrary first frequency to DFT bin zero.  Only selected pilot
    # samples are nonzero, so rotating those values avoids a transform-sized
    # exponential and multiplication over zeros.
    base_rotation = np.exp(-2j * np.pi * absolute_cfo_hz[0] * sample_indexes / sample_rate_hz)
    received = np.stack(received_frames, axis=0)
    denominator = np.sqrt(template_energy * np.sum(np.abs(received) ** 2, axis=1))
    scratch = np.zeros((len(received_frames), transform_size), dtype=np.complex128)
    scratch[:, sample_indexes] = received * np.conj(references)[None, :] * base_rotation[None, :]
    selected = np.fft.fft(scratch, axis=1)[:, : len(absolute_cfo_hz)].T
    normalized = np.divide(
        np.abs(selected),
        denominator[None, :],
        out=np.zeros_like(selected.real),
        where=denominator[None, :] > 0,
    )
    return tuple(float(value) for value in np.mean(normalized, axis=1))


def _fine_cfo_transform_size(
    sample_rate_hz: float,
    cfo_hz: tuple[float, ...],
    sample_indexes: np.ndarray,
) -> int | None:
    """Return a beneficial exact transform size, otherwise select direct work."""

    step_hz = _constant_grid_step(cfo_hz)
    if step_hz is None or step_hz <= 0:
        return None
    size_float = sample_rate_hz / step_hz
    size = round(size_float)
    if (
        size < 2
        or not math.isclose(size_float, size, rel_tol=0.0, abs_tol=1e-12)
        or len(cfo_hz) > size
        or int(sample_indexes[-1]) >= size
    ):
        return None
    direct_work = len(cfo_hz) * len(sample_indexes)
    transform_work = size * math.log2(size)
    # Factored direct grids use the host BLAS rather than the earlier einsum
    # loop. A fixed factor keeps dispatch deterministic while selecting the
    # measured production crossover: Standard's N=5,000 grid remains an FFT,
    # while Research's 201-bin/N=25,000 geometry uses direct GEMM.
    return size if transform_work < 0.5 * direct_work else None


def conditioned_frame_score(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    epoch_sample: int,
    absolute_cfo_hz: float,
) -> tuple[float, int]:
    """Whole-frame score used only after timing has been fixed."""

    template_energy = float(np.vdot(template, template).real)
    period = sample_rate_hz / FRAME_RATE_HZ
    scores: list[float] = []
    frame = 0
    while True:
        start = epoch_sample + round(frame * period)
        if start + template.size > values.size:
            break
        indexes = np.arange(start, start + template.size, dtype=float)
        segment = values[start : start + template.size]
        corrected = segment * np.exp(-2j * np.pi * absolute_cfo_hz * indexes / sample_rate_hz)
        denominator = math.sqrt(template_energy * float(np.vdot(segment, segment).real))
        scores.append(
            float(abs(np.vdot(template, corrected)) / denominator) if denominator else 0.0
        )
        frame += 1
    return (float(np.mean(scores)) if scores else 0.0, len(scores))


def _conditioned_frame_scores(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    epoch_sample: int,
    absolute_cfo_hz: tuple[float, ...],
) -> tuple[float, ...]:
    """Vectorized whole-frame score over a CFO grid with shared local phases."""

    if not absolute_cfo_hz:
        return ()
    template_energy = float(np.vdot(template, template).real)
    period = sample_rate_hz / FRAME_RATE_HZ
    segments: list[np.ndarray] = []
    frame = 0
    while True:
        start = epoch_sample + round(frame * period)
        if start + template.size > values.size:
            break
        segment = values[start : start + template.size]
        segments.append(segment)
        frame += 1
    if not segments:
        return tuple(0.0 for _ in absolute_cfo_hz)
    local_indexes = np.arange(template.size, dtype=float)
    received = np.stack(segments, axis=0)
    denominator = np.sqrt(template_energy * np.sum(np.abs(received) ** 2, axis=1))
    weighted = received * np.conj(template)[None, :]
    step = _constant_grid_step(absolute_cfo_hz)
    if step is None:
        rotation = _conditioned_rotation_bank(
            sample_rate_hz,
            template.size,
            absolute_cfo_hz,
            local_indexes,
        )
        correlations = rotation @ weighted.T
    else:
        base = np.exp(-2j * np.pi * absolute_cfo_hz[0] * local_indexes / sample_rate_hz)
        offsets = _cached_conditioned_offset_rotation(
            float(sample_rate_hz), template.size, len(absolute_cfo_hz), step
        )
        correlations = offsets @ (weighted * base).T
    scores = np.divide(
        np.abs(correlations),
        denominator[None, :],
        out=np.zeros_like(correlations.real),
        where=denominator[None, :] > 0,
    )
    return tuple(float(value) for value in np.mean(scores, axis=1))


def _normalized_rotation_bank(
    sample_rate_hz: float,
    symbols: tuple[int, ...],
    cfo_hz: tuple[float, ...],
    sample_indexes: np.ndarray,
) -> np.ndarray:
    step = _constant_grid_step(cfo_hz)
    if step is None:
        cfo = np.asarray(cfo_hz, dtype=float)
        return np.exp((-2j * np.pi * cfo[:, None]) * sample_indexes[None, :] / sample_rate_hz)
    base = np.exp(-2j * np.pi * cfo_hz[0] * sample_indexes / sample_rate_hz)
    return (
        _cached_normalized_offset_rotation(float(sample_rate_hz), symbols, len(cfo_hz), step)
        * base[None, :]
    )


def _conditioned_rotation_bank(
    sample_rate_hz: float,
    sample_count: int,
    cfo_hz: tuple[float, ...],
    sample_indexes: np.ndarray,
) -> np.ndarray:
    step = _constant_grid_step(cfo_hz)
    if step is None:
        cfo = np.asarray(cfo_hz, dtype=float)
        return np.exp((-2j * np.pi * cfo[:, None]) * sample_indexes[None, :] / sample_rate_hz)
    base = np.exp(-2j * np.pi * cfo_hz[0] * sample_indexes / sample_rate_hz)
    return (
        _cached_conditioned_offset_rotation(float(sample_rate_hz), sample_count, len(cfo_hz), step)
        * base[None, :]
    )


def _constant_grid_step(values: tuple[float, ...]) -> float | None:
    if len(values) < 2:
        return None
    step = float(values[1] - values[0])
    exact = all(value == values[0] + index * step for index, value in enumerate(values))
    return step if exact else None


@lru_cache(maxsize=16)
def _cached_normalized_offset_rotation(
    sample_rate_hz: float,
    symbols: tuple[int, ...],
    count: int,
    step_hz: float,
) -> np.ndarray:
    indexes = _pilot_sample_indexes(sample_rate_hz, symbols)
    offsets = np.arange(count, dtype=float) * step_hz
    result = np.exp((-2j * np.pi * offsets[:, None]) * indexes[None, :] / sample_rate_hz)
    result.flags.writeable = False
    return result


@lru_cache(maxsize=16)
def _cached_conditioned_offset_rotation(
    sample_rate_hz: float,
    sample_count: int,
    count: int,
    step_hz: float,
) -> np.ndarray:
    indexes = np.arange(sample_count, dtype=float)
    offsets = np.arange(count, dtype=float) * step_hz
    result = np.exp((-2j * np.pi * offsets[:, None]) * indexes[None, :] / sample_rate_hz)
    result.flags.writeable = False
    return result


def _folded_anchor_scores(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    absolute_cfo_hz: float,
    symbols: tuple[int, ...],
    epoch_count: int,
) -> np.ndarray:
    indexes = np.arange(values.size, dtype=float)
    derotated = values * np.exp(-2j * np.pi * absolute_cfo_hz * indexes / sample_rate_hz)
    return _folded_anchor_scores_derotated(
        derotated, template, sample_rate_hz, symbols, epoch_count
    )


def _folded_anchor_score_grid(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    absolute_cfo_hz: tuple[float, ...],
    symbols: tuple[int, ...],
    epoch_count: int,
) -> tuple[np.ndarray, ...]:
    if not absolute_cfo_hz:
        return ()
    native_grid = getattr(_native_acquisition, "folded_anchor_score_grid", None)
    if native_grid is not None:
        return _folded_anchor_score_grid_native(
            values,
            template,
            sample_rate_hz,
            absolute_cfo_hz,
            symbols,
            epoch_count,
        )
    rotation = _cached_dense_rotation_bank(
        float(sample_rate_hz), values.size, tuple(float(value) for value in absolute_cfo_hz)
    )
    # CFO derotation has unit magnitude, so every hypothesis has the same
    # sliding received-energy denominator.  Computing it once avoids repeating
    # the second convolution for every coarse CFO basin.
    power_prefix = _power_prefix(values)
    return tuple(
        _folded_anchor_scores_derotated(
            values * rotation[index],
            template,
            sample_rate_hz,
            symbols,
            epoch_count,
            power_prefix=power_prefix,
        )
        for index in range(len(absolute_cfo_hz))
    )


def _folded_anchor_score_grid_native(
    values: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    absolute_cfo_hz: tuple[float, ...],
    symbols: tuple[int, ...],
    epoch_count: int,
    *,
    backend: str = "auto",
) -> tuple[np.ndarray, ...]:
    """Evaluate the full coarse grid while sharing CFO-invariant native work."""

    backend_functions = {
        "auto": "folded_anchor_score_grid",
        "portable": "folded_anchor_score_grid_portable",
        "avx2_fma": "folded_anchor_score_grid_avx2_fma",
    }
    try:
        function_name = backend_functions[backend]
    except KeyError as error:
        raise ValueError(
            "native acquisition backend must be auto, portable, or avx2_fma"
        ) from error
    native_grid = getattr(_native_acquisition, function_name, None)
    if native_grid is None:
        raise RuntimeError(f"the {backend} batched native acquisition backend is unavailable")
    period = sample_rate_hz / FRAME_RATE_HZ
    local_starts = np.fromiter(
        (round(symbol * sample_rate_hz * OFDM_SYMBOL_DURATION_S) for symbol in symbols),
        dtype=np.intp,
    )
    local_stops = np.fromiter(
        (round((symbol + 1) * sample_rate_hz * OFDM_SYMBOL_DURATION_S) for symbol in symbols),
        dtype=np.intp,
    )
    frame_offsets = []
    frame = 0
    while (offset := round(frame * period)) < values.size:
        frame_offsets.append(offset)
        frame += 1
    scientific_cfo_count = len(absolute_cfo_hz)
    execution_cfo_hz = absolute_cfo_hz
    step = _constant_grid_step(absolute_cfo_hz)
    if scientific_cfo_count == 11 and step is not None:
        # Standard has 11 scientific CFO rows. A twelfth discarded execution
        # lane gives the AVX2/FMA kernel a materially better vector shape while
        # leaving the searched grid and returned inventory unchanged.
        execution_cfo_hz = (*absolute_cfo_hz, absolute_cfo_hz[-1] + step)
    scores = native_grid(
        np.asarray(values, dtype=np.complex128),
        np.asarray(template, dtype=np.complex128),
        np.asarray(execution_cfo_hz, dtype=float),
        local_starts,
        local_stops,
        np.asarray(frame_offsets, dtype=np.intp),
        _power_prefix(values),
        float(sample_rate_hz),
        epoch_count,
    )
    return tuple(scores[index] for index in range(scientific_cfo_count))


def _folded_anchor_score_grid_backend() -> str:
    """Return the native backend selected for this process."""

    selected = getattr(_native_acquisition, "folded_anchor_score_grid_backend", None)
    return str(selected()) if selected is not None else "unavailable"


def _folded_anchor_scores_derotated(
    derotated: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    symbols: tuple[int, ...],
    epoch_count: int,
    *,
    power_prefix: np.ndarray | None = None,
) -> np.ndarray:
    received_power_prefix = _power_prefix(derotated) if power_prefix is None else power_prefix
    if _native_acquisition is not None:
        return _folded_anchor_scores_derotated_native(
            derotated,
            template,
            sample_rate_hz,
            symbols,
            epoch_count,
            power_prefix=received_power_prefix,
        )
    return _folded_anchor_scores_derotated_python(
        derotated,
        template,
        sample_rate_hz,
        symbols,
        epoch_count,
        power_prefix=received_power_prefix,
    )


def _folded_anchor_scores_derotated_native(
    derotated: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    symbols: tuple[int, ...],
    epoch_count: int,
    *,
    power_prefix: np.ndarray | None = None,
) -> np.ndarray:
    """Native implementation paired with the readable Python oracle below."""

    if _native_acquisition is None:
        raise RuntimeError("the native acquisition extension is unavailable")
    period = sample_rate_hz / FRAME_RATE_HZ
    local_starts = np.fromiter(
        (round(symbol * sample_rate_hz * OFDM_SYMBOL_DURATION_S) for symbol in symbols),
        dtype=np.intp,
    )
    local_stops = np.fromiter(
        (round((symbol + 1) * sample_rate_hz * OFDM_SYMBOL_DURATION_S) for symbol in symbols),
        dtype=np.intp,
    )
    frame_offsets = []
    frame = 0
    while (offset := round(frame * period)) < derotated.size:
        frame_offsets.append(offset)
        frame += 1
    received_power_prefix = _power_prefix(derotated) if power_prefix is None else power_prefix
    return _native_acquisition.folded_anchor_scores(
        np.asarray(derotated, dtype=np.complex128),
        np.asarray(template, dtype=np.complex128),
        local_starts,
        local_stops,
        np.asarray(frame_offsets, dtype=np.intp),
        received_power_prefix,
        epoch_count,
    )


def _folded_anchor_scores_derotated_python(
    derotated: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    symbols: tuple[int, ...],
    epoch_count: int,
    *,
    power_prefix: np.ndarray | None = None,
) -> np.ndarray:
    """Readable numerical oracle for the fused native anchor kernel."""

    scores = np.zeros(epoch_count, dtype=float)
    support = np.zeros(epoch_count, dtype=np.int32)
    period = sample_rate_hz / FRAME_RATE_HZ
    received_power_prefix = _power_prefix(derotated) if power_prefix is None else power_prefix
    epoch_indexes = np.arange(epoch_count)
    reference_groups: dict[int, list[tuple[int, np.ndarray]]] = {}
    for symbol in symbols:
        local_start = round(symbol * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
        local_stop = round((symbol + 1) * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
        reference = template[local_start:local_stop]
        reference_groups.setdefault(reference.size, []).append((local_start, reference))

    for reference_size, group in reference_groups.items():
        references = np.stack(tuple(reference for _, reference in group), axis=0)
        # One strided window matrix times the complete same-size reference bank
        # replaces independent correlations for every anchor symbol.
        correlations = sliding_window_view(derotated, reference_size) @ np.conj(references.T)
        energy = np.maximum(
            received_power_prefix[reference_size:] - received_power_prefix[:-reference_size],
            0.0,
        )
        reference_energy = np.sum(np.abs(references) ** 2, axis=1)
        denominator = np.sqrt(energy[:, None] * reference_energy[None, :])
        normalized_group = np.divide(
            np.abs(correlations),
            denominator,
            out=np.zeros_like(denominator),
            where=denominator > 0,
        )
        for column, (local_start, _) in enumerate(group):
            normalized = normalized_group[:, column]
            frame = 0
            while True:
                starts = epoch_indexes + local_start + round(frame * period)
                valid = starts < normalized.size
                if not np.any(valid):
                    break
                scores[valid] += normalized[starts[valid]]
                support[valid] += 1
                frame += 1
    return np.divide(scores, support, out=np.zeros_like(scores), where=support > 0)


def _power_prefix(values: np.ndarray) -> np.ndarray:
    """Return a sliding-energy prefix without materializing a ones kernel."""

    power = values.real * values.real + values.imag * values.imag
    result = np.empty(power.size + 1, dtype=float)
    result[0] = 0.0
    np.cumsum(power, out=result[1:])
    return result


@lru_cache(maxsize=8)
def _cached_dense_offset_rotation(
    sample_rate_hz: float,
    sample_count: int,
    count: int,
    step_hz: float,
) -> np.ndarray:
    indexes = np.arange(sample_count, dtype=float)
    offsets = np.arange(count, dtype=float) * step_hz
    result = np.exp((-2j * np.pi * offsets[:, None]) * indexes[None, :] / sample_rate_hz)
    result.flags.writeable = False
    return result


@lru_cache(maxsize=4)
def _cached_dense_rotation_bank(
    sample_rate_hz: float,
    sample_count: int,
    cfo_hz: tuple[float, ...],
) -> np.ndarray:
    """Cache the exact coarse bank reused by every same-geometry probe."""

    indexes = np.arange(sample_count, dtype=float)
    step = _constant_grid_step(cfo_hz)
    if step is None:
        result = np.exp(
            (-2j * np.pi * np.asarray(cfo_hz)[:, None]) * indexes[None, :] / sample_rate_hz
        )
    else:
        base = np.exp(-2j * np.pi * cfo_hz[0] * indexes / sample_rate_hz)
        result = (
            _cached_dense_offset_rotation(sample_rate_hz, sample_count, len(cfo_hz), step)
            * base[None, :]
        )
    result.flags.writeable = False
    return result


def _empty_result(
    status: NumericalStatus,
    calibration: ReceiverFrequencyCalibration,
    edge: StarlinkEdge,
    sample_rate_hz: float,
    sample_count: int,
    reason: str,
) -> SymbolwiseAcquisitionResult:
    return SymbolwiseAcquisitionResult(
        status,
        calibration,
        edge,
        float(sample_rate_hz),
        int(sample_count),
        (),
        reason,
    )


@lru_cache(maxsize=32)
def _pilot_sample_indexes(sample_rate_hz: float, symbols: tuple[int, ...]) -> np.ndarray:
    """Return immutable pilot indexes reused across every CFO hypothesis."""

    result = np.concatenate(
        tuple(
            np.arange(
                round(symbol * sample_rate_hz * OFDM_SYMBOL_DURATION_S),
                round((symbol + 1) * sample_rate_hz * OFDM_SYMBOL_DURATION_S),
            )
            for symbol in symbols
        )
    )
    result.flags.writeable = False
    return result


def _local_peak_indexes(scores: np.ndarray) -> tuple[int, ...]:
    if not scores.size:
        return ()
    if scores.size == 1:
        return (0,) if scores[0] > 0 else ()
    left = np.empty_like(scores)
    right = np.empty_like(scores)
    left[0] = -math.inf
    left[1:] = scores[:-1]
    right[-1] = -math.inf
    right[:-1] = scores[1:]
    selected = (scores >= left) & (scores >= right) & ((scores > left) | (scores > right))
    return tuple(int(index) for index in np.flatnonzero(selected))


def _circular_local_peak_indexes(scores: np.ndarray) -> tuple[int, ...]:
    """Return deterministic local maxima on a circular epoch domain."""

    if not scores.size:
        return ()
    if scores.size == 1:
        return (0,) if scores[0] > 0 else ()
    left = np.roll(scores, 1)
    right = np.roll(scores, -1)
    selected = (scores >= left) & (scores >= right) & ((scores > left) | (scores > right))
    return tuple(int(index) for index in np.flatnonzero(selected))


def _refine_circular_epoch(scores: np.ndarray, epoch: int) -> int:
    """Refine one sample on either side without breaking at the frame seam."""

    count = len(scores)
    choices = ((epoch - 1) % count, epoch % count, (epoch + 1) % count)
    return max(choices, key=lambda candidate: (scores[candidate], -candidate))


def _retain_separated(
    peaks: list[tuple[float, int, float]],
    count: int,
    epoch_separation: int,
    cfo_separation: float,
    epoch_count: int,
) -> tuple[tuple[float, int, float], ...]:
    retained: list[tuple[float, int, float]] = []
    for candidate in peaks:
        _, epoch, cfo = candidate
        for _, other_epoch, other_cfo in retained:
            epoch_distance = min(abs(epoch - other_epoch), epoch_count - abs(epoch - other_epoch))
            if epoch_distance < epoch_separation and abs(cfo - other_cfo) <= cfo_separation:
                break
        else:
            retained.append(candidate)
            if len(retained) == count:
                break
    return tuple(retained)


def _refine_epoch(scores: np.ndarray, epoch: int, epoch_count: int) -> int:
    choices = range(max(0, epoch - 1), min(epoch_count - 1, epoch + 1) + 1)
    return max(choices, key=lambda candidate: (scores[candidate], -candidate))


def _quadratic_peak(grid: tuple[float, ...], scores: tuple[float, ...], index: int) -> float:
    if index == 0 or index + 1 == len(grid):
        return grid[index]
    left, center, right = scores[index - 1 : index + 2]
    curvature = left - 2 * center + right
    if not math.isfinite(curvature) or curvature >= -1e-15:
        return grid[index]
    step = grid[index + 1] - grid[index]
    offset = min(step, max(-step, 0.5 * (left - right) / curvature * step))
    return float(grid[index] + offset)


def _bounded_grid(start: float, stop: float, step: float) -> tuple[float, ...]:
    count = math.floor((stop - start) / step + 1e-12)
    values = [float(start + index * step) for index in range(count + 1)]
    if not math.isclose(values[-1], stop, rel_tol=0, abs_tol=1e-9):
        values.append(float(stop))
    return tuple(values)


def _validate_symbols(values: tuple[int, ...], name: str) -> None:
    if (
        not values
        or tuple(sorted(set(values))) != values
        or any(isinstance(value, bool) or not isinstance(value, int) for value in values)
        or values[0] < 2
        or values[-1] > 301
    ):
        raise ValueError(f"{name} must be a sorted unique subset of 2..301")
