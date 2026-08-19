"""Bounded Doppler fitting, de-Doppler, and optional TLE association contracts."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import StrEnum

import numpy as np

from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.long_dwell import RefinedCandidate, ScientificConfidence
from leo.contracts.digests import canonical_digest


class MotionClass(StrEnum):
    DYNAMIC = "dynamic"
    STATIONARY_CONFOUNDER = "stationary_confounder"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class DopplerFitConfig:
    polynomial_order: int = 1
    minimum_points: int = 3
    maximum_points: int = 2048
    stationary_slope_limit_hz_s: float = 5.0
    stationary_excursion_limit_hz: float = 100.0
    maximum_residual_rms_hz: float = 5_000.0

    def __post_init__(self) -> None:
        if self.polynomial_order not in (1, 2):
            raise ValueError("polynomial_order must be one or two")
        if self.minimum_points < self.polynomial_order + 2:
            raise ValueError("minimum_points is too small for the fit")
        if self.maximum_points < self.minimum_points:
            raise ValueError("maximum_points must be at least minimum_points")
        limits = (
            self.stationary_slope_limit_hz_s,
            self.stationary_excursion_limit_hz,
            self.maximum_residual_rms_hz,
        )
        if any(not math.isfinite(value) or value < 0 for value in limits):
            raise ValueError("Doppler limits must be finite and nonnegative")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class DopplerFitResult:
    status: NumericalStatus
    config_digest: str
    reference_time_s: float | None
    frequency_at_reference_hz: float | None
    slope_hz_s: float | None
    acceleration_hz_s2: float | None
    residual_rms_hz: float | None
    point_count: int
    time_coverage_s: float
    motion_class: MotionClass
    confidence: ScientificConfidence
    source_candidate_ids: tuple[str, ...]
    reason: str

    def frequency_hz(self, time_s: np.ndarray | float) -> np.ndarray:
        if self.status is not NumericalStatus.COMPLETE or self.reference_time_s is None:
            raise ValueError("Doppler fit is unavailable")
        assert self.frequency_at_reference_hz is not None
        assert self.slope_hz_s is not None
        assert self.acceleration_hz_s2 is not None
        values = np.asarray(time_s, dtype=float)
        delta = values - self.reference_time_s
        return (
            self.frequency_at_reference_hz
            + self.slope_hz_s * delta
            + 0.5 * self.acceleration_hz_s2 * delta**2
        )


def fit_doppler(
    candidates: tuple[RefinedCandidate, ...],
    sample_rate_hz: float,
    config: DopplerFitConfig,
) -> DopplerFitResult:
    """Fit receiver-calibrated absolute CFO as a function of dwell time."""

    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    ordered = sorted(candidates, key=lambda item: item.absolute_epoch_sample)
    if len(ordered) > config.maximum_points:
        step = (len(ordered) - 1) / (config.maximum_points - 1)
        ordered = [ordered[round(index * step)] for index in range(config.maximum_points)]
    if len(ordered) < config.minimum_points:
        return DopplerFitResult(
            NumericalStatus.INSUFFICIENT,
            config.digest,
            None,
            None,
            None,
            None,
            None,
            len(ordered),
            0.0,
            MotionClass.INDETERMINATE,
            ScientificConfidence.INSUFFICIENT,
            tuple(item.candidate_id for item in ordered),
            "too few dense candidates for Doppler fitting",
        )
    times = np.asarray([item.absolute_epoch_sample / sample_rate_hz for item in ordered])
    frequencies = np.asarray([item.absolute_cfo_hz for item in ordered])
    reference = float(np.mean(times))
    delta = times - reference
    columns = [np.ones_like(delta), delta]
    if config.polynomial_order == 2:
        columns.append(0.5 * delta**2)
    design = np.column_stack(columns)
    weights = np.asarray(
        [max(item.verify_minus_control_margin, 1e-6) for item in ordered], dtype=float
    )
    weighted_design = design * np.sqrt(weights)[:, None]
    weighted_frequency = frequencies * np.sqrt(weights)
    coefficients = np.linalg.lstsq(weighted_design, weighted_frequency, rcond=None)[0]
    predicted = design @ coefficients
    residual_rms = float(np.sqrt(np.average((frequencies - predicted) ** 2, weights=weights)))
    slope = float(coefficients[1])
    acceleration = float(coefficients[2]) if config.polynomial_order == 2 else 0.0
    excursion = float(np.ptp(predicted))
    coverage = float(times[-1] - times[0])
    stationary = (
        abs(slope) <= config.stationary_slope_limit_hz_s
        and excursion <= config.stationary_excursion_limit_hz
    )
    if stationary:
        motion = MotionClass.STATIONARY_CONFOUNDER
        confidence = ScientificConfidence.REJECTED
        reason = "frequency evolution is consistent with a stationary interferer"
    elif residual_rms > config.maximum_residual_rms_hz:
        motion = MotionClass.INDETERMINATE
        confidence = ScientificConfidence.CANDIDATE
        reason = "Doppler residual exceeds the configured research gate"
    else:
        motion = MotionClass.DYNAMIC
        confidence = ScientificConfidence.CANDIDATE
        reason = "dynamic CFO track; association and controls remain candidate-only"
    return DopplerFitResult(
        NumericalStatus.COMPLETE,
        config.digest,
        reference,
        float(coefficients[0]),
        slope,
        acceleration,
        residual_rms,
        len(ordered),
        coverage,
        motion,
        confidence,
        tuple(item.candidate_id for item in ordered),
        reason,
    )


@dataclass(frozen=True, slots=True)
class LockedFrame:
    source_id: str
    absolute_sample_start: int
    samples: np.ndarray


@dataclass(frozen=True, slots=True)
class LockedIntegrationConfig:
    maximum_frames: int = 256
    maximum_frame_samples: int = 50_000
    minimum_frames: int = 2

    def __post_init__(self) -> None:
        if self.minimum_frames < 2 or self.maximum_frames < self.minimum_frames:
            raise ValueError("locked frame bounds must allow at least two frames")
        if self.maximum_frame_samples <= 0:
            raise ValueError("maximum_frame_samples must be positive")

    @property
    def digest(self) -> str:
        return canonical_digest(asdict(self))


@dataclass(frozen=True, slots=True)
class LockedIntegrationResult:
    status: NumericalStatus
    config_digest: str
    integrated: np.ndarray
    frame_count: int
    coherent_power: float | None
    incoherent_power: float | None
    coherent_gain_db: float | None
    source_ids: tuple[str, ...]
    maximum_working_set_bytes: int
    confidence: ScientificConfidence
    reason: str


def dedoppler_locked_integration(
    frames: tuple[LockedFrame, ...],
    sample_rate_hz: float,
    doppler: DopplerFitResult,
    config: LockedIntegrationConfig,
    *,
    reference_template: np.ndarray | None = None,
) -> LockedIntegrationResult:
    """De-Doppler, phase-lock, and average a bounded set of equal-size frames."""

    if len(frames) > config.maximum_frames:
        raise ValueError("locked integration exceeds maximum_frames")
    if not frames or doppler.status is not NumericalStatus.COMPLETE:
        return _empty_locked(config, "Doppler model or frames are unavailable")
    length = len(frames[0].samples)
    if length == 0 or length > config.maximum_frame_samples:
        raise ValueError("locked frame length lies outside its budget")
    if any(np.asarray(frame.samples).shape != (length,) for frame in frames):
        raise ValueError("locked frames must have equal one-dimensional shape")
    if len(frames) < config.minimum_frames:
        return _empty_locked(config, "too few frames for locked integration")
    if reference_template is not None and np.asarray(reference_template).shape != (length,):
        raise ValueError("reference template shape differs from locked frames")
    assert doppler.reference_time_s is not None
    assert doppler.frequency_at_reference_hz is not None
    assert doppler.slope_hz_s is not None
    assert doppler.acceleration_hz_s2 is not None
    corrected = np.empty((len(frames), length), dtype=np.complex128)
    incoherent = 0.0
    phase_reference = (
        None if reference_template is None else np.asarray(reference_template, dtype=np.complex128)
    )
    for frame_index, frame in enumerate(frames):
        values = np.asarray(frame.samples, dtype=np.complex128)
        absolute_time = (frame.absolute_sample_start + np.arange(length)) / sample_rate_hz
        delta = absolute_time - doppler.reference_time_s
        phase_cycles = (
            doppler.frequency_at_reference_hz * delta
            + 0.5 * doppler.slope_hz_s * delta**2
            + doppler.acceleration_hz_s2 * delta**3 / 6
        )
        row = values * np.exp(-2j * np.pi * phase_cycles)
        if phase_reference is None:
            phase_reference = row.copy()
        match = np.vdot(phase_reference, row)
        row *= np.exp(-1j * np.angle(match))
        corrected[frame_index] = row
        incoherent += float(np.mean(np.abs(row) ** 2))
    integrated = np.mean(corrected, axis=0)
    coherent = float(np.mean(np.abs(integrated) ** 2))
    incoherent /= len(frames)
    gain = (
        10 * math.log10(len(frames) * coherent / incoherent)
        if coherent > 0 and incoherent > 0
        else None
    )
    integrated.flags.writeable = False
    return LockedIntegrationResult(
        NumericalStatus.COMPLETE,
        config.digest,
        integrated,
        len(frames),
        coherent,
        incoherent,
        gain,
        tuple(frame.source_id for frame in frames),
        corrected.nbytes + integrated.nbytes,
        doppler.confidence,
        "de-Doppler locked integration; scientific controls remain required",
    )


class TleAssociationStatus(StrEnum):
    UNAVAILABLE = "unavailable"
    NO_MATCH = "no_match"
    CANDIDATE = "candidate"


@dataclass(frozen=True, slots=True)
class TlePrediction:
    object_id: str
    epoch_utc: str
    frequency_at_reference_hz: float
    slope_hz_s: float
    acceleration_hz_s2: float = 0.0


@dataclass(frozen=True, slots=True)
class TleAssociationResult:
    status: TleAssociationStatus
    object_id: str | None
    frequency_residual_hz: float | None
    slope_residual_hz_s: float | None
    prediction_epoch_utc: str | None
    candidate_only: bool
    reason: str


def associate_tle_candidate(
    doppler: DopplerFitResult,
    predictions: tuple[TlePrediction, ...] | None,
    *,
    maximum_frequency_residual_hz: float,
    maximum_slope_residual_hz_s: float,
) -> TleAssociationResult:
    """Associate against externally produced predictions; no propagation occurs here."""

    if (
        not math.isfinite(maximum_frequency_residual_hz)
        or maximum_frequency_residual_hz <= 0
        or not math.isfinite(maximum_slope_residual_hz_s)
        or maximum_slope_residual_hz_s <= 0
    ):
        raise ValueError("TLE association residual bounds must be finite and positive")
    if not predictions:
        return TleAssociationResult(
            TleAssociationStatus.UNAVAILABLE,
            None,
            None,
            None,
            None,
            True,
            "TLE predictions were not supplied",
        )
    if doppler.status is not NumericalStatus.COMPLETE:
        return TleAssociationResult(
            TleAssociationStatus.UNAVAILABLE,
            None,
            None,
            None,
            None,
            True,
            "Doppler fit is unavailable",
        )
    assert doppler.frequency_at_reference_hz is not None
    assert doppler.slope_hz_s is not None
    ranked = sorted(
        (
            (
                math.hypot(
                    (doppler.frequency_at_reference_hz - item.frequency_at_reference_hz)
                    / maximum_frequency_residual_hz,
                    (doppler.slope_hz_s - item.slope_hz_s) / maximum_slope_residual_hz_s,
                ),
                item,
            )
            for item in predictions
        ),
        key=lambda pair: (pair[0], pair[1].object_id),
    )
    _, best = ranked[0]
    frequency_residual = doppler.frequency_at_reference_hz - best.frequency_at_reference_hz
    slope_residual = doppler.slope_hz_s - best.slope_hz_s
    accepted = (
        abs(frequency_residual) <= maximum_frequency_residual_hz
        and abs(slope_residual) <= maximum_slope_residual_hz_s
    )
    return TleAssociationResult(
        TleAssociationStatus.CANDIDATE if accepted else TleAssociationStatus.NO_MATCH,
        best.object_id if accepted else None,
        frequency_residual,
        slope_residual,
        best.epoch_utc,
        True,
        "nearest externally supplied prediction" if accepted else "no prediction passed bounds",
    )


def _empty_locked(config: LockedIntegrationConfig, reason: str) -> LockedIntegrationResult:
    output = np.empty(0, dtype=np.complex128)
    output.flags.writeable = False
    return LockedIntegrationResult(
        NumericalStatus.INSUFFICIENT,
        config.digest,
        output,
        0,
        None,
        None,
        None,
        (),
        0,
        ScientificConfidence.INSUFFICIENT,
        reason,
    )
