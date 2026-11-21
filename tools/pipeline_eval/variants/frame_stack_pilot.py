"""Blind pilot acquisition on two data-derived combinations of repeated radio frames."""

import numpy as np
from scipy import fft, signal

from leo.analysis.starlink.templates import qin_edge_pilot_frame

from . import full_epoch_glrt as g


def frame_modes(samples, edge, center):
    rate = g.RATE // 2
    half = samples
    if center:
        half = samples * np.exp((-2j * np.pi * center / g.RATE) * np.arange(len(samples)))
    half = signal.resample_poly(np.asarray(half, np.complex64), 1, 2)
    refs = signal.resample_poly(qin_edge_pilot_frame(g.RATE, edge), 1, 2)
    first = g.FIRST // 2
    code = refs[first : first + 32 * g.SYMBOL // 2]
    epochs = round(rate / 750)
    starts = np.rint(np.arange(14) * rate / 750).astype(int) + first
    data = half[starts[:, None] + np.arange(epochs + len(code) - 1)]
    data -= np.mean(data, axis=1, keepdims=True)
    data /= np.maximum(np.sqrt(np.mean(abs(data) ** 2, axis=1, keepdims=True)), 1e-10)
    covariance = data @ data.conj().T
    _, basis = np.linalg.eigh(covariance)
    return basis[:, -2:].conj().T @ data, code, epochs


def acquire(samples, edge, lo, hi):
    center = (lo + hi) / 2
    modes, code, epochs = frame_modes(samples, edge, center)
    nfft = g.NFFT // 2
    rate = g.RATE / 2
    spectrum = fft.fft(modes, n=nfft, axis=1)
    base = fft.fft(code, n=nfft)
    prefix = np.r_[0.0, np.cumsum((np.abs(modes) ** 2).sum(axis=0), dtype=float)]
    energy = np.maximum(
        (prefix[len(code) :] - prefix[: -len(code)]) * np.vdot(code, code).real, 1e-20
    )
    freqs = g.frequency_grid(lo - center, hi - center, 8 * g.RATE / g.NFFT)
    power = np.empty((len(freqs), 1, 3), np.float32)
    times = np.empty(power.shape, np.int32)
    jj = np.arange(nfft)
    n = np.arange(len(code)) / rate
    for start in range(0, len(freqs), 8):
        fs = freqs[start : start + 8]
        bins = fs * nfft / rate
        kernel = base[(jj[None, :] - np.rint(bins).astype(int)[:, None]) % nfft]
        for local in np.flatnonzero(abs(bins - np.rint(bins)) > 1e-7):
            kernel[local] = fft.fft(
                np.asarray(code * np.exp(2j * np.pi * fs[local] * n), np.complex64), n=nfft
            )
        corr = fft.ifft(spectrum[None, :, :] * kernel.conj()[:, None, :], axis=2)[:, :, :epochs]
        score = (corr.real**2 + corr.imag**2).sum(axis=1) / energy
        rows = np.arange(len(fs))
        for rank in range(3):
            pick = np.argmax(score, axis=1)
            power[start : start + len(fs), 0, rank] = score[rows, pick]
            times[start : start + len(fs), 0, rank] = 2 * pick
            score[rows[:, None], (pick[:, None] + np.arange(-3, 4)) % epochs] = -1
    scan = g.Sweep(freqs + center, times, power)
    return g.distinct(scan, 8)


def detect(samples, edge, lo, hi, verify):
    code = g.pilot(edge)
    candidates = []
    for epoch, hz in acquire(samples, edge, lo, hi):
        row = g.refine(samples, code, epoch, hz, g.EVEN, lo, hi, radius=3250, step=250, span=3)
        odd = g.powers(samples, code, np.array([row["epoch"]]), np.array([row["hz"]]), g.ODD)[0, 0]
        candidates.append((min(odd, row["score"]), row))
    for _, row in sorted(candidates, key=lambda p: p[0], reverse=True)[:4]:
        output = verify(row["epoch"], row["hz"])
        if output["gate"]:
            return output
    return None
