"""Raw-IQ GLRT trajectory and reset-debiased local CFO-rate analysis.

The persisted GLRT trajectory supplies track membership and the overall rate.
Raw source candidates supply the acquisition CFO and timing epoch.  Complete
1.333 ms Qin frames are then re-estimated from IQ, joined into frequency-
continuous ramps, and fit with one free CFO intercept per ramp.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Protocol

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink.local_doppler import frequency_line, line_slope_sigma
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.analysis.starlink.templates import StarlinkEdge


class RandomAccessIqReader(Protocol):
    """Narrow raw-IQ port required by the dwell-rate analyzer."""

    @property
    def sample_rate_hz(self) -> int: ...

    @property
    def sample_count(self) -> int: ...

    def read(
        self,
        sample_start: int,
        sample_count: int,
        *,
        receiver_ids: tuple[int, ...] | None = None,
    ) -> npt.NDArray[np.int16]: ...


class DwellDopplerStatus(StrEnum):
    COMPLETE = "complete"
    INSUFFICIENT_GLRT_SUPPORT = "insufficient_glrt_support"
    INSUFFICIENT_FRAME_SUPPORT = "insufficient_frame_support"
    INSUFFICIENT_RAMP_SUPPORT = "insufficient_ramp_support"
    UNSTABLE_LOCAL_RATE = "unstable_local_rate"
    VALIDATION_FAILED = "validation_failed"


@dataclass(frozen=True, slots=True)
class DwellDopplerConfig:
    frame_exact_gate: float = 0.20
    frame_gate_sweep: tuple[float, ...] = (0.10, 0.15, 0.20, 0.25, 0.30)
    glrt_exact_gate: float = 0.10
    residual_half_width_hz: float = 6_000.0
    residual_step_hz: float = 25.0
    minimum_glrt_windows: int = 12
    minimum_glrt_span_s: float = 0.25
    minimum_frames_per_lock: int = 6
    maximum_joined_span_s: float = 0.125
    maximum_joined_frame_gap_s: float = 0.016
    maximum_joined_locks: int = 8
    minimum_ramp_span_s: float = 0.020
    maximum_ramp_raw_rms_hz: float = 40.0
    minimum_ramps: int = 3
    maximum_practical_sigma_hz_s: float = 1_000.0
    maximum_gate_spread_hz_s: float = 1_000.0
    validation_tolerance_fraction: float = 0.05
    bootstrap_replicates: int = 4_000
    bootstrap_seed: int = 20260824

    def __post_init__(self) -> None:
        positive = (
            self.residual_half_width_hz,
            self.residual_step_hz,
            self.minimum_glrt_span_s,
            self.maximum_joined_span_s,
            self.maximum_joined_frame_gap_s,
            self.minimum_ramp_span_s,
            self.maximum_ramp_raw_rms_hz,
            self.maximum_practical_sigma_hz_s,
            self.maximum_gate_spread_hz_s,
            self.validation_tolerance_fraction,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("dwell Doppler positive thresholds must be finite")
        counts = (
            self.minimum_glrt_windows,
            self.minimum_frames_per_lock,
            self.maximum_joined_locks,
            self.minimum_ramps,
            self.bootstrap_replicates,
        )
        if any(value < 1 for value in counts):
            raise ValueError("dwell Doppler count thresholds must be positive")
        gates = (self.frame_exact_gate, self.glrt_exact_gate, *self.frame_gate_sweep)
        if any(not 0.0 < value <= 1.0 for value in gates):
            raise ValueError("Qin gates must lie in (0, 1]")
        cells = 2.0 * self.residual_half_width_hz / self.residual_step_hz
        if not math.isclose(cells, round(cells), abs_tol=1e-9):
            raise ValueError("residual search width must be divisible by its step")


@dataclass(frozen=True, slots=True)
class GlrtProbe:
    probe_index: int
    detection_time_s: float
    detection_sample_start: int
    local_epoch_sample: int
    source_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float

    @property
    def aligned_sample_start(self) -> int:
        return self.detection_sample_start + self.local_epoch_sample


@dataclass(frozen=True, slots=True)
class DwellDopplerTrackInput:
    branch_id: str
    stream_id: str
    receiver_id: int
    edge: StarlinkEdge
    start_s: float
    end_s: float
    reference_time_s: float
    glrt_coefficients_hz: tuple[float, float]
    glrt_rate_sigma_hz_s: float | None
    probe_samples: int
    probes: tuple[GlrtProbe, ...]

    @property
    def overall_glrt_rate_hz_s(self) -> float:
        return self.glrt_coefficients_hz[0]


@dataclass(frozen=True, slots=True)
class FrameCfoMeasurement:
    row_index: int
    probe_index: int
    time_s: float
    train_cfo_hz: float
    validation_cfo_hz: float
    train_exact_score: float
    train_control_score: float
    residual_grid_edge: bool

    @property
    def train_margin(self) -> float:
        return self.train_exact_score - self.train_control_score


@dataclass(frozen=True, slots=True)
class RampFit:
    source_probe_start: int
    source_probe_end: int
    observation_indices: tuple[int, ...]
    frame_count: int
    start_time_s: float
    end_time_s: float
    center_time_s: float
    intercept_hz: float
    slope_hz_s: float
    slope_sigma_hz_s: float | None
    raw_rms_hz: float

    @property
    def span_s(self) -> float:
        return self.end_time_s - self.start_time_s


@dataclass(frozen=True, slots=True)
class JointRampFit:
    reference_time_s: float
    shared_slope_hz_s: float
    shared_slope_sigma_hz_s: float
    slope_progression_hz_s2: float | None
    slope_progression_sigma_hz_s2: float | None
    residual_rms_hz: float
    bic: float
    ramp_intercepts_hz: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class DwellDopplerResult:
    status: DwellDopplerStatus
    reason: str
    track: DwellDopplerTrackInput
    frames: tuple[FrameCfoMeasurement, ...]
    ramps: tuple[RampFit, ...]
    diagnostics: dict[str, object]

    def document(self, *, include_frames: bool = True) -> dict[str, object]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "track": {
                **asdict(self.track),
                "edge": self.track.edge.value,
            },
            "frames": [asdict(item) for item in self.frames] if include_frames else [],
            "ramps": [asdict(item) for item in self.ramps],
            "diagnostics": self.diagnostics,
        }


def _complex_receiver(values: npt.NDArray[np.int16]) -> npt.NDArray[np.complex128]:
    if values.ndim != 3 or values.shape[1:] != (1, 2):
        raise ValueError("one-receiver CI16 data must have shape (samples, 1, 2)")
    return np.asarray(
        (values[:, 0, 0].astype(np.float64) + 1j * values[:, 0, 1].astype(np.float64)) / (2**15),
        dtype=np.complex128,
    )


def _frequency_powers(
    values: np.ndarray,
    times_s: np.ndarray,
    indexes: np.ndarray,
    residual_grid_hz: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    selected_times = np.asarray(times_s[:, indexes], dtype=float)
    lags = selected_times - np.mean(selected_times, axis=1, keepdims=True)
    if not np.allclose(lags, lags[:1], rtol=0.0, atol=2e-12):
        raise ValueError("frames do not share one within-frame symbol geometry")
    selected = np.asarray(values[:, indexes], dtype=np.complex128)
    phase_bank = np.exp(-2j * np.pi * lags[0, None, :] * residual_grid_hz[:, None])
    powers = np.abs(selected @ phase_bank.T) ** 2
    ceilings = np.sum(np.abs(selected), axis=1) ** 2
    return powers, ceilings, lags


def extract_frame_cfos(
    reader: RandomAccessIqReader,
    track: DwellDopplerTrackInput,
    config: DwellDopplerConfig,
) -> tuple[FrameCfoMeasurement, ...]:
    """Re-estimate complete even/odd Qin frame CFOs from raw IQ."""

    if reader.sample_rate_hz != 2_500_000:
        raise ValueError("dwell Doppler frame extraction currently requires 2.5 Msps")
    symbols = np.arange(2, 302, dtype=int)
    even = np.arange(0, len(symbols), 2, dtype=int)
    odd = np.arange(1, len(symbols), 2, dtype=int)
    cells = round(2.0 * config.residual_half_width_hz / config.residual_step_hz)
    residual_grid = np.linspace(
        -config.residual_half_width_hz,
        config.residual_half_width_hz,
        cells + 1,
    )
    output: list[FrameCfoMeasurement] = []
    for probe in track.probes:
        if probe.aligned_sample_start + track.probe_samples > reader.sample_count:
            continue
        raw = reader.read(
            probe.aligned_sample_start,
            track.probe_samples,
            receiver_ids=(track.receiver_id,),
        )
        workspace = _conditioned_correlation_workspace(
            _complex_receiver(raw),
            reader.sample_rate_hz,
            0,
            probe.source_cfo_hz,
            edge=track.edge,
            selected_symbols=symbols,
        )
        exact = workspace.select(symbols)
        control = workspace.select(symbols, control=True)
        if not exact.values.size or exact.values.shape != control.values.shape:
            continue
        even_power, even_ceiling, even_lags = _frequency_powers(
            exact.values, exact.times_s, even, residual_grid
        )
        odd_power, _odd_ceiling, _odd_lags = _frequency_powers(
            exact.values, exact.times_s, odd, residual_grid
        )
        train_indexes = np.argmax(even_power, axis=1)
        validation_indexes = np.argmax(odd_power, axis=1)
        control_selected = np.asarray(control.values[:, even], dtype=np.complex128)
        control_ceiling = np.sum(np.abs(control_selected), axis=1) ** 2
        selected_frequency = residual_grid[train_indexes]
        phase = np.exp(-2j * np.pi * even_lags * selected_frequency[:, None])
        control_power = np.abs(np.sum(control_selected * phase, axis=1)) ** 2
        absolute_offset_s = probe.aligned_sample_start / reader.sample_rate_hz
        for frame_index in range(exact.values.shape[0]):
            train_index = int(train_indexes[frame_index])
            validation_index = int(validation_indexes[frame_index])
            output.append(
                FrameCfoMeasurement(
                    row_index=len(output),
                    probe_index=probe.probe_index,
                    time_s=float(absolute_offset_s + np.mean(exact.times_s[frame_index])),
                    train_cfo_hz=float(probe.source_cfo_hz + residual_grid[train_index]),
                    validation_cfo_hz=float(probe.source_cfo_hz + residual_grid[validation_index]),
                    train_exact_score=float(
                        even_power[frame_index, train_index]
                        / max(float(even_ceiling[frame_index]), 1e-20)
                    ),
                    train_control_score=float(
                        control_power[frame_index] / max(float(control_ceiling[frame_index]), 1e-20)
                    ),
                    residual_grid_edge=train_index in {0, len(residual_grid) - 1},
                )
            )
    return tuple(output)


def _qualified_frames(
    frames: tuple[FrameCfoMeasurement, ...], exact_gate: float
) -> tuple[FrameCfoMeasurement, ...]:
    return tuple(
        item for item in frames if item.train_exact_score >= exact_gate and item.train_margin > 0.0
    )


def _fit_ramp(
    frames: tuple[FrameCfoMeasurement, ...],
    *,
    minimum_frames: int,
) -> RampFit | None:
    ordered = tuple(sorted(frames, key=lambda item: (item.time_s, item.row_index)))
    if len(ordered) < minimum_frames:
        return None
    times = np.asarray([item.time_s for item in ordered], dtype=float)
    values = np.asarray([item.train_cfo_hz for item in ordered], dtype=float)
    fit = frequency_line(times, values)
    if fit is None:
        return None
    predicted = fit.intercept_at_reference_hz + fit.slope_hz_per_s * (times - fit.reference_time_s)
    return RampFit(
        source_probe_start=min(item.probe_index for item in ordered),
        source_probe_end=max(item.probe_index for item in ordered),
        observation_indices=tuple(item.row_index for item in ordered),
        frame_count=len(ordered),
        start_time_s=float(times[0]),
        end_time_s=float(times[-1]),
        center_time_s=float(fit.reference_time_s),
        intercept_hz=float(fit.intercept_at_reference_hz),
        slope_hz_s=float(fit.slope_hz_per_s),
        slope_sigma_hz_s=line_slope_sigma(times, fit),
        raw_rms_hz=float(np.sqrt(np.mean((values - predicted) ** 2))),
    )


def independent_probe_fits(
    frames: tuple[FrameCfoMeasurement, ...], config: DwellDopplerConfig
) -> tuple[RampFit, ...]:
    grouped: dict[int, list[FrameCfoMeasurement]] = {}
    for item in frames:
        grouped.setdefault(item.probe_index, []).append(item)
    result = [
        _fit_ramp(tuple(grouped[index]), minimum_frames=config.minimum_frames_per_lock)
        for index in sorted(grouped)
    ]
    return tuple(item for item in result if item is not None)


def batch_joined_ramps(
    frames: tuple[FrameCfoMeasurement, ...],
    lock_fits: tuple[RampFit, ...],
    config: DwellDopplerConfig,
) -> tuple[RampFit, ...]:
    """Globally partition ordered locks, then retain frequency-coherent ramps."""

    if not lock_fits:
        return ()
    by_index = {item.row_index: item for item in frames}
    lock_rms = np.asarray([item.raw_rms_hz for item in lock_fits], dtype=float)
    noise_scale_hz = max(5.0, float(np.percentile(lock_rms, 90)))
    penalty = float(2.0 * math.log(max(2, len(frames))))
    candidate: dict[tuple[int, int], tuple[float, RampFit]] = {}
    count = len(lock_fits)
    for start in range(count):
        for end in range(start, min(count, start + config.maximum_joined_locks)):
            source = lock_fits[start : end + 1]
            indexes = [index for fit in source for index in fit.observation_indices]
            ordered = tuple(
                sorted(
                    (by_index[index] for index in indexes),
                    key=lambda item: item.time_s,
                )
            )
            times = np.asarray([item.time_s for item in ordered], dtype=float)
            if float(np.ptp(times)) > config.maximum_joined_span_s:
                break
            if len(times) > 1 and float(np.max(np.diff(times))) > config.maximum_joined_frame_gap_s:
                break
            fit = _fit_ramp(ordered, minimum_frames=config.minimum_frames_per_lock)
            if fit is None:
                continue
            values = np.asarray([item.train_cfo_hz for item in ordered], dtype=float)
            predicted = fit.intercept_hz + fit.slope_hz_s * (times - fit.center_time_s)
            standardized = (values - predicted) / noise_scale_hz
            loss = float(np.sum(np.minimum(standardized**2, 9.0)))
            candidate[start, end] = (loss + penalty, fit)
    objective = [math.inf] * (count + 1)
    predecessor: list[int | None] = [None] * (count + 1)
    objective[0] = 0.0
    for stop in range(1, count + 1):
        for start in range(max(0, stop - config.maximum_joined_locks), stop):
            proposed = candidate.get((start, stop - 1))
            if proposed is None:
                continue
            value = objective[start] + proposed[0]
            if value < objective[stop]:
                objective[stop] = value
                predecessor[stop] = start
    if predecessor[count] is None:
        return ()
    selected: list[RampFit] = []
    stop = count
    while stop:
        previous_stop = predecessor[stop]
        if previous_stop is None:
            return ()
        selected.append(candidate[previous_stop, stop - 1][1])
        stop = previous_stop
    partition = tuple(reversed(selected))
    return tuple(
        item
        for item in partition
        if item.span_s >= config.minimum_ramp_span_s
        and item.raw_rms_hz <= config.maximum_ramp_raw_rms_hz
    )


def _robust_linear_solve(
    design: np.ndarray, values: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
    weights = np.ones(len(values), dtype=float)
    for _iteration in range(50):
        residuals = values - design @ coefficients
        median = float(np.median(residuals))
        scale = max(5.0, 1.4826 * float(np.median(np.abs(residuals - median))))
        normalized = np.abs(residuals) / (1.345 * scale)
        weights = np.ones(len(values), dtype=float)
        tail = normalized > 1.0
        weights[tail] = 1.0 / normalized[tail]
        root = np.sqrt(weights)
        updated = np.linalg.lstsq(design * root[:, None], values * root, rcond=None)[0]
        if float(np.max(np.abs(updated - coefficients))) < 1e-7:
            coefficients = updated
            break
        coefficients = updated
    residuals = values - design @ coefficients
    dof = max(1, len(values) - design.shape[1])
    variance = float(np.sum(weights * residuals**2) / dof)
    covariance = np.linalg.pinv(design.T @ (weights[:, None] * design)) * variance
    return coefficients, covariance, residuals


def joint_ramp_fit(
    frames: tuple[FrameCfoMeasurement, ...],
    ramps: tuple[RampFit, ...],
    *,
    slope_progression: bool,
) -> JointRampFit:
    if len(ramps) < 3:
        raise ValueError("at least three ramps are required")
    by_index = {item.row_index: item for item in frames}
    reference = float(np.mean([item.center_time_s for item in ramps]))
    row_count = sum(item.frame_count for item in ramps)
    column_count = len(ramps) + 1 + int(slope_progression)
    design = np.zeros((row_count, column_count), dtype=float)
    values = np.empty(row_count, dtype=float)
    row_start = 0
    for ramp_index, ramp in enumerate(ramps):
        members = tuple(by_index[index] for index in ramp.observation_indices)
        times = np.asarray([item.time_s for item in members], dtype=float)
        frequencies = np.asarray([item.train_cfo_hz for item in members], dtype=float)
        local_time = times - ramp.center_time_s
        row_stop = row_start + len(members)
        design[row_start:row_stop, ramp_index] = 1.0
        design[row_start:row_stop, len(ramps)] = local_time
        if slope_progression:
            design[row_start:row_stop, len(ramps) + 1] = (
                ramp.center_time_s - reference
            ) * local_time + 0.5 * local_time**2
        values[row_start:row_stop] = frequencies
        row_start = row_stop
    coefficients, covariance, residuals = _robust_linear_solve(design, values)
    slope_index = len(ramps)
    progression_index = slope_index + 1
    rss = float(np.sum(residuals**2))
    bic = len(values) * math.log(max(rss / len(values), 1e-20)) + column_count * math.log(
        len(values)
    )
    return JointRampFit(
        reference_time_s=reference,
        shared_slope_hz_s=float(coefficients[slope_index]),
        shared_slope_sigma_hz_s=float(math.sqrt(max(0.0, covariance[slope_index, slope_index]))),
        slope_progression_hz_s2=(
            float(coefficients[progression_index]) if slope_progression else None
        ),
        slope_progression_sigma_hz_s2=(
            float(math.sqrt(max(0.0, covariance[progression_index, progression_index])))
            if slope_progression
            else None
        ),
        residual_rms_hz=float(math.sqrt(rss / len(values))),
        bic=bic,
        ramp_intercepts_hz=tuple(float(value) for value in coefficients[: len(ramps)]),
    )


def _prediction_errors(
    frames: tuple[FrameCfoMeasurement, ...],
    ramps: tuple[RampFit, ...],
    *,
    slope_hz_s: float,
) -> dict[str, float | int]:
    by_index = {item.row_index: item for item in frames}
    train_errors: list[float] = []
    validation_errors: list[float] = []
    for ramp in ramps:
        members = tuple(by_index[index] for index in ramp.observation_indices)
        local_time = np.asarray([item.time_s - ramp.center_time_s for item in members])
        train = np.asarray([item.train_cfo_hz for item in members])
        validation = np.asarray([item.validation_cfo_hz for item in members])
        intercept = float(np.median(train - slope_hz_s * local_time))
        predicted = intercept + slope_hz_s * local_time
        train_errors.extend(train - predicted)
        validation_errors.extend(validation - predicted)
    train_array = np.asarray(train_errors)
    validation_array = np.asarray(validation_errors)
    return {
        "frame_count": len(train_array),
        "train_rms_hz": float(np.sqrt(np.mean(train_array**2))),
        "validation_rms_hz": float(np.sqrt(np.mean(validation_array**2))),
        "validation_median_absolute_hz": float(np.median(np.abs(validation_array))),
        "validation_p95_absolute_hz": float(np.percentile(np.abs(validation_array), 95)),
    }


def _ramp_cluster_bootstrap(
    frames: tuple[FrameCfoMeasurement, ...],
    ramps: tuple[RampFit, ...],
    *,
    primary_slope_hz_s: float,
    config: DwellDopplerConfig,
) -> dict[str, float | int | bool]:
    by_index = {item.row_index: item for item in frames}
    numerators = []
    denominators = []
    for ramp in ramps:
        members = tuple(by_index[index] for index in ramp.observation_indices)
        times = np.asarray([item.time_s for item in members], dtype=float)
        values = np.asarray([item.train_cfo_hz for item in members], dtype=float)
        x = times - float(np.mean(times))
        y = values - float(np.mean(values))
        numerators.append(float(x @ y))
        denominators.append(float(x @ x))
    numerator = np.asarray(numerators)
    denominator = np.asarray(denominators)
    generator = np.random.default_rng(config.bootstrap_seed)
    samples = np.empty(config.bootstrap_replicates, dtype=float)
    for start in range(0, config.bootstrap_replicates, 1_000):
        stop = min(config.bootstrap_replicates, start + 1_000)
        indexes = generator.integers(0, len(ramps), size=(stop - start, len(ramps)))
        samples[start:stop] = np.sum(numerator[indexes], axis=1) / np.sum(
            denominator[indexes], axis=1
        )
    median = float(np.median(samples))
    centered = samples - median + primary_slope_hz_s
    return {
        "replicates": config.bootstrap_replicates,
        "seed": config.bootstrap_seed,
        "standard_error_hz_s": float(np.std(samples, ddof=1)),
        "p025_hz_s": float(np.percentile(centered, 2.5)),
        "p50_hz_s": primary_slope_hz_s,
        "p975_hz_s": float(np.percentile(centered, 97.5)),
        "recentered_on_robust_primary": True,
    }


def _rate_at_gate(
    frames: tuple[FrameCfoMeasurement, ...],
    config: DwellDopplerConfig,
    gate: float,
) -> tuple[tuple[FrameCfoMeasurement, ...], tuple[RampFit, ...], JointRampFit | None]:
    qualified = _qualified_frames(frames, gate)
    locks = independent_probe_fits(qualified, config)
    ramps = batch_joined_ramps(qualified, locks, config)
    fit = (
        joint_ramp_fit(qualified, ramps, slope_progression=False)
        if len(ramps) >= config.minimum_ramps
        else None
    )
    return qualified, ramps, fit


def infer_track_doppler(
    track: DwellDopplerTrackInput,
    frames: tuple[FrameCfoMeasurement, ...],
    config: DwellDopplerConfig,
) -> DwellDopplerResult:
    """Infer the overall and local rates from persisted GLRT plus raw frame CFOs."""

    strong_glrt = tuple(
        item
        for item in track.probes
        if item.exact_score >= config.glrt_exact_gate and item.margin > 0.0
    )
    glrt_span = (
        strong_glrt[-1].detection_time_s - strong_glrt[0].detection_time_s
        if len(strong_glrt) > 1
        else 0.0
    )
    base_diagnostics: dict[str, object] = {
        "overall_glrt_rate_hz_s": track.overall_glrt_rate_hz_s,
        "overall_glrt_rate_sigma_hz_s": track.glrt_rate_sigma_hz_s,
        "glrt_window_count": len(track.probes),
        "strong_glrt_window_count": len(strong_glrt),
        "strong_glrt_span_s": glrt_span,
        "frame_count": len(frames),
        "residual_grid_edge_frame_count": sum(item.residual_grid_edge for item in frames),
    }
    if len(strong_glrt) < config.minimum_glrt_windows or glrt_span < config.minimum_glrt_span_s:
        return DwellDopplerResult(
            DwellDopplerStatus.INSUFFICIENT_GLRT_SUPPORT,
            "persisted GLRT branch lacks minimum strong-window support",
            track,
            frames,
            (),
            base_diagnostics,
        )
    qualified, ramps, common = _rate_at_gate(frames, config, config.frame_exact_gate)
    base_diagnostics["qualified_frame_count"] = len(qualified)
    base_diagnostics["ramp_count"] = len(ramps)
    if len(qualified) < config.minimum_frames_per_lock * config.minimum_ramps:
        return DwellDopplerResult(
            DwellDopplerStatus.INSUFFICIENT_FRAME_SUPPORT,
            "too few Qin-specific frame CFOs pass the primary gate",
            track,
            frames,
            ramps,
            base_diagnostics,
        )
    if common is None:
        return DwellDopplerResult(
            DwellDopplerStatus.INSUFFICIENT_RAMP_SUPPORT,
            "fewer than three frequency-coherent ramps survive",
            track,
            frames,
            ramps,
            base_diagnostics,
        )
    progression = joint_ramp_fit(qualified, ramps, slope_progression=True)
    bootstrap = _ramp_cluster_bootstrap(
        qualified,
        ramps,
        primary_slope_hz_s=common.shared_slope_hz_s,
        config=config,
    )
    glrt_errors = _prediction_errors(
        qualified,
        ramps,
        slope_hz_s=track.overall_glrt_rate_hz_s,
    )
    local_errors = _prediction_errors(
        qualified,
        ramps,
        slope_hz_s=common.shared_slope_hz_s,
    )
    gate_sensitivity = []
    gate_rates = []
    for gate in config.frame_gate_sweep:
        gated_frames, gated_ramps, gated_fit = _rate_at_gate(frames, config, gate)
        rate = None if gated_fit is None else gated_fit.shared_slope_hz_s
        if rate is not None and gate >= 0.15:
            gate_rates.append(rate)
        gate_sensitivity.append(
            {
                "frame_exact_gate": gate,
                "qualified_frame_count": len(gated_frames),
                "ramp_count": len(gated_ramps),
                "local_rate_hz_s": rate,
            }
        )
    gate_spread = float(np.ptp(gate_rates)) if len(gate_rates) >= 2 else math.inf
    base_diagnostics.update(
        {
            "local_corrected_rate_hz_s": common.shared_slope_hz_s,
            "local_conditional_sigma_hz_s": common.shared_slope_sigma_hz_s,
            "local_practical_sigma_hz_s": bootstrap["standard_error_hz_s"],
            "local_p025_hz_s": bootstrap["p025_hz_s"],
            "local_p975_hz_s": bootstrap["p975_hz_s"],
            "rate_correction_hz_s": (common.shared_slope_hz_s - track.overall_glrt_rate_hz_s),
            "coherent_frame_count": sum(item.frame_count for item in ramps),
            "common_ramp_fit": asdict(common),
            "slope_progression_fit": asdict(progression),
            "bic_progression_minus_common": progression.bic - common.bic,
            "ramp_cluster_bootstrap": bootstrap,
            "glrt_rate_errors": glrt_errors,
            "local_rate_errors": local_errors,
            "odd_validation_reduction_percent": 100.0
            * (
                1.0
                - float(local_errors["validation_rms_hz"]) / float(glrt_errors["validation_rms_hz"])
            ),
            "gate_sensitivity": gate_sensitivity,
            "strict_gate_rate_spread_hz_s": gate_spread,
        }
    )
    practical_sigma = float(bootstrap["standard_error_hz_s"])
    if practical_sigma > config.maximum_practical_sigma_hz_s or (
        math.isfinite(gate_spread) and gate_spread > config.maximum_gate_spread_hz_s
    ):
        status = DwellDopplerStatus.UNSTABLE_LOCAL_RATE
        reason = "local rate is too sensitive across ramp clusters or Qin gates"
    elif float(local_errors["validation_rms_hz"]) > (
        (1.0 + config.validation_tolerance_fraction) * float(glrt_errors["validation_rms_hz"])
    ):
        status = DwellDopplerStatus.VALIDATION_FAILED
        reason = "local rate predicts held-out odd Qin worse than the GLRT rate"
    else:
        status = DwellDopplerStatus.COMPLETE
        reason = "overall GLRT and reset-debiased local rates are supported"
    return DwellDopplerResult(status, reason, track, frames, ramps, base_diagnostics)


def analyze_track_doppler(
    reader: RandomAccessIqReader,
    track: DwellDopplerTrackInput,
    config: DwellDopplerConfig | None = None,
) -> DwellDopplerResult:
    selected = config or DwellDopplerConfig()
    frames = extract_frame_cfos(reader, track, selected)
    return infer_track_doppler(track, frames, selected)
