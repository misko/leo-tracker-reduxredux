"""Reset-safe Doppler-rate fits from independent frame-CFO profiles.

The acquisition layer remains authoritative for the frame lattice and CFO
alias.  These helpers connect frequency, never carrier phase: every input
frame has already profiled out its own complex pilot-tone gains.  Even Qin
symbols fit the line; odd Qin and the rolled-Qin control are responses only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class FrameCfoRateMethod(StrEnum):
    GLRT_RATE = "glrt_rate_recentered"
    FRAME_MAXIMA = "frame_maxima"
    SUMMED_PROFILE = "summed_profile"
    OCCUPANCY_MIXTURE = "occupancy_mixture"


@dataclass(frozen=True, slots=True)
class FrameCfoProfile:
    """One frame's four acquisition-bound, parity-split likelihood curves."""

    frame_start_sample: int
    reference_time_s: float
    continuity_segment: int
    cfo_origin_hz: float
    residual_grid_hz: np.ndarray
    even_exact_log_likelihood: np.ndarray
    even_control_log_likelihood: np.ndarray
    odd_exact_log_likelihood: np.ndarray
    odd_control_log_likelihood: np.ndarray

    def __post_init__(self) -> None:
        if self.frame_start_sample < 0 or self.continuity_segment < 0:
            raise ValueError("frame coordinates must be non-negative")
        if not math.isfinite(self.reference_time_s) or not math.isfinite(self.cfo_origin_hz):
            raise ValueError("frame time and CFO origin must be finite")
        grid = np.asarray(self.residual_grid_hz, dtype=float)
        curves = tuple(
            np.asarray(value, dtype=float)
            for value in (
                self.even_exact_log_likelihood,
                self.even_control_log_likelihood,
                self.odd_exact_log_likelihood,
                self.odd_control_log_likelihood,
            )
        )
        if grid.ndim != 1 or grid.size < 3 or np.any(np.diff(grid) <= 0.0):
            raise ValueError("profile grid must be one-dimensional and strictly increasing")
        if not np.all(np.isfinite(grid)):
            raise ValueError("profile grid must be finite")
        if any(curve.shape != grid.shape or not np.all(np.isfinite(curve)) for curve in curves):
            raise ValueError("profile curves must be finite and match the common grid")
        frozen = []
        for value in (grid, *curves):
            copied = value.copy()
            copied.flags.writeable = False
            frozen.append(copied)
        object.__setattr__(self, "residual_grid_hz", frozen[0])
        object.__setattr__(self, "even_exact_log_likelihood", frozen[1])
        object.__setattr__(self, "even_control_log_likelihood", frozen[2])
        object.__setattr__(self, "odd_exact_log_likelihood", frozen[3])
        object.__setattr__(self, "odd_control_log_likelihood", frozen[4])


