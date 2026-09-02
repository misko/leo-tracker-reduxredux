"""Shared sample-rate-independent fractional epoch primitives.

Integer epochs remain the stable acquisition/index identity.  This module adds
one bounded, circular refinement and one deterministic band-limited sampler for
consumers that need the corresponding continuous-time alignment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from leo.analysis.starlink.templates import FRAME_RATE_HZ

FRACTIONAL_GLRT_GRID_OFFSETS: tuple[int, ...] = (-2, -1, 0, 1, 2)
_LANCZOS_HALF_WIDTH = 8


class FractionalEpochStatus(StrEnum):
    COMPLETE = "complete"
    UNBRACKETED = "unbracketed"


@dataclass(frozen=True, slots=True)
class FractionalEpochRefinement:
    """One fixed-CFO GLRT timing surface around an integer anchor."""

    integer_epoch_sample: int
    frame_period_samples: float
    wrapped_epoch_samples: tuple[int, ...]
    exact_score_grid: tuple[float, ...]
    control_score_grid: tuple[float, ...]
    status: FractionalEpochStatus
    fractional_epoch_offset_samples: float | None
    log_curvature: float | None
    fractional_exact_score: float | None = None
    fractional_control_score: float | None = None

    @property
    def fractional_frame_phase_sample(self) -> float | None:
        offset = self.fractional_epoch_offset_samples
        if offset is None:
            return None
        # Acquisition searches ``round(Fs / 750)`` discrete phase cells.  The
        # circular coordinate must use that same ring even when the physical
        # frame period is fractional (for example 3333.333 samples at 2.5M).
        return float((self.integer_epoch_sample + offset) % round(self.frame_period_samples))


def circular_epoch_grid(
    integer_epoch_sample: int,
    sample_rate_hz: float,
    offsets: tuple[int, ...] = FRACTIONAL_GLRT_GRID_OFFSETS,
) -> tuple[int, ...]:
    """Return integer timing probes with the 750 Hz frame seam wrapped."""

    if (
        isinstance(integer_epoch_sample, bool)
        or not isinstance(integer_epoch_sample, (int, np.integer))
        or integer_epoch_sample < 0
    ):
        raise ValueError("integer epoch must be a nonnegative integer")
    if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample rate must be finite and positive")
    if not offsets or offsets != tuple(sorted(set(offsets))):
        raise ValueError("fractional epoch offsets must be unique and ordered")
    epoch_count = round(sample_rate_hz / FRAME_RATE_HZ)
    if integer_epoch_sample >= epoch_count:
        raise ValueError("integer epoch lies outside one frame period")
    return tuple((int(integer_epoch_sample) + offset) % epoch_count for offset in offsets)


def fractional_log_peak(
    scores: tuple[float, ...],
    offsets: tuple[int, ...] = FRACTIONAL_GLRT_GRID_OFFSETS,
) -> tuple[float | None, float | None]:
    """Fit a bracketed log-parabola and return (offset, curvature)."""

    values = np.asarray(scores, dtype=float)
    grid = np.asarray(offsets, dtype=float)
    if values.ndim != 1 or grid.ndim != 1 or values.size != grid.size or values.size < 3:
        raise ValueError("fractional GLRT peak requires equal score and offset vectors")
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError("fractional GLRT scores must be finite and nonnegative")
    steps = np.diff(grid)
    if np.any(steps <= 0.0) or not np.allclose(steps, steps[0], rtol=0.0, atol=1e-12):
        raise ValueError("fractional GLRT offsets must be uniformly increasing")
    index = int(np.argmax(values))
    if index == 0 or index == len(values) - 1:
        return None, None
    selected = np.log(np.maximum(values[index - 1 : index + 2], np.finfo(float).tiny))
    curvature = float(selected[0] - 2.0 * selected[1] + selected[2])
    if not math.isfinite(curvature) or curvature >= -np.finfo(float).eps:
        return None, None
    fraction = float(np.clip(0.5 * (selected[0] - selected[2]) / curvature, -0.5, 0.5))
    return float(grid[index] + fraction * steps[0]), curvature


def build_fractional_epoch_refinement(
    *,
    integer_epoch_sample: int,
    sample_rate_hz: float,
    exact_score_grid: tuple[float, ...],
    control_score_grid: tuple[float, ...],
    offsets: tuple[int, ...] = FRACTIONAL_GLRT_GRID_OFFSETS,
) -> FractionalEpochRefinement:
    """Close one exact/control integer surface into an immutable estimate."""

    if len(exact_score_grid) != len(control_score_grid):
        raise ValueError("fractional exact/control grids must have equal length")
    wrapped = circular_epoch_grid(integer_epoch_sample, sample_rate_hz, offsets)
    offset, curvature = fractional_log_peak(exact_score_grid, offsets)
    return FractionalEpochRefinement(
        integer_epoch_sample=int(integer_epoch_sample),
        frame_period_samples=float(sample_rate_hz / FRAME_RATE_HZ),
        wrapped_epoch_samples=wrapped,
        exact_score_grid=tuple(float(item) for item in exact_score_grid),
        control_score_grid=tuple(float(item) for item in control_score_grid),
        status=(
            FractionalEpochStatus.COMPLETE
            if offset is not None
            else FractionalEpochStatus.UNBRACKETED
        ),
        fractional_epoch_offset_samples=offset,
        log_curvature=curvature,
    )


def fractional_take(
    samples: np.ndarray,
    positions: np.ndarray,
    *,
    half_width: int = _LANCZOS_HALF_WIDTH,
) -> np.ndarray:
    """Sample complex IQ at continuous positions with a normalized Lanczos kernel.

    Integer positions take the exact original values.  Fractional positions use
    a fixed 16-tap windowed-sinc interpolator; unsupported edge positions fail
    closed instead of silently padding or clipping.
    """

    values = np.asarray(samples, dtype=np.complex128)
    locations = np.asarray(positions, dtype=float)
    if values.ndim != 1 or not values.size:
        raise ValueError("fractional source samples must be a nonempty vector")
    if not np.all(np.isfinite(locations)):
        raise ValueError("fractional sample positions must be finite")
    if isinstance(half_width, bool) or not isinstance(half_width, int) or half_width < 2:
        raise ValueError("fractional interpolation half width must be at least two")
    rounded = np.rint(locations)
    if np.all(np.abs(locations - rounded) <= 1e-12):
        indexes = rounded.astype(np.int64)
        if np.any(indexes < 0) or np.any(indexes >= len(values)):
            raise ValueError("integer sample position lies outside source support")
        return np.asarray(values[indexes], dtype=np.complex128)

    bases = np.floor(locations).astype(np.int64)
    tap_offsets = np.arange(-half_width + 1, half_width + 1, dtype=np.int64)
    indexes = bases[..., None] + tap_offsets
    if np.any(indexes < 0) or np.any(indexes >= len(values)):
        raise ValueError("fractional sample position lacks interpolation support")
    distance = locations[..., None] - indexes
    weights = np.sinc(distance) * np.sinc(distance / half_width)
    normalizer = np.sum(weights, axis=-1, keepdims=True)
    if np.any(np.abs(normalizer) <= np.finfo(float).tiny):
        raise ValueError("fractional interpolation kernel is singular")
    return np.sum(values[indexes] * (weights / normalizer), axis=-1)


def fractional_take_bounds(
    offset_samples: float, *, half_width: int = _LANCZOS_HALF_WIDTH
) -> tuple[int, int]:
    """Return required left/right guards for a common fractional offset."""

    if not math.isfinite(offset_samples):
        raise ValueError("fractional epoch offset must be finite")
    if math.isclose(offset_samples, round(offset_samples), rel_tol=0.0, abs_tol=1e-12):
        return 0, 0
    return half_width - 1, half_width
