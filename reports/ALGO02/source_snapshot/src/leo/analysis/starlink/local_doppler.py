"""Shared local CFO-line and complete-frame helpers for dwell and scanner analysis."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from leo.analysis.robust_linear import HuberLinearFit, fit_huber_linear_irls
from leo.analysis.starlink.templates import FRAME_RATE_HZ, OFDM_SYMBOL_DURATION_S


def frequency_line(times: np.ndarray, values: np.ndarray) -> HuberLinearFit | None:
    """Fit one robust local frequency line at the mean measurement time."""

    if len(times) < 6 or np.unique(times).size < 3:
        return None
    reference = float(np.mean(times))
    initial = np.polyfit(times - reference, values, 1)
    return fit_huber_linear_irls(
        times,
        values,
        initial_coefficients_hz=(float(initial[0]), float(initial[1])),
        reference_time_s=reference,
        scale_floor_hz=5.0,
    )


def complete_lattice_count(sample_count: int, sample_rate_hz: int, epoch_sample: int) -> int:
    """Count complete known-pilot frames from one acquisition epoch."""

    frame_content = round(302 * sample_rate_hz * OFDM_SYMBOL_DURATION_S)
    frame = 0
    while (
        epoch_sample + round(frame * sample_rate_hz / FRAME_RATE_HZ) + frame_content <= sample_count
    ):
        frame += 1
    return frame


def interleaved_held_out_rms(times: np.ndarray, values: np.ndarray) -> float | None:
    """Cross-predict even and odd supported frames with independent robust lines."""

    if len(times) < 12:
        return None
    errors: list[np.ndarray] = []
    for train_start in (0, 1):
        train = np.arange(train_start, len(times), 2)
        test = np.arange(1 - train_start, len(times), 2)
        fit = frequency_line(times[train], values[train])
        if fit is None or not len(test):
            return None
        predicted = fit.intercept_at_reference_hz + fit.slope_hz_per_s * (
            times[test] - fit.reference_time_s
        )
        errors.append(values[test] - predicted)
    combined = np.concatenate(errors)
    return float(math.sqrt(np.mean(combined**2)))


def line_slope_sigma(times: np.ndarray, fit: HuberLinearFit | None) -> float | None:
    """Return the residual-derived one-sigma scale of a local slope."""

    if fit is None or len(times) < 3:
        return None
    denominator = float(np.sum((times - fit.reference_time_s) ** 2))
    return fit.residual_rms_hz / math.sqrt(denominator) if denominator > 0 else None


def stable_measurement_floats(value: Any) -> Any:
    """Quantize persisted measurements beyond relevant RF precision."""

    if isinstance(value, float):
        return float(format(value, ".12g"))
    if isinstance(value, dict):
        return {key: stable_measurement_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [stable_measurement_floats(item) for item in value]
    if isinstance(value, tuple):
        return tuple(stable_measurement_floats(item) for item in value)
    return value
