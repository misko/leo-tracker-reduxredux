"""Experimental, storage-free prefilters for saved 20 ms narrowband windows.

Scores are features, not calibrated detections. No GLRT result is an input.
The reduced pilot search deliberately trades support for cost: four symbols,
two complete frames and a coarse CFO grid, without fractional timing refinement.
"""
from __future__ import annotations

import numpy as np


def _samples(iq: np.ndarray) -> np.ndarray:
    values = np.asarray(iq, dtype=np.complex128)
    if values.ndim != 1 or values.size < 1024 or not np.isfinite(values).all():
        raise ValueError("expected a finite one-dimensional IQ window")
    return values


def power_features(iq: np.ndarray, sample_rate_hz: float) -> dict[str, float]:
    """Match adaptive mean-component dBFS; use 1 ms energy bins for spread."""
    x = _samples(iq)
    energy = x.real**2 + x.imag**2
    block = round(sample_rate_hz * .001)
    if block < 1 or x.size < 4 * block:
        raise ValueError("at least four 1 ms blocks required")
    means = energy[:x.size // block * block].reshape(-1, block).mean(axis=1)
    tiny = np.finfo(float).tiny
    block_db = 10 * np.log10(np.maximum(means, tiny))
    total_db = 10 * np.log10(max(float(energy.mean()), tiny))
    return {
        "power_dbfs": total_db - 10 * np.log10(2 * 32768.0**2),
        "burst_spread_db": float(np.percentile(block_db, 90) - np.percentile(block_db, 10)),
        "burst_peak_db": float(block_db.max() - total_db),
        "dc_fraction": float(abs(x.mean())**2 / max(float(energy.mean()), tiny)),
    }


def repeat_features(iq: np.ndarray, sample_rate_hz: float) -> dict[str, float]:
    """Three-frame coherence minus off-frame controls, in 1 ms blocks.

Nearby target delays accommodate up to one sample of clock/delay error. Block
power normalization removes gain; control delays reject persistent pure tones.
Subtract DC before correlation. Controls do not make this Starlink-specific.
"""
    x = _samples(iq)
    x = x - x.mean()
    lag = round(sample_rate_hz * .004)
    offset = max(3, round(sample_rate_hz * 14.8e-6))
    block = round(sample_rate_hz * .001)
    count = (x.size - lag - offset) // block * block
    if count < block or lag <= 1:
        raise ValueError("insufficient frame-repeat support")
    a = x[:count].reshape(-1, block)
    ea = np.mean(abs(a)**2, axis=1)

    def coherence(delay: int) -> float:
        b = x[delay:delay + count].reshape(-1, block)
        denom = ea * np.mean(abs(b)**2, axis=1)
        cross = abs(np.mean(a.conj() * b, axis=1))**2
        return float(np.mean(np.divide(cross, denom, out=np.zeros_like(cross), where=denom > 0)))

    target = max(coherence(lag + d) for d in (-1, 0, 1))
    control = .5 * (coherence(lag - offset) + coherence(lag + offset))
    return {"repeat_excess": target - control, "repeat_coherence": target,
            "repeat_control": control}


def spectrum_features(iq: np.ndarray, sample_rate_hz: float) -> dict[str, float]:
    """Nonoverlapping 1024-point Hann spectra over the complete window.

Use the inner 80% of sampled bandwidth, excluding three DC bins; this avoids
the steepest filter edges, but channel response still requires calibration.
"""
    x = _samples(iq)
    blocks = x[:x.size // 1024 * 1024].reshape(-1, 1024)
    blocks = blocks - blocks.mean(axis=1, keepdims=True)
    psd = np.mean(abs(np.fft.fft(blocks * np.hanning(1024), axis=1))**2, axis=0)
    f = np.fft.fftfreq(1024, 1 / sample_rate_hz)
    selected = psd[(abs(f) < .4 * sample_rate_hz) & (abs(f) > 1.5 * sample_rate_hz / 1024)]
    selected = np.maximum(selected, np.finfo(float).tiny)
    return {
        "spectral_contrast_db": float(
            10 * np.log10(np.percentile(selected, 90) / np.percentile(selected, 10))
        ),
        "spectral_nonflatness": float(1 - np.exp(np.mean(np.log(selected))) / np.mean(selected)),
        "spectral_peak_fraction": float(selected.max() / selected.sum()),
    }


def reduced_pilot_features(
    iq: np.ndarray, sample_rate_hz: float, exact: np.ndarray, control: np.ndarray,
    center_hz: float = 0.0, half_width_hz: float = 429687.5,
) -> dict[str, float]:
    """Coarse pilot evidence, using no full-GLRT timing or CFO information.

Search every integer epoch of a frame. Four symbol correlations are normalized
individually and combined noncoherently across two frames. Select by exact
score, then subtract the rolled-control score at that same CFO/epoch. The
control is not independently optimized. Approximate sampled-frame alignment
and the sparse anchors are intentionally weaker than standard acquisition.
"""
    x = _samples(iq)
    if sample_rate_hz != 2500000:
        raise ValueError("reduced-pilot prototype is qualified only at 2.5 MS/s")
    if half_width_hz <= 0:
        raise ValueError("empty pilot CFO search")
    x = x[:10000]
    if x.size != 10000:
        raise ValueError("reduced pilot requires the first 4 ms")
    period = sample_rate_hz / 750
    epochs = np.arange(int(np.ceil(period)))
    starts = [round(s * sample_rate_hz * 4.4e-6) for s in (2, 80, 160, 240)]
    width = 11
    if min(len(exact), len(control)) <= starts[-1] + width:
        raise ValueError("pilot templates do not cover selected symbols")
    powers = np.concatenate(([0.0], np.cumsum(abs(x)**2)))
    energy = powers[width:] - powers[:-width]
    frequencies = np.unique(np.r_[np.linspace(-half_width_hz, half_width_hz,
                                    int(np.ceil(2 * half_width_hz / 80000)) + 1), 0.0]) + center_hz
    time_s = np.arange(x.size) / sample_rate_hz
    best = (-np.inf, 0.0, 0.0, 0)
    for freq in frequencies:
        rotated = x * np.exp(-2j * np.pi * freq * time_s)
        maps = []
        for template in (exact, control):
            scores = np.zeros(epochs.size)
            for start in starts:
                replica = template[start:start + width]
                denom = energy * float(np.vdot(replica, replica).real)
                correlation = abs(np.correlate(rotated, replica, mode='valid'))**2
                normalized = np.divide(
                    correlation, denom, out=np.zeros_like(correlation), where=denom > 0
                )
                for frame in (0, 1):
                    indexes = epochs + round(frame * period) + start
                    scores += normalized[indexes]
            maps.append(scores / 8)
        index = int(np.argmax(maps[0]))
        if maps[0][index] > best[0]:
            best = (float(maps[0][index]), float(maps[1][index]), float(freq), index)
    return {"pilot_margin": best[0] - best[1], "pilot_exact": best[0],
            "pilot_control": best[1], "pilot_cfo_hz": best[2],
            "pilot_epoch_sample": best[3]}
