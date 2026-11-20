"""Raw three-frame cross-coherence timing with a known Qin edge contrast."""

from functools import lru_cache

import numpy as np

RATE = 10_000_000
FRAME = 13_333
LAG = 40_000
SAMPLES = RATE // 50
FFT = 32_768
STARTS = tuple(round(i * LAG / 3) for i in range(12))


@lru_cache(maxsize=2)
def filters(edge):
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

    out = []
    for roll in (0, CONTROL_SYMBOL_ROLL):
        h = qin_edge_pilot_frame(RATE, edge, symbol_roll=roll)
        p = (h.real * h.real + h.imag * h.imag).astype(np.float32)
        p -= p.mean(dtype=np.float64)
        p /= np.linalg.norm(p)
        out.append(np.fft.fft(p, n=FFT).conj())
    return tuple(out)


def circular_prompt(observed_fft, reference_fft):
    """Recover all frame-circular lags by folding the two linear partial sums."""
    corr = np.fft.ifft(observed_fft * reference_fft, axis=-1)
    positive = corr[..., :FRAME]
    positive[..., 1:] += corr[..., FFT - FRAME + 1 :]
    return positive


def coherent_surface(samples, edge):
    if samples.shape != (SAMPLES, 2, 2) or samples.dtype != np.dtype("<i2"):
        raise ValueError("Expected the original 20 ms dual-RX 10 MS/s CI16 window")
    exact, control = filters(edge)
    x = np.empty((2, SAMPLES), dtype=np.complex64)
    x.real, x.imag = samples[:, :, 0].T, samples[:, :, 1].T
    folded = np.zeros((2, 3, FRAME), dtype=np.complex64)
    pair = np.empty((2, FRAME), dtype=np.complex64)
    for i, start in enumerate(STARTS):
        np.conjugate(x[:, start : start + FRAME], out=pair)
        pair *= x[:, start + LAG : start + LAG + FRAME]
        folded[:, i % 3] += pair

    energy = (folded.real**2 + folded.imag**2).sum(axis=-1, dtype=np.float64)
    folded -= folded.mean(axis=-1, dtype=np.complex128, keepdims=True)
    y = np.fft.fft(folded, n=FFT, axis=-1)
    a, b = circular_prompt(y, exact), circular_prompt(y, control)
    power = (a.real**2 + a.imag**2) - (b.real**2 + b.imag**2)
    return (power / np.maximum(energy[..., None], 1)).sum(axis=1)


def ranked_centers(surface, capacity=16):
    if surface.shape != (FRAME,) or not 1 <= capacity <= 16:
        raise ValueError("Unsupported timing surface or scout budget")
    left, right = np.roll(surface, 1), np.roll(surface, -1)
    positive = (surface > 0) & (surface >= left) & (surface >= right)
    peaks = np.flatnonzero(positive & ((surface > left) | (surface > right)))
    order = peaks[np.argsort(-surface[peaks], kind="stable")]
    centers = []
    for k in map(int, order):
        if all(min(abs(k - p), FRAME - abs(k - p)) >= 5 for p in centers):
            centers.append(k)
            if len(centers) == capacity:
                break
    return centers


def scout(samples, edge):
    surface = coherent_surface(samples, edge)
    ranks = [ranked_centers(row) for row in surface]
    return [
        (rank, [float(values[x]) for x in rank])
        for rank, values in zip(ranks, surface, strict=True)
    ]
