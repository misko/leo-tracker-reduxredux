"""Full Qin pilot timing from adjacent OFDM-symbol products at 10 MS/s."""

from functools import lru_cache

import numpy as np

from .frame_coherence import FFT, FRAME, RATE, SAMPLES, ranked_centers

LAG = 44
PAIR_COUNT = SAMPLES - LAG
FOLD_SIZE = 2 * FRAME - 1
STARTS = tuple((m % 3, round(m * RATE / 750)) for m in range(-1, 15))
PHASE_THIRDS = (0, 1, -1)


def phase_templates(edge, symbol_roll=0):
    from leo.analysis.starlink.templates import qin_edge_pilot_frame

    # 30 MS/s gives an exact grid for the 0, +1/3 and -1/3 sample residues.
    wave = qin_edge_pilot_frame(3 * RATE, edge, symbol_roll=symbol_roll)
    high_sample = 3 * np.arange(FRAME) - np.asarray(PHASE_THIRDS)[:, None]
    active = (high_sample >= 2 * 3 * LAG) & (high_sample < 302 * 3 * LAG)
    out = np.zeros(active.shape, dtype=np.complex64)
    out[active] = wave[high_sample[active]]
    return out, active


def template_products(edge, symbol_roll=0):
    waves, active = phase_templates(edge, symbol_roll)
    pairs = np.zeros_like(waves)
    valid = active[:, LAG:] & active[:, :-LAG]
    q = waves[:, LAG:] * waves[:, :-LAG].conj()
    mean = np.sum(q, axis=-1, dtype=np.complex128, keepdims=True) / valid.sum(
        axis=-1, keepdims=True
    )
    pairs[:, :-LAG] = np.where(valid, q - mean, 0)
    return pairs


def available_energy(kernels):
    epochs = np.arange(FRAME)
    prefix = np.pad(np.cumsum(abs(kernels) ** 2, axis=-1, dtype=np.float64), ((0, 0), (1, 0)))
    energy = np.zeros(FRAME)
    for residue, start in STARTS:
        finish = PAIR_COUNT - start
        lo, hi = prefix[residue, 0], prefix[residue, FRAME]
        if start < 0:
            lo = prefix[residue, np.clip(-start - epochs, 0, FRAME)]
        if finish < FOLD_SIZE:
            hi = prefix[residue, np.clip(finish - epochs, 0, FRAME)]
        energy += hi - lo
    return energy


@lru_cache(maxsize=2)
def filters(edge):
    from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL

    out = []
    for roll in (0, CONTROL_SYMBOL_ROLL):
        product = template_products(edge, roll)
        out.append((np.fft.fft(product, n=FFT, axis=-1).conj(), available_energy(product)))
    return tuple(out)


def fold_products(products):
    folded = np.zeros((products.shape[0], len(PHASE_THIRDS), FOLD_SIZE), dtype=products.dtype)
    for residue, start in STARTS:
        begin, end = max(-start, 0), min(FOLD_SIZE, PAIR_COUNT - start)
        folded[:, residue, begin:end] += products[:, start + begin : start + end]
    return folded


def surface(samples, edge):
    if samples.shape != (SAMPLES, 2, 2) or samples.dtype != np.dtype("<i2"):
        raise ValueError("Expected a dual-receiver 20 ms CI16 window at 10 MS/s")
    x = np.empty((2, SAMPLES), dtype=np.complex64)
    x.real, x.imag = samples[:, :, 0].T, samples[:, :, 1].T
    pairs = x[:, :-LAG].conj()
    pairs *= x[:, LAG:]
    pairs -= pairs.mean(axis=-1, dtype=np.complex128, keepdims=True)
    folded = np.fft.fft(fold_products(pairs), n=FFT, axis=-1)
    scores = []
    for kernel, energy in filters(edge):
        correlation = np.fft.ifft(np.einsum("lrf,rf->lf", folded, kernel), axis=-1)[:, :FRAME]
        scores.append(abs(correlation) ** 2 / energy)
    return scores[0] - scores[1]


def scout(samples, edge):
    values = surface(samples, edge)
    ranks = [ranked_centers(row) for row in values]
    return [
        (centers, [float(row[e]) for e in centers])
        for centers, row in zip(ranks, values, strict=True)
    ]
