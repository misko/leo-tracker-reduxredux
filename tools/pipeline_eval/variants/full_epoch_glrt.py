"""All-epoch, full-band matched-filter GLRT for an unknown complex gain per frame."""

from dataclasses import dataclass

import numpy as np
from scipy import fft, signal

from leo.analysis.starlink.templates import (
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)

RATE = 10_000_000
PERIOD = round(RATE / FRAME_RATE_HZ)
ALIAS = 1 / OFDM_SYMBOL_DURATION_S
NFFT = 16_384
FIRST = 88
SYMBOL = 44
WIDTH = 2_000.0
EVEN = np.arange(0, 14, 2)
ODD = np.arange(1, 14, 2)


@dataclass
class Sweep:
    hz: np.ndarray
    epochs: np.ndarray  # frequency, frame partition, local peak rank
    scores: np.ndarray


def pilot(edge, wrong=False):
    template = qin_edge_pilot_frame(RATE, edge)
    code = template[FIRST : FIRST + 64 * SYMBOL].copy()
    if wrong:
        order = np.random.default_rng(51961).permutation(64)
        code = code.reshape(64, SYMBOL)[order].reshape(-1)
    return code


def frequency_grid(lo, hi, spacing):
    if hi <= lo or spacing <= 0:
        raise ValueError("invalid CFO interval")
    bins = np.arange(np.ceil(lo / spacing), np.floor(hi / spacing) + 1) * spacing
    return np.unique(np.r_[lo, bins, hi])


def sweep(samples, code, *, rate, first, frames, split, hz, nfft, ranks=3):
    """Linear correlation at every integer epoch, including both sides of the frame seam."""
    epochs = round(rate / FRAME_RATE_HZ)
    width = len(code)
    support = epochs + width - 1
    if support > nfft or len(frames) != len(split):
        raise ValueError("FFT too short or invalid frame partition")
    starts = np.rint(frames * (rate / FRAME_RATE_HZ)).astype(int) + first
    if min(starts) < 0 or max(starts) + support > len(samples):
        raise ValueError("incomplete frame support")
    data = np.asarray(samples[starts[:, None] + np.arange(support)], np.complex64)
    energy = np.empty((len(frames), support + 1), np.float64)
    energy[:, 0] = 0
    np.cumsum(data.real**2 + data.imag**2, axis=1, dtype=np.float64, out=energy[:, 1:])
    sliding = energy[:, width:] - energy[:, :-width]
    groups = [np.flatnonzero(split == k) for k in np.unique(split)]
    denom = np.array(
        [np.maximum(np.sum(sliding[g], axis=0) * np.vdot(code, code).real, 1e-20) for g in groups],
        dtype=np.float32,
    )
    spectrum = fft.fft(data, n=nfft, axis=-1)
    base = fft.fft(code, n=nfft)
    scores = np.empty((len(hz), len(groups), ranks), np.float32)
    times = np.empty(scores.shape, np.int32)
    # Frequency shifts on the FFT grid cost one circular reindex of the template spectrum.
    # For non-grid endpoints use the exact modulated reference.
    sample_time = np.arange(width) / rate
    indexes = np.arange(nfft)
    row = np.arange(len(groups))
    for i, f in enumerate(hz):
        bin_index = f * nfft / rate
        if abs(bin_index - round(bin_index)) < 1e-8:
            spec = base[(indexes - round(bin_index)) % nfft]
        else:
            spec = fft.fft(
                np.asarray(code * np.exp(2j * np.pi * f * sample_time), np.complex64), n=nfft
            )
        corr = fft.ifft(spectrum * spec.conj(), axis=-1)[:, :epochs]
        power = corr.real**2 + corr.imag**2
        values = np.asarray([np.sum(power[g], axis=0) for g in groups]) / denom
        for rank in range(ranks):
            best = np.argmax(values, axis=1)
            times[i, :, rank] = best
            scores[i, :, rank] = values[row, best]
            values[row[:, None], (best[:, None] + np.arange(-5, 6)) % epochs] = -1
    return Sweep(np.asarray(hz), times, scores)


