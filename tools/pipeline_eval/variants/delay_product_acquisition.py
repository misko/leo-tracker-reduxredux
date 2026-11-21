"""Blind Qin pilot acquisition by estimating timing before searching signed carrier frequency."""

from functools import lru_cache

import numpy as np
from scipy import fft, signal

from leo.analysis.starlink.templates import qin_edge_pilot_frame

from . import full_epoch_glrt as g

HALF_RATE_LAGS = (3, 7, 13, 22, 37, 55, 88, 149)
STARTS = np.rint(np.arange(14) * g.RATE / 750).astype(int) + g.FIRST
NATIVE_OFFSETS = np.arange(64 * g.SYMBOL)
FREQUENCY_FFT = 4096
HELD_START = (160, 232)


@lru_cache(maxsize=8)
def templates(edge, stride=2, prefilter=True):
    full = qin_edge_pilot_frame(g.RATE, edge)
    low = signal.resample_poly(full, 1, stride) if prefilter else full[::stride]
    h = low[g.FIRST // stride : (g.FIRST + 128 * g.SYMBOL) // stride]
    nfft = 32768 // stride
    filters = []
    for d in HALF_RATE_LAGS:
        lag = max(1, round(2 * d / stride))
        p = h[lag:] * h[:-lag].conj()
        p -= p.mean()
        filters.append((lag, fft.fft(p, n=nfft).conj() / np.linalg.norm(p)))
    held = [
        full[g.FIRST + start * g.SYMBOL : g.FIRST + (start + 64) * g.SYMBOL] for start in HELD_START
    ]
    return h, filters, full[g.FIRST : g.FIRST + 64 * g.SYMBOL], held


def timing(samples, edge, center, stride=2, prefilter=True, native=None):
    code, filters, _, _ = templates(edge, stride, prefilter)
    rate = g.RATE // stride
    epochs = round(rate / 750)
    if not prefilter:
        half = samples[::stride]
        if center:
            half = np.asarray(
                half * np.exp((-2j * np.pi * center / rate) * np.arange(len(half))), np.complex64
            )
    else:
        if center:
            samples = np.asarray(
                samples * np.exp((-2j * np.pi * center / g.RATE) * np.arange(len(samples))),
                np.complex64,
            )
        half = (
            native.decimate(samples, stride) if native else signal.resample_poly(samples, 1, stride)
        )
    width = epochs + len(code) - 1
    start = np.rint(np.arange(14) * rate / 750).astype(int) + g.FIRST // stride
    frames = half[start[:, None] + np.arange(width)]
    frames -= frames.mean(axis=1, keepdims=True)
    frames /= np.maximum(np.sqrt(np.mean(np.abs(frames) ** 2, axis=1, keepdims=True)), 1e-12)
    _, basis = np.linalg.eigh(frames @ frames.conj().T)
    modes = basis[:, -2:].conj().T @ frames
    score = np.zeros(epochs)
    for lag, kernel in filters:
        pair = (modes[:, lag:] * modes[:, :-lag].conj()).sum(axis=0)
        z = fft.ifft(fft.fft(pair, n=len(kernel)) * kernel)[:epochs]
        prefix = np.r_[0.0, np.cumsum(abs(pair) ** 2, dtype=float)]
        length = len(code) - lag
        energy = prefix[length:] - prefix[:-length]
        score += np.abs(z) ** 2 / np.maximum(energy, 1e-20)
    candidates = []
    for _ in range(12):
        e = int(np.argmax(score))
        candidates.append(e)
        radius = max(1, round(6 / stride))
        score[(e + np.arange(-radius, radius + 1)) % epochs] = -1
    return modes, candidates


@lru_cache(maxsize=16)
def band(lo, hi, rate):
    hz = fft.fftfreq(FREQUENCY_FFT, 1 / rate)
    lower = np.ceil((lo - hz) / rate).astype(int)
    upper = np.floor((hi - hz) / rate).astype(int)
    return hz, np.flatnonzero(lower <= upper), lower, upper


def carriers(modes, epochs, edge, lo, hi, center, stride=2, prefilter=True):
    rate = g.RATE // stride
    code = templates(edge, stride, prefilter)[0][: 64 * g.SYMBOL // stride]
    windows = modes[:, np.asarray(epochs)[:, None] + np.arange(len(code))]
    spectrum = fft.fft(windows * code.conj(), n=FREQUENCY_FFT, axis=-1)
    norm = np.maximum((np.abs(windows) ** 2).sum(axis=(0, 2)), 1e-15)
    powers = (np.abs(spectrum) ** 2).sum(axis=0) / norm[:, None]
    hz, inside, lower, upper = band(lo - center, hi - center, rate)
    if not len(inside):
        return []
    subset = powers[:, inside].copy()
    proposals = []
    for _ in range(2):
        bins = subset.argmax(axis=1)
        for i, j in enumerate(bins):
            index = inside[j]
            f = hz[index]
            proposals.append((float(subset[i, j]), epochs[i] * stride, index))
            subset[i, abs((hz[inside] - f + rate / 2) % rate - rate / 2) < 10000] = -1
    finalists = []
    for score, epoch, j in sorted(proposals, reverse=True)[:4]:
        for alias in range(lower[j], upper[j] + 1):
            finalists.append((score, epoch, float(hz[j] + center + alias * rate)))
    return finalists


def measured_peak(samples, code, epoch, hz, lo, hi):
    epochs = (epoch + np.arange(-4, 5)) % g.PERIOD
    ref = code.conj() * np.exp((-2j * np.pi * hz / g.RATE) * NATIVE_OFFSETS).astype(np.complex64)
    blocks = samples[epochs[:, None, None] + STARTS[None, :, None] + NATIVE_OFFSETS]
    part = (blocks * ref).reshape(len(epochs), len(STARTS), 8, -1).sum(axis=-1)
    lag = (part[:, :, 4:] * part[:, :, :4].conj()).sum(axis=(1, 2))
    delta = np.angle(lag) * g.RATE / (2 * np.pi * (len(code) // 2))
    adjusted = np.clip(hz + delta, lo, hi)
    phase = np.exp(
        (-2j * np.pi * len(code) / 8 / g.RATE) * (adjusted - hz)[:, None] * np.arange(8)
    ).astype(np.complex64)
    projected = np.abs((part * phase[:, None, :]).sum(axis=2)) ** 2
    energy = (np.abs(blocks) ** 2).sum(axis=2)
    scores = [
        projected[:, f].sum(axis=1)
        / np.maximum(energy[:, f].sum(axis=1) * np.vdot(code, code).real, 1e-15)
        for f in (g.EVEN, g.ODD)
    ]
    joint = np.minimum(*scores)
    i = int(np.argmax(joint))
    off = 0.0
    if 0 < i < len(joint) - 1:
        curvature = joint[i - 1] - 2 * joint[i] + joint[i + 1]
        if curvature < 0:
            off = float(np.clip(0.5 * (joint[i - 1] - joint[i + 1]) / curvature, -0.5, 0.5))
    return dict(
        epoch=float((epochs[i] + off) % g.PERIOD),
        hz=float(adjusted[i]),
        sample=int(epochs[i]),
        score=float(joint[i]),
    )


def residual_spectrum(samples, code, p, start_symbol):
    starts = STARTS + p["sample"] + start_symbol * g.SYMBOL
    starts = starts[starts + len(code) <= len(samples)]
    ref = code.conj() * np.exp((-2j * np.pi * p["hz"] / g.RATE) * NATIVE_OFFSETS).astype(
        np.complex64
    )
    symbols = (
        (samples[starts[:, None] + NATIVE_OFFSETS] * ref).reshape(len(starts), 64, -1).sum(axis=2)
    )
    return np.abs(fft.fft(symbols, axis=1)) ** 2


def held_symbols(samples, code, p, start_symbol):
    spectrum = residual_spectrum(samples, code, p, start_symbol)
    ranks = []
    ratios = []
    for v in (spectrum[::2].sum(axis=0), spectrum[1::2].sum(axis=0), spectrum.sum(axis=0)):
        ranks.append(1 + int(np.sum(v[1:] >= v[0])))
        ratios.append(float(v[0] / max(float(np.median(v[1:])), 1e-12)))
    return ranks, ratios


def detect(samples, edge, lo, hi, *, stride=None, prefilter=None, diagnostic=False, native=None):
    if samples.shape != (200000,) or not lo < hi:
        raise ValueError("expected one 20 ms antenna and an ordered CFO range")
    if stride is None:
        stride = 4 if hi - lo <= 1600000 else 1
    if stride not in (1, 2, 4):
        raise ValueError("unsupported sample rate")
    if prefilter is None:
        prefilter = stride != 1
    center = (lo + hi) / 2
    modes, epochs = timing(samples, edge, center, stride, prefilter, native)
    seeds = carriers(modes, epochs, edge, lo, hi, center, stride, prefilter)
    _, _, code, held = templates(edge, stride, prefilter)
    refine = native.refine if native else measured_peak
    peaks = [refine(samples, code, e, f, lo, hi) for _, e, f in seeds]
    peaks.sort(key=lambda p: -p["score"])
    chosen = None
    for p in peaks:
        p["held"] = []
        for start, h in zip(HELD_START, held, strict=True):
            ranks, ratios = held_symbols(samples, h, p, start)
            p["held"].append(dict(start_symbol=start, ranks=ranks, ratios=ratios))
            if max(ranks[:2]) == 1:
                p["confirmation"] = "later_symbols"
                break
        if "confirmation" not in p:
            spectrum = residual_spectrum(samples, code, p, 0)
            pairs = spectrum[:7] + spectrum[7:]
            if np.all(pairs[:, 0] > np.max(pairs[:, 1:], axis=1)):
                p["confirmation"] = "seven_frame_pairs"
        if chosen is None and "confirmation" in p:
            chosen = p
        if chosen is not None and not diagnostic:
            break
    if diagnostic:
        return chosen, dict(epochs=[e * stride for e in epochs], seeds=seeds, finalists=peaks)
    return chosen
