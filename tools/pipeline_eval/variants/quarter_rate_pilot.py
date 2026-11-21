"""Blind acquisition from the leading repeated waveform at quarter sample rate."""

import numpy as np
from scipy import signal

from leo.analysis.starlink.templates import qin_edge_pilot_frame

from . import full_epoch_glrt as g


def acquire(samples, edge, lo, hi):
    middle = (lo + hi) / 2
    if middle:
        phase = (-2j * np.pi * middle / g.RATE) * np.arange(len(samples))
        samples = np.asarray(samples * np.exp(phase), np.complex64)
    rate = g.RATE // 4
    data = signal.resample_poly(samples, 1, 4)
    template = signal.resample_poly(qin_edge_pilot_frame(g.RATE, edge), 1, 4)
    start = g.FIRST // 4
    code = template[start : start + 24 * g.SYMBOL // 4]
    width = round(rate / 750) + len(code) - 1
    starts = np.rint(np.arange(14) * rate / 750).astype(int) + start
    frames = data[starts[:, None] + np.arange(width)]
    frames -= frames.mean(axis=1, keepdims=True)
    frames /= np.maximum(np.sqrt((np.abs(frames) ** 2).mean(axis=1, keepdims=True)), 1e-10)
    _, axes = np.linalg.eigh(frames @ frames.conj().T)
    common = axes[:, -1].conj() @ frames
    grid = g.sweep(
        common,
        code,
        rate=rate,
        first=0,
        frames=np.array([0]),
        split=np.array([0]),
        hz=g.frequency_grid(lo - middle, hi - middle, 12 * g.RATE / g.NFFT),
        nfft=g.NFFT // 4,
    )
    grid.epochs *= 4
    grid.hz += middle
    return g.distinct(grid, 4)


def detect(samples, edge, lo, hi, verify):
    code = g.pilot(edge)
    first, second = np.array([0, 9]), np.array([4, 13])
    finalists = []
    for epoch, hz in acquire(samples, edge, lo, hi):
        epochs = (epoch + np.arange(-4, 5)) % g.PERIOD
        freq = np.unique(np.clip(hz + np.arange(-4500, 4501, 750), lo, hi))
        values = np.minimum(
            g.powers(samples, code, epochs, freq, first),
            g.powers(samples, code, epochs, freq, second),
        )
        i, j = np.unravel_index(np.argmax(values), values.shape)
        finalists.append((float(values[i, j]), int(epochs[i]), float(freq[j])))
    for _, epoch, hz in sorted(finalists, reverse=True):
        result = verify(epoch, hz)
        if result["gate"]:
            return result
    return None
