"""Estimate CFO at already nominated Qin pilot times from two sample lags."""

from functools import lru_cache

import numpy as np

from . import differential_pilot as timing

SHORT_LAG = 4
LIMIT_HZ = 800_000
GRID_HZ = 80_000


def frequency_options(phase, lag, rate=timing.RATE):
    """Enumerate signed physical frequencies consistent with the measured lag phase."""
    spacing = rate / lag
    base = phase * spacing / (2 * np.pi)
    low = int(np.ceil((-LIMIT_HZ - base) / spacing))
    high = int(np.floor((LIMIT_HZ - base) / spacing))
    return [float(base + step * spacing) for step in range(low, high + 1)]


def resolve(long_value, short_value):
    if not abs(long_value) or not abs(short_value):
        return None
    long_phase = np.angle(long_value)
    short_phase = np.angle(short_value)
    options = frequency_options(long_phase, timing.LAG)
    short_hz = float(short_phase * timing.RATE / (2 * np.pi * SHORT_LAG))
    best = min(options, key=lambda hz: abs(hz - short_hz))
    return dict(
        folded_hz=float(long_phase * timing.RATE / (2 * np.pi * timing.LAG)),
        short_hz=short_hz,
        absolute_hz=best,
        grid_hz=GRID_HZ * round(best / GRID_HZ),
    )


@lru_cache(maxsize=4)
def coefficients(edge, lag):
    if lag == timing.LAG:
        return timing.template_products(edge)
    if lag != SHORT_LAG:
        raise ValueError("unsupported differential lag")
    wave, active = timing.phase_templates(edge)
    valid = active[:, lag:] & active[:, :-lag]
    pair = wave[:, lag:] * wave[:, :-lag].conj()
    mean = np.sum(np.where(valid, pair, 0), axis=1, dtype=np.complex128) / valid.sum(axis=1)
    out = np.zeros_like(wave)
    out[:, :-lag] = np.where(valid, pair - mean[:, None], 0)
    return out


def products(samples, receiver):
    if samples.shape != (timing.SAMPLES, 2, 2) or samples.dtype != np.dtype("<i2"):
        raise ValueError("expected 20 ms of dual-receiver signed CI16 at 10 MS/s")
    if receiver not in (0, 1):
        raise ValueError("unknown raw receiver")
    stream = np.empty(timing.SAMPLES, dtype=np.complex64)
    stream.real, stream.imag = samples[:, receiver, 0], samples[:, receiver, 1]
    out = []
    for lag in (timing.LAG, SHORT_LAG):
        pair = stream[lag:] * stream[:-lag].conj()
        pair -= pair.mean(dtype=np.complex128)
        out.append(pair)
    return out


def at_epoch(pairs, edge, epoch):
    """Project the two received lag products onto the coded pilot at one integer start."""
    if type(epoch) is not int or not 0 <= epoch < timing.FRAME:
        raise ValueError("pilot time is outside one nominal frame")
    projected = []
    for lag, signal in zip((timing.LAG, SHORT_LAG), pairs, strict=True):
        # The long lag uses the entire timing scout's exact-template inner product.
        # The short lag uses one in four samples, fixing the sampling phase to the pilot.
        step = 1 if lag == timing.LAG else 4
        kernel = coefficients(edge, lag)
        value = 0j
        for residue, offset in timing.STARTS:
            start = epoch + offset
            left = max(0, -start)
            left += (-left) % step
            right = min(timing.FRAME, len(signal) - start)
            if left < right:
                x = signal[start + left : start + right : step]
                weight = kernel[residue, left:right:step]
                value += np.sum(x * weight.conj(), dtype=np.complex128)
        projected.append(value)
    return resolve(*projected)
