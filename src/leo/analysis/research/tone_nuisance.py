"""Bounded stationary-tone nuisance fitting for offline detector experiments.

This is not a signal-presence verdict. Removing a fitted component may remove
part of a real signal; callers must preserve original IQ and label the transform.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ToneFit:
    applied: bool
    frequency_hz: float | None
    spectral_fraction: float
    fitted_power_fraction: float


def remove_stationary_tone(samples, rate):
    """Try one tone, with fixed spectral/energy guards; return new IQ plus evidence."""
    values = np.asarray(samples, dtype=np.complex128)
    if (
        rate not in (2500000, 5000000)
        or values.shape != (rate // 50,)
        or not np.all(np.isfinite(values))
        or np.any(np.abs(values.real) > 1e12)
        or np.any(np.abs(values.imag) > 1e12)
    ):
        raise ValueError("one finite 20ms probe at a supported rate is required")
    energy = float(np.vdot(values, values).real)
    if energy == 0:
        return values.copy(), ToneFit(False, None, 0, 0)
    size = 4096 if rate == 2500000 else 8192
    spectrum = np.abs(np.fft.fft(values[:size])) ** 2
    peak = int(np.argmax(spectrum))
    indices = np.array([peak - 1, peak, peak + 1]) % size
    fraction = float(spectrum[indices].sum() / max(spectrum.sum(), np.finfo(float).tiny))
    if fraction < 0.02:
        return values.copy(), ToneFit(False, None, fraction, 0)
    signed = peak if peak < size // 2 else peak - size
    frequency = signed * rate / size
    # Increasing integer lags refine phase. Each ambiguity branch is selected
    # from the preceding estimate, never from a reference signal label/CFO.
    for lag in (256, 4096, 16384):
        product = np.vdot(values[:-lag], values[lag:])
        if abs(product) <= np.finfo(float).tiny:
            return values.copy(), ToneFit(False, None, fraction, 0)
        period = rate / lag
        local = float(np.angle(product)) * period / (2 * np.pi)
        frequency = local + round((frequency - local) / period) * period
    oscillator = np.exp(2j * np.pi * frequency * np.arange(len(values)) / rate)
    amplitude = np.vdot(oscillator, values) / len(values)
    fitted = float(abs(amplitude) ** 2 * len(values) / energy)
    if fitted < 0.01:
        return values.copy(), ToneFit(False, frequency, fraction, fitted)
    residual = values - amplitude * oscillator
    return residual, ToneFit(True, frequency, fraction, fitted)
