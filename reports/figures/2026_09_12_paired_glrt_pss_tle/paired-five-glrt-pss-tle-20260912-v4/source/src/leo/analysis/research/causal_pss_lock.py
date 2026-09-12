"""Causal outlier gating conditional on a caller-acquired PSS timing candidate.

This pure research analyzer owns no IQ acquisition or candidate association.
Rejected observations never update its state; missing support expires the lock.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PssLockConfig:
    frame_period_s: float = 1 / 750
    acquisition_frames: int = 64
    acquisition_inlier_fraction: float = 0.75
    history_frames: int = 128
    innovation_gate_s: float = 120e-9
    maximum_coast_s: float = 0.250
    minimum_peak_ratio: float = 5.0

    def __post_init__(self):
        for value in (
            self.frame_period_s,
            self.innovation_gate_s,
            self.maximum_coast_s,
            self.minimum_peak_ratio,
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("PSS lock scales must be positive and finite")
        for value in (self.acquisition_frames, self.history_frames):
            if isinstance(value, bool) or not isinstance(value, int) or value < 3:
                raise ValueError("PSS lock history counts must be integers at least three")
        if not 0.5 < self.acquisition_inlier_fraction <= 1:
            raise ValueError("PSS acquisition requires a strict majority")
        if self.innovation_gate_s >= self.frame_period_s / 2:
            raise ValueError("PSS gate must be smaller than half a frame")


@dataclass(frozen=True)
class PssLockObservation:
    time_s: float
    phase_s: float
    peak_ratio: float
    continuity_segment: int = 0


@dataclass(frozen=True)
class PssLockDecision:
    index: int
    time_s: float
    observed_phase_s: float
    status: str
    lock_id: int
    predicted_phase_s: float | None = None
    innovation_s: float | None = None
    predicted_stretch: float | None = None
    reset_reason: str | None = None


def _line(history: list[tuple[float, float]]) -> tuple[float, float, float]:
    times, phases = np.asarray(history, dtype=float).T
    origin = float(times[-1])
    slope, intercept = np.polyfit(times - origin, phases, 1)
    return origin, float(intercept), float(slope)


def track_pss_observations(
    observations: tuple[PssLockObservation, ...],
    config: PssLockConfig | None = None,
) -> tuple[PssLockDecision, ...]:
    """Predict each measurement from earlier accepted data before gating it.

    Startup is explicitly separate: a median-pair-slope line selects a majority
    from the last acquisition_frames eligible observations, then starts a new
    lock. No bootstrap observation is backdated as a predicted accepted frame.
    """
    config = config or PssLockConfig()
    history: list[tuple[float, float]] = []
    bootstrap: list[tuple[float, float]] = []
    output = []
    last_time = -math.inf
    segment = None
    lock_id = 0
    period = config.frame_period_s
    for index, point in enumerate(observations):
        if not all(math.isfinite(x) for x in (point.time_s, point.phase_s, point.peak_ratio)):
            raise ValueError("PSS lock observations must be finite")
        if point.time_s <= last_time:
            raise ValueError("PSS observations must have strictly increasing times")
        if (
            isinstance(point.continuity_segment, bool)
            or not isinstance(point.continuity_segment, int)
            or point.continuity_segment < 0
        ):
            raise ValueError("PSS continuity segment must be a nonnegative integer")
        last_time = point.time_s
        reset_reason = None
        if segment is not None and segment != point.continuity_segment:
            reset_reason = "continuity_segment_changed"
        elif history and point.time_s - history[-1][0] > config.maximum_coast_s:
            reset_reason = "coast_expired"
        if reset_reason:
            history.clear()
            bootstrap.clear()
        segment = point.continuity_segment
        phase = point.phase_s % period
        if not history:
            bootstrap = [p for p in bootstrap if point.time_s - p[0] <= config.maximum_coast_s]
            if point.peak_ratio >= config.minimum_peak_ratio:
                bootstrap.append((point.time_s, phase))
                bootstrap = bootstrap[-config.acquisition_frames :]
            status = "lost_lock" if reset_reason else "acquiring"
            if len(bootstrap) == config.acquisition_frames:
                times, phases = np.asarray(bootstrap).T
                phases = np.unwrap(phases * 2 * np.pi / period) * period / (2 * np.pi)
                x = times - times[-1]
                i, j = np.triu_indices(len(times), 1)
                slope = float(np.median((phases[j] - phases[i]) / (x[j] - x[i])))
                intercept = float(np.median(phases - slope * x))
                usable = abs(phases - (intercept + slope * x)) <= config.innovation_gate_s
                if np.mean(usable) >= config.acquisition_inlier_fraction:
                    history = list(
                        zip(times[usable].tolist(), phases[usable].tolist(), strict=True)
                    )
                    bootstrap.clear()
                    lock_id += 1
                    status = "lock_acquired"
            output.append(
                PssLockDecision(
                    index, point.time_s, phase, status, lock_id, reset_reason=reset_reason
                )
            )
            continue
        origin, intercept, slope = _line(history)
        prediction = intercept + slope * (point.time_s - origin)
        unwrapped = phase + round((prediction - phase) / period) * period
        innovation = unwrapped - prediction
        accepted = (
            abs(innovation) <= config.innovation_gate_s
            and point.peak_ratio >= config.minimum_peak_ratio
        )
        output.append(
            PssLockDecision(
                index,
                point.time_s,
                unwrapped,
                "accepted" if accepted else "rejected",
                lock_id,
                prediction,
                innovation,
                slope,
            )
        )
        if accepted:
            history.append((point.time_s, unwrapped))
            history = history[-config.history_frames :]
    return tuple(output)