def reference(samples, edge, lo, hi):
    frames = np.arange(14)
    return sweep(
        samples,
        pilot(edge),
        rate=RATE,
        first=FIRST,
        frames=frames,
        split=frames % 2,
        hz=frequency_grid(lo, hi, 2 * RATE / NFFT),
        nfft=NFFT,
    )


def compact(samples, edge, lo, hi):
    """Short pilot scout at half rate on three frames, independent of satellite nominations."""
    mid = (lo + hi) / 2
    n = np.arange(len(samples))
    centered = samples if mid == 0 else samples * np.exp((-2j * np.pi * mid / RATE) * n)
    data = signal.resample_poly(np.asarray(centered, np.complex64), 1, 2)
    template = signal.resample_poly(qin_edge_pilot_frame(RATE, edge), 1, 2)
    code = template[FIRST // 2 : (FIRST + 16 * SYMBOL) // 2]
    frames = np.array([0, 6, 12])
    result = sweep(
        data,
        code,
        rate=RATE // 2,
        first=FIRST // 2,
        frames=frames,
        split=np.zeros(len(frames), int),
        hz=frequency_grid(lo - mid, hi - mid, 16 * RATE / NFFT),
        nfft=NFFT // 2,
        ranks=3,
    )
    result.hz += mid
    result.epochs *= 2
    return result


def best(s, group, center=None):
    take = np.ones(len(s.hz), bool) if center is None else np.abs(s.hz - center) <= WIDTH
    if not np.any(take):
        return None
    ids = np.flatnonzero(take)
    i = ids[np.argmax(s.scores[ids, group, 0])]
    return int(s.epochs[i, group, 0]), float(s.hz[i]), float(s.scores[i, group, 0])


def distinct(s, count):
    values = s.scores[:, 0, :]
    out = []
    for index in np.argsort(-values.ravel(), kind="stable"):
        i, k = np.unravel_index(index, values.shape)
        e, f = int(s.epochs[i, 0, k]), float(s.hz[i])
        if all(
            abs((e - t + PERIOD / 2) % PERIOD - PERIOD / 2) > 5 or abs(f - h) > 12_000
            for t, h in out
        ):
            out.append((e, f))
        if len(out) == count:
            break
    return out


def powers(samples, code, epochs, hz, frames):
    """Direct independent calculation at selected cells, also used to test the FFT search."""
    n = np.arange(len(code))
    starts = np.rint(frames * (RATE / FRAME_RATE_HZ)).astype(int) + FIRST
    refs = (code[None, :] * np.exp(2j * np.pi * hz[:, None] * n[None, :] / RATE)).astype(
        np.complex64
    )
    blocks = samples[epochs[:, None, None] + starts[None, :, None] + n]
    corr = blocks @ refs.conj().T
    energy = (np.abs(blocks) ** 2).sum(axis=(1, 2), dtype=np.float64) * np.vdot(code, code).real
    return (np.abs(corr) ** 2).sum(axis=1, dtype=np.float64) / np.maximum(1e-20, energy[:, None])


def refine(samples, code, e, f, frames, lo, hi, *, radius=1500, step=125, span=2):
    epochs = (e + np.arange(-span, span + 1)) % PERIOD
    hz = np.unique(np.clip(f + np.arange(-radius, radius + step / 2, step), lo, hi))
    score = powers(samples, code, epochs, hz, frames)
    i, j = np.unravel_index(np.argmax(score), score.shape)
    return dict(epoch=int(epochs[i]), hz=float(hz[j]), score=float(score[i, j]))


def branches(hz, lo, hi):
    return [
        (k, hz + k * ALIAS)
        for k in range(
            int(np.ceil((lo - WIDTH - hz) / ALIAS)), int(np.floor((hi + WIDTH - hz) / ALIAS)) + 1
        )
    ]
