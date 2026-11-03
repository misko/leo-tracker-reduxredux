"""Research-only frequency-selective known-pilot subtraction for saved IQ.

Each of the eight published tones has its own complex channel coefficient in
each complete frame. This is a specificity control, not an acquisition or
localization measurement. It uses no orbital or geographic information.
"""

from functools import lru_cache
import math

import numpy as np

from leo.analysis.starlink.templates import (
    CYCLIC_PREFIX_DURATION_S, OFDM_SYMBOL_DURATION_S,
    edge_frequencies_hz, qin_edge_pilot_symbols,
)
from probe_native_code_carrier import interpolate_periodic, periodic_upsample


def pilot_tone_frames(fs, edge):
    """Return the eight components whose sum is the canonical pilot frame."""
    count = round(fs / 750)
    t = np.arange(count) / fs
    index = np.floor(t / OFDM_SYMBOL_DURATION_S).astype(int)
    selected = (index >= 2) & (index < 302)
    output = np.zeros((count, 8), dtype=complex)
    local = t[selected] - index[selected] * OFDM_SYMBOL_DURATION_S
    symbols = qin_edge_pilot_symbols(edge)
    output[selected] = symbols[index[selected] - 2] * np.exp(
        2j * np.pi * (local[:, None] - CYCLIC_PREFIX_DURATION_S)
        * edge_frequencies_hz(edge)[None, :]
    ) / math.sqrt(8)
    return output


@lru_cache(maxsize=4)
def tone_waves(fs, edge):
    frames = pilot_tone_frames(fs, edge)
    wave = np.zeros((round(fs / 250), 8), dtype=complex)
    for frame in range(3):
        start = round(frame * fs / 750)
        stop = min(start + len(frames), len(wave))
        wave[start:stop] += frames[:stop - start]
    return tuple(periodic_upsample(wave[:, k], 32) for k in range(8))


def project_pilot_channel(samples, fs, edge, epoch, fit, *, delay_taps=(0.,)):
    """Remove a per-frame, per-tone known pilot channel, retaining noise/data."""
    y = np.asarray(samples, complex)
    if y.ndim != 1 or len(y) < 100 or not np.isfinite(y).all():
        raise ValueError("finite one-dimensional samples required")
    if not delay_taps or len(delay_taps) > 5:
        raise ValueError("one to five bounded delay taps required")
    if any(abs(tap) > 2 for tap in delay_taps):
        raise ValueError("delay taps must stay within two samples")
    n = np.arange(len(y))
    t = n / fs
    rotation = np.exp(2j * np.pi * fit['CFO_hz'] * (t - t.mean()))
    columns = []
    for tap in delay_taps:
        position = (n - epoch - fit['offset_samples'] - tap) * (
            1 + fit['modulation_ppm'] * 1e-6) * 32
        for wave in tone_waves(fs, edge):
            columns.append(interpolate_periodic(wave, position) * rotation)
    design = np.column_stack(columns + [np.ones(len(y))])
    residual = np.zeros_like(y)
    period = fs / 750
    frame = 0
    ranks = []
    while epoch + (frame + 1) * period + 16 < len(y):
        ix = np.flatnonzero((n >= epoch + frame * period + 16)
                            & (n < epoch + (frame + 1) * period - 16))
        coefficient, _, rank, _ = np.linalg.lstsq(design[ix], y[ix], rcond=1e-8)
        residual[ix] = y[ix] - design[ix] @ coefficient
        ranks.append(int(rank))
        frame += 1
    if frame < 4:
        raise ValueError("at least four complete frames required")
    return residual, dict(frames=frame, channel_columns=design.shape[1], ranks=ranks,
                         energy_fraction=float(np.vdot(residual, residual).real
                                               / np.vdot(y, y).real))


def project_arbitrary_pilot_symbols(samples, fs, edge, epoch, fit):
    """Null all eight pilot tones with arbitrary amplitudes every OFDM symbol.

    This intentionally removes more than the published sequence: a common
    residual cannot be attributed to any sequence on these eight subcarriers
    in an ideal flat channel. Real bandlimiting and interpolation can still
    mix symbols, so matched controls remain necessary.
    """
    y = np.asarray(samples, complex)
    n = np.arange(len(y))
    local_samples = (n - epoch - fit['offset_samples']) * (
        1 + fit['modulation_ppm'] * 1e-6)
    frame_time = (local_samples / fs) % (1 / 750)
    frame_index = np.floor(local_samples / fs * 750).astype(int)
    symbol_index = np.floor(frame_time / OFDM_SYMBOL_DURATION_S).astype(int)
    local_time = frame_time - symbol_index * OFDM_SYMBOL_DURATION_S
    active = (local_samples >= 0) & (symbol_index >= 2) & (symbol_index < 302)
    frequencies = edge_frequencies_hz(edge)
    carrier = np.exp(2j * np.pi * fit['CFO_hz'] * n / fs)
    design = np.exp(2j * np.pi * local_time[:, None] * frequencies[None, :]) * carrier[:, None]
    residual = np.zeros_like(y)
    labels = frame_index * 303 + symbol_index
    labels[~active] = -1
    cuts = np.r_[0, np.flatnonzero(np.diff(labels)) + 1, len(labels)]
    groups = 0
    for start, stop in zip(cuts[:-1], cuts[1:]):
        if labels[start] < 0 or stop - start < 9:
            continue
        ix = slice(start, stop)
        coefficient = np.linalg.lstsq(design[ix], y[ix], rcond=1e-8)[0]
        residual[ix] = y[ix] - design[ix] @ coefficient
        groups += 1
    return residual, dict(symbols=groups,
        energy_fraction=float(np.vdot(residual, residual).real / np.vdot(y, y).real))


def advance_samples(samples, advance):
    """Fractional time advance with zero padding, for epoch-matched controls."""
    y = np.asarray(samples, complex)
    if not np.isfinite(advance) or abs(advance) > len(y) / 4:
        raise ValueError('bounded finite control shift required')
    size = 1 << int(np.ceil(np.log2(2 * len(y))))
    rotated = np.fft.ifft(np.fft.fft(y, size) * np.exp(
        2j * np.pi * np.fft.fftfreq(size) * advance))[:len(y)]
    # Remove edges that would lack real input support after the shift.
    trim = int(np.ceil(abs(advance))) + 4
    rotated[:trim] = 0
    rotated[-trim:] = 0
    return rotated
