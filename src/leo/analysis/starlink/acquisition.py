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


def acquire_symbolwise(
    samples: np.ndarray,
    sample_rate_hz: float,
    calibration: ReceiverFrequencyCalibration,
    *,
    edge: StarlinkEdge | str = StarlinkEdge.LOWER,
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
    """Vectorized equivalent of ``normalized_frame_score`` over one CFO grid."""

    if not absolute_cfo_hz:
        return ()
    sample_indexes = _pilot_sample_indexes(sample_rate_hz, symbols)
    references = template[sample_indexes]
    template_energy = float(np.vdot(references, references).real)
    received_frames: list[np.ndarray] = []
    denominators: list[float] = []
    period = sample_rate_hz / FRAME_RATE_HZ
    frame = 0
    while True:
        start = epoch_sample + round(frame * period)
        absolute = start + sample_indexes
        if absolute[-1] >= values.size:
            break
        received = values[absolute]
        received_frames.append(received)
        denominators.append(math.sqrt(template_energy * float(np.vdot(received, received).real)))
        frame += 1
    if not received_frames:
        return tuple(0.0 for _ in absolute_cfo_hz)
    rotation = _normalized_rotation_bank(
        sample_rate_hz,
        symbols,
        absolute_cfo_hz,
        sample_indexes,
    )
    received = np.stack(received_frames, axis=0)
    correlations = np.einsum(
        "cn,fn->cf",
        rotation,
        received * np.conj(references)[None, :],
        optimize=False,
    )
    denominator = np.asarray(denominators, dtype=float)
    scores = np.divide(
        np.abs(correlations),
        denominator[None, :],
        out=np.zeros_like(correlations.real),
        where=denominator[None, :] > 0,
    )
    return tuple(float(value) for value in np.mean(scores, axis=1))


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
    denominators: list[float] = []
    frame = 0
    while True:
        start = epoch_sample + round(frame * period)
        if start + template.size > values.size:
            break
        segment = values[start : start + template.size]
        segments.append(segment)
        denominators.append(math.sqrt(template_energy * float(np.vdot(segment, segment).real)))
        frame += 1
    if not segments:
        return tuple(0.0 for _ in absolute_cfo_hz)
    local_indexes = np.arange(template.size, dtype=float)
    rotation = _conditioned_rotation_bank(
        sample_rate_hz,
        template.size,
        absolute_cfo_hz,
        local_indexes,
    )
    received = np.stack(segments, axis=0)
    correlations = np.einsum(
        "cn,fn->cf",
        rotation,
        received * np.conj(template)[None, :],
        optimize=False,
    )
    denominator = np.asarray(denominators, dtype=float)
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


def _folded_anchor_scores_derotated(
    derotated: np.ndarray,
    template: np.ndarray,
    sample_rate_hz: float,
    symbols: tuple[int, ...],
    epoch_count: int,
    *,
    power_prefix: np.ndarray | None = None,
) -> np.ndarray:
    scores = np.zeros(epoch_count, dtype=float)
    support = np.zeros(epoch_count, dtype=np.int32)
    period = sample_rate_hz / FRAME_RATE_HZ
    received_power_prefix = _power_prefix(derotated) if power_prefix is None else power_prefix
    epoch_indexes = np.arange(epoch_count)
    for symbol in symbols:
        local_start = round(symbol * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
        local_stop = round((symbol + 1) * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
        reference = template[local_start:local_stop]
        correlation = np.correlate(derotated, reference, mode="valid")
        energy = np.maximum(
            received_power_prefix[reference.size :] - received_power_prefix[: -reference.size],
            0.0,
        )
        denominator = np.sqrt(float(np.vdot(reference, reference).real) * energy)
        normalized = np.divide(
            np.abs(correlation),
            denominator,
            out=np.zeros_like(denominator),
            where=denominator > 0,
        )
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
    if scores.size == 1:
        return (0,) if scores[0] > 0 else ()
    result = []
    for index, score in enumerate(scores):
        left = scores[index - 1] if index else -math.inf
        right = scores[index + 1] if index + 1 < scores.size else -math.inf
        if score >= left and score >= right and (score > left or score > right):
            result.append(index)
    return tuple(result)


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