@dataclass(frozen=True, slots=True)
class FrameCfoRateSearchConfig:
    cfo_half_width_hz: float = 500.0
    rate_half_width_hz_s: float = 6_000.0
    coarse_cfo_step_hz: float = 25.0
    coarse_rate_step_hz_s: float = 250.0
    fine_cfo_step_hz: float = 5.0
    fine_rate_step_hz_s: float = 25.0
    occupancy_outlier_fraction: float = 0.20
    minimum_frames: int = 10
    minimum_span_s: float = 0.012

    def __post_init__(self) -> None:
        positive = (
            self.cfo_half_width_hz,
            self.rate_half_width_hz_s,
            self.coarse_cfo_step_hz,
            self.coarse_rate_step_hz_s,
            self.fine_cfo_step_hz,
            self.fine_rate_step_hz_s,
            self.minimum_span_s,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("rate-search scales must be finite and positive")
        if not 0.0 < self.occupancy_outlier_fraction < 0.5:
            raise ValueError("occupancy outlier fraction must lie in (0, 0.5)")
        if self.minimum_frames < 3:
            raise ValueError("rate fit requires at least three frames")


@dataclass(frozen=True, slots=True)
class FrameCfoRateFit:
    method: FrameCfoRateMethod
    frame_count: int
    span_s: float
    reference_time_s: float
    cfo_hz: float
    rate_hz_s: float
    conditional_rate_sigma_hz_s: float | None
    training_objective: float
    even_exact_objective: float
    even_control_objective: float
    odd_exact_objective: float
    odd_control_objective: float
    even_exact_minus_control: float
    odd_exact_minus_control: float
    odd_cfo_rms_hz: float
    odd_cfo_median_absolute_hz: float
    cfo_search_boundary: bool
    rate_search_boundary: bool
    profile_support_complete: bool
    fit_symbols: str = "even Qin"
    validation_symbols: str = "odd Qin"
    carrier_phase_connected: bool = False
    odd_symbols_influenced_fit: bool = False


def fit_frame_cfo_rate(
    frames: tuple[FrameCfoProfile, ...],
    *,
    initial_cfo_hz: float,
    initial_rate_hz_s: float,
    method: FrameCfoRateMethod | str,
    config: FrameCfoRateSearchConfig | None = None,
) -> FrameCfoRateFit:
    """Fit one line on a single verified-continuity window."""

    settings = config or FrameCfoRateSearchConfig()
    selected_method = FrameCfoRateMethod(method)
    ordered = _validated_frames(frames, settings)
    reference_time_s = float(np.mean([frame.reference_time_s for frame in ordered]))
    if not math.isfinite(initial_cfo_hz) or not math.isfinite(initial_rate_hz_s):
        raise ValueError("initial CFO and rate must be finite")

    if selected_method is FrameCfoRateMethod.FRAME_MAXIMA:
        raw_cfo_hz, raw_rate_hz_s = _fit_frame_maxima(ordered, reference_time_s)
        cfo_hz = float(
            np.clip(
                raw_cfo_hz,
                initial_cfo_hz - settings.cfo_half_width_hz,
                initial_cfo_hz + settings.cfo_half_width_hz,
            )
        )
        rate_hz_s = float(
            np.clip(
                raw_rate_hz_s,
                initial_rate_hz_s - settings.rate_half_width_hz_s,
                initial_rate_hz_s + settings.rate_half_width_hz_s,
            )
        )
        cfo_boundary = cfo_hz != raw_cfo_hz
        rate_boundary = rate_hz_s != raw_rate_hz_s
        sigma = _regression_rate_sigma(ordered, reference_time_s, cfo_hz, rate_hz_s)
        objective = _line_score(
            ordered,
            reference_time_s,
            cfo_hz,
            rate_hz_s,
            split="even",
            sequence="exact",
            mixture_fraction=None,
        )
    elif selected_method is FrameCfoRateMethod.GLRT_RATE:
        cfo_hz, cfo_boundary, objective = _fit_fixed_rate_intercept(
            ordered,
            reference_time_s,
            initial_cfo_hz,
            initial_rate_hz_s,
            settings,
        )
        rate_hz_s = initial_rate_hz_s
        rate_boundary = False
        sigma = None
    else:
        mixture = (
            settings.occupancy_outlier_fraction
            if selected_method is FrameCfoRateMethod.OCCUPANCY_MIXTURE
            else None
        )
        cfo_hz, rate_hz_s, cfo_boundary, rate_boundary, objective, sigma = _fit_surface(
            ordered,
            reference_time_s,
            initial_cfo_hz,
            initial_rate_hz_s,
            settings,
            mixture_fraction=mixture,
        )

    even_exact = _line_score(
        ordered,
        reference_time_s,
        cfo_hz,
        rate_hz_s,
        split="even",
        sequence="exact",
        mixture_fraction=None,
    )
    even_control = _line_score(
        ordered,
        reference_time_s,
        cfo_hz,
        rate_hz_s,
        split="even",
        sequence="control",
        mixture_fraction=None,
    )
    odd_exact = _line_score(
        ordered,
        reference_time_s,
        cfo_hz,
        rate_hz_s,
        split="odd",
        sequence="exact",
        mixture_fraction=None,
    )
    odd_control = _line_score(
        ordered,
        reference_time_s,
        cfo_hz,
        rate_hz_s,
        split="odd",
        sequence="control",
        mixture_fraction=None,
    )
    odd_points = np.asarray(
        [
            frame.cfo_origin_hz
            + _curve_peak(frame.residual_grid_hz, frame.odd_exact_log_likelihood)
            for frame in ordered
        ],
        dtype=float,
    )
    times = np.asarray([frame.reference_time_s for frame in ordered], dtype=float)
    prediction = cfo_hz + rate_hz_s * (times - reference_time_s)
    residual = odd_points - prediction
    glrt_context = selected_method is FrameCfoRateMethod.GLRT_RATE
    return FrameCfoRateFit(
        method=selected_method,
        frame_count=len(ordered),
        span_s=float(times[-1] - times[0]),
        reference_time_s=reference_time_s,
        cfo_hz=float(cfo_hz),
        rate_hz_s=float(rate_hz_s),
        conditional_rate_sigma_hz_s=sigma,
        training_objective=float(objective),
        even_exact_objective=float(even_exact),
        even_control_objective=float(even_control),
        odd_exact_objective=float(odd_exact),
        odd_control_objective=float(odd_control),
        even_exact_minus_control=float(even_exact - even_control),
        odd_exact_minus_control=float(odd_exact - odd_control),
        odd_cfo_rms_hz=float(np.sqrt(np.mean(residual**2))),
        odd_cfo_median_absolute_hz=float(np.median(np.abs(residual))),
        cfo_search_boundary=cfo_boundary,
        rate_search_boundary=rate_boundary,
        profile_support_complete=True,
        fit_symbols=(
            "upstream GLRT64 (even + odd Qin); local even-Qin intercept"
            if glrt_context
            else "even Qin"
        ),
        validation_symbols=(
            "odd Qin response (not fit-withheld from upstream GLRT64 slope)"
            if glrt_context
            else "odd Qin"
        ),
        odd_symbols_influenced_fit=glrt_context,
    )


def trailing_frame_windows(
    frames: tuple[FrameCfoProfile, ...],
    *,
    duration_s: float,
    minimum_frames: int,
) -> tuple[tuple[FrameCfoProfile, ...], ...]:
    """Return causal, frame-cadence trailing windows within one segment."""

    if not math.isfinite(duration_s) or duration_s <= 0.0 or minimum_frames < 2:
        raise ValueError("window duration and support must be positive")
    ordered = tuple(sorted(frames, key=lambda frame: frame.reference_time_s))
    output = []
    start = 0
    for stop, frame in enumerate(ordered):
        while ordered[start].reference_time_s < frame.reference_time_s - duration_s:
            start += 1
        window = ordered[start : stop + 1]
        if (
            len(window) >= minimum_frames
            and window[-1].reference_time_s - window[0].reference_time_s >= duration_s - 2.0 / 750.0
        ):
            output.append(window)
    return tuple(output)


def _validated_frames(
    frames: tuple[FrameCfoProfile, ...],
    config: FrameCfoRateSearchConfig,
) -> tuple[FrameCfoProfile, ...]:
    ordered = tuple(sorted(frames, key=lambda frame: frame.reference_time_s))
    if len(ordered) < config.minimum_frames:
        raise ValueError("insufficient frames for a CFO-rate fit")
    if len({frame.frame_start_sample for frame in ordered}) != len(ordered):
        raise ValueError("frame starts must be unique")
    if any(
        current.reference_time_s <= previous.reference_time_s
        or current.frame_start_sample <= previous.frame_start_sample
        for previous, current in zip(ordered, ordered[1:], strict=False)
    ):
        raise ValueError("frame sample and time coordinates must increase together")
    segments = {frame.continuity_segment for frame in ordered}
    if len(segments) != 1:
        raise ValueError("one CFO-rate fit cannot cross a continuity segment")
    span_s = ordered[-1].reference_time_s - ordered[0].reference_time_s
    if span_s < config.minimum_span_s:
        raise ValueError("insufficient time span for a CFO-rate fit")
    first_grid = ordered[0].residual_grid_hz
    if any(not np.array_equal(frame.residual_grid_hz, first_grid) for frame in ordered[1:]):
        raise ValueError("all frame profiles must share one residual-frequency grid")
    return ordered


def _fit_frame_maxima(
    frames: tuple[FrameCfoProfile, ...], reference_time_s: float
) -> tuple[float, float]:
    times = np.asarray([frame.reference_time_s - reference_time_s for frame in frames])
    values = np.asarray(
        [
            frame.cfo_origin_hz
            + _curve_peak(frame.residual_grid_hz, frame.even_exact_log_likelihood)
            for frame in frames
        ]
    )
    design = np.column_stack((np.ones(len(times)), times))
    weights = np.ones(len(times), dtype=float)
    coefficients = np.linalg.lstsq(design, values, rcond=None)[0]
    for _ in range(4):
        residual = values - design @ coefficients
        scale = max(1.4826 * float(np.median(np.abs(residual - np.median(residual)))), 1.0)
        weights = np.minimum(1.0, 1.5 * scale / np.maximum(np.abs(residual), 1e-12))
        coefficients = np.linalg.lstsq(
            design * np.sqrt(weights[:, None]), values * np.sqrt(weights), rcond=None
        )[0]
    return float(coefficients[0]), float(coefficients[1])


def _regression_rate_sigma(
    frames: tuple[FrameCfoProfile, ...],
    reference_time_s: float,
    cfo_hz: float,
    rate_hz_s: float,
) -> float | None:
    times = np.asarray([frame.reference_time_s - reference_time_s for frame in frames])
    values = np.asarray(
        [
            frame.cfo_origin_hz
            + _curve_peak(frame.residual_grid_hz, frame.even_exact_log_likelihood)
            for frame in frames
        ]
    )
    residual = values - cfo_hz - rate_hz_s * times
    denominator = float(np.sum(times**2))
    if len(frames) <= 2 or denominator <= 0.0:
        return None
    variance = float(np.sum(residual**2) / (len(frames) - 2))
    return float(math.sqrt(max(variance / denominator, 0.0)))


def _fit_fixed_rate_intercept(
    frames: tuple[FrameCfoProfile, ...],
    reference_time_s: float,
    initial_cfo_hz: float,
    rate_hz_s: float,
    config: FrameCfoRateSearchConfig,
) -> tuple[float, bool, float]:
    axis = _axis(initial_cfo_hz, config.cfo_half_width_hz, config.fine_cfo_step_hz)
    scores = np.asarray(
        [
            _line_score(
                frames,
                reference_time_s,
                cfo,
                rate_hz_s,
                split="even",
                sequence="exact",
                mixture_fraction=None,
            )
            for cfo in axis
        ]
    )
    best = int(np.argmax(scores))
    return float(axis[best]), best in {0, len(axis) - 1}, float(scores[best])


def _fit_surface(
    frames: tuple[FrameCfoProfile, ...],
    reference_time_s: float,
    initial_cfo_hz: float,
    initial_rate_hz_s: float,
    config: FrameCfoRateSearchConfig,
    *,
    mixture_fraction: float | None,
) -> tuple[float, float, bool, bool, float, float | None]:
    coarse_cfo = _axis(initial_cfo_hz, config.cfo_half_width_hz, config.coarse_cfo_step_hz)
    coarse_rate = _axis(
        initial_rate_hz_s,
        config.rate_half_width_hz_s,
        config.coarse_rate_step_hz_s,
    )
    coarse = _surface(
        frames,
        reference_time_s,
        coarse_cfo,
        coarse_rate,
        mixture_fraction=mixture_fraction,
    )
    coarse_best = np.unravel_index(int(np.argmax(coarse)), coarse.shape)
    center_rate = float(coarse_rate[coarse_best[0]])
    center_cfo = float(coarse_cfo[coarse_best[1]])
    fine_cfo = _axis(center_cfo, config.coarse_cfo_step_hz, config.fine_cfo_step_hz)
    fine_rate = _axis(center_rate, config.coarse_rate_step_hz_s, config.fine_rate_step_hz_s)
    fine = _surface(
        frames,
        reference_time_s,
        fine_cfo,
        fine_rate,
        mixture_fraction=mixture_fraction,
    )
    best = np.unravel_index(int(np.argmax(fine)), fine.shape)
    rate_index, cfo_index = int(best[0]), int(best[1])
    # The fine grid deliberately overlaps both neighboring coarse cells.  A
    # fine-edge maximum is not the edge of the predeclared search basin.
    cfo_boundary = coarse_best[1] in {0, len(coarse_cfo) - 1}
    rate_boundary = coarse_best[0] in {0, len(coarse_rate) - 1}
    sigma = _surface_rate_sigma(
        fine,
        rate_index,
        cfo_index,
        config.fine_rate_step_hz_s,
        config.fine_cfo_step_hz,
    )
    return (
        float(fine_cfo[cfo_index]),
        float(fine_rate[rate_index]),
        cfo_boundary,
        rate_boundary,
        float(fine[rate_index, cfo_index]),
        sigma,
    )


def _surface(
    frames: tuple[FrameCfoProfile, ...],
    reference_time_s: float,
    cfo_axis_hz: np.ndarray,
    rate_axis_hz_s: np.ndarray,
    *,
    mixture_fraction: float | None,
) -> np.ndarray:
    score = np.zeros((len(rate_axis_hz_s), len(cfo_axis_hz)), dtype=float)
    for frame in frames:
        offsets = (
            cfo_axis_hz[None, :]
            + rate_axis_hz_s[:, None] * (frame.reference_time_s - reference_time_s)
            - frame.cfo_origin_hz
        )
        values = _interpolate_curve(
            frame.residual_grid_hz,
            frame.even_exact_log_likelihood,
            offsets,
        )
        if mixture_fraction is not None:
            normalized = values - _logsumexp(frame.even_exact_log_likelihood)
            uniform = -math.log(len(frame.residual_grid_hz))
            values = np.logaddexp(
                math.log1p(-mixture_fraction) + normalized,
                math.log(mixture_fraction) + uniform,
            )
        score += values
    return score


def _line_score(
    frames: tuple[FrameCfoProfile, ...],
    reference_time_s: float,
    cfo_hz: float,
    rate_hz_s: float,
    *,
    split: str,
    sequence: str,
    mixture_fraction: float | None,
) -> float:
    if split not in {"even", "odd"} or sequence not in {"exact", "control"}:
        raise ValueError("profile lane must name an even/odd exact/control curve")
    field_name = f"{split}_{sequence}_log_likelihood"
    total = 0.0
    for frame in frames:
        curve = getattr(frame, field_name)
        offset = (
            cfo_hz + rate_hz_s * (frame.reference_time_s - reference_time_s) - frame.cfo_origin_hz
        )
        value = float(_interpolate_curve(frame.residual_grid_hz, curve, np.asarray(offset)))
        if mixture_fraction is not None:
            normalized = value - _logsumexp(curve)
            value = float(
                np.logaddexp(
                    math.log1p(-mixture_fraction) + normalized,
                    math.log(mixture_fraction) - math.log(len(curve)),
                )
            )
        total += value
    return float(total)


def _interpolate_curve(grid: np.ndarray, curve: np.ndarray, values: np.ndarray) -> np.ndarray:
    result = np.interp(values, grid, curve, left=np.nan, right=np.nan)
    if np.any(~np.isfinite(result)):
        raise ValueError("candidate CFO line leaves a frame's profiled acquisition basin")
    return np.asarray(result, dtype=float)


def _curve_peak(grid: np.ndarray, curve: np.ndarray) -> float:
    best = int(np.argmax(curve))
    value = float(grid[best])
    if 0 < best < len(grid) - 1:
        leading, center, trailing = curve[best - 1 : best + 2]
        denominator = float(leading - 2.0 * center + trailing)
        if abs(denominator) > 1e-20:
            fraction = float(np.clip(0.5 * (leading - trailing) / denominator, -0.5, 0.5))
            value += fraction * float(grid[best + 1] - grid[best])
    return value


def _axis(center: float, half_width: float, step: float) -> np.ndarray:
    count = int(math.ceil(half_width / step))
    return center + np.arange(-count, count + 1, dtype=float) * step


def _surface_rate_sigma(
    surface: np.ndarray,
    rate_index: int,
    cfo_index: int,
    rate_step: float,
    cfo_step: float,
) -> float | None:
    if not (0 < rate_index < surface.shape[0] - 1 and 0 < cfo_index < surface.shape[1] - 1):
        return None
    center = float(surface[rate_index, cfo_index])
    drr = (
        float(surface[rate_index + 1, cfo_index] - 2 * center + surface[rate_index - 1, cfo_index])
        / rate_step**2
    )
    dff = (
        float(surface[rate_index, cfo_index + 1] - 2 * center + surface[rate_index, cfo_index - 1])
        / cfo_step**2
    )
    drf = float(
        surface[rate_index + 1, cfo_index + 1]
        - surface[rate_index + 1, cfo_index - 1]
        - surface[rate_index - 1, cfo_index + 1]
        + surface[rate_index - 1, cfo_index - 1]
    ) / (4.0 * rate_step * cfo_step)
    hessian = np.asarray(((dff, drf), (drf, drr)), dtype=float)
    if np.any(np.linalg.eigvalsh(hessian) >= 0.0):
        return None
    covariance = -np.linalg.inv(hessian)
    return float(math.sqrt(max(float(covariance[1, 1]), 0.0)))


def _logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    return float(maximum + math.log(float(np.sum(np.exp(values - maximum)))))
