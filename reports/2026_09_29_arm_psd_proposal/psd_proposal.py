"""Cheap power-spectrum ranking of the ORIGINAL11 residual-CFO bins.

This is a standalone numerical prototype.  It deliberately consumes only raw
IQ, an exact pilot template, and a sample rate; acquisition baseline results
are not inputs to the ranking.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


ORIGINAL11_CFO_HZ = np.arange(-400_000.0, 400_000.1, 80_000.0)
DEFAULT_NFFT = 2048
DEFAULT_SEGMENTS = 8


def load_complex128(path: str | Path) -> np.ndarray:
    """Load a little-endian complex128 pilot file without copying it."""

    return np.fromfile(Path(path), dtype="<c16")


def averaged_psd(
    iq: np.ndarray,
    *,
    nfft: int = DEFAULT_NFFT,
    segments: int = DEFAULT_SEGMENTS,
) -> np.ndarray:
    """Return a unit-sum, fftshift-ordered averaged periodogram.

    Segment starts span all available IQ.  Short inputs are zero-padded, while
    inputs between one and eight FFT lengths use overlapping windows.  Removing
    each segment mean prevents a DC offset from deciding the CFO rank.
    """

    samples = np.asarray(iq, dtype=np.complex128).reshape(-1)
    if nfft <= 0 or segments <= 0:
        raise ValueError("nfft and segments must be positive")
    if samples.size == 0:
        samples = np.zeros(1, dtype=np.complex128)

    last_start = max(samples.size - nfft, 0)
    starts = np.rint(np.linspace(0, last_start, min(segments, max(last_start + 1, 1)))).astype(int)
    # Rounding can repeat starts on very short inputs; repeated identical
    # periodograms add no information, so compute each distinct start once.
    starts = np.unique(starts)
    window = np.hanning(nfft)
    power = np.zeros(nfft, dtype=np.float64)
    for start in starts:
        block = np.zeros(nfft, dtype=np.complex128)
        available = samples[start : start + nfft]
        block[: available.size] = available
        if available.size:
            block[: available.size] -= np.mean(available)
        spectrum = np.fft.fft(block * window)
        power += np.abs(spectrum) ** 2
    power = np.fft.fftshift(power / starts.size)
    total = float(np.sum(power))
    if not np.isfinite(total) or total <= np.finfo(float).tiny:
        return np.full(nfft, 1.0 / nfft)
    return power / total


def _shift_psd(psd: np.ndarray, shift_hz: float, sample_rate_hz: float) -> np.ndarray:
    """Periodically interpolate an fftshift-ordered sampled-data PSD."""

    nfft = psd.size
    spacing_hz = sample_rate_hz / nfft
    bins = np.arange(nfft, dtype=float)
    # Output at frequency f takes template power from f - shift.
    source_bins = (bins - shift_hz / spacing_hz) % nfft
    lo = np.floor(source_bins).astype(int)
    hi = (lo + 1) % nfft
    fraction = source_bins - lo
    shifted = psd[lo] * (1.0 - fraction) + psd[hi] * fraction
    return shifted


def _centered_log_psd(psd: np.ndarray) -> np.ndarray:
    floor = max(float(np.max(psd)) * 1e-9, np.finfo(float).tiny)
    logged = np.log(np.maximum(psd, floor))
    if float(np.ptp(logged)) <= 16.0 * np.finfo(float).eps * max(abs(float(logged[0])), 1.0):
        return np.zeros_like(logged)
    centered = logged - np.mean(logged)
    norm = float(np.linalg.norm(centered))
    if not np.isfinite(norm) or norm <= np.finfo(float).tiny:
        return np.zeros_like(centered)
    return centered / norm


def make_bank(
    exact_template: np.ndarray,
    sample_rate_hz: float,
    *,
    cfo_bins_hz: np.ndarray = ORIGINAL11_CFO_HZ,
    nfft: int = DEFAULT_NFFT,
    segments: int = DEFAULT_SEGMENTS,
) -> dict:
    """Precompute reusable ORIGINAL11 spectral features for one exact pilot."""

    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    bins = np.asarray(cfo_bins_hz, dtype=float).reshape(-1)
    if bins.size == 0 or not np.all(np.isfinite(bins)):
        raise ValueError("cfo_bins_hz must contain finite values")

    reference = averaged_psd(exact_template, nfft=nfft, segments=segments)
    shifted = np.asarray([_shift_psd(reference, cfo, sample_rate_hz) for cfo in bins])
    log_features = np.asarray([_centered_log_psd(item) for item in shifted])
    sqrt_features = np.sqrt(shifted)
    norms = np.linalg.norm(sqrt_features, axis=1)
    sqrt_features = np.divide(
        sqrt_features,
        norms[:, None],
        out=np.zeros_like(sqrt_features),
        where=norms[:, None] > np.finfo(float).tiny,
    )
    return {
        "cfo_bins_hz": bins,
        "log_features": log_features,
        "sqrt_features": sqrt_features,
        "nfft": int(nfft),
        "segments": int(segments),
    }


def propose(iq: np.ndarray, bank: dict) -> dict:
    """Rank a raw-IQ window against a bank, without acquisition-result inputs."""

    psd = averaged_psd(iq, nfft=bank["nfft"], segments=bank["segments"])
    log_scores = np.asarray(bank["log_features"] @ _centered_log_psd(psd), dtype=float)
    sqrt_observed = np.sqrt(psd)
    sqrt_norm = float(np.linalg.norm(sqrt_observed))
    if sqrt_norm > np.finfo(float).tiny:
        sqrt_observed /= sqrt_norm
    sqrt_scores = np.asarray(bank["sqrt_features"] @ sqrt_observed, dtype=float)
    scores = log_scores
    bins = np.asarray(bank["cfo_bins_hz"])
    # Stable sorting makes ties deterministic in the published ORIGINAL11 order.
    order = np.argsort(-scores, kind="stable")
    sqrt_order = np.argsort(-sqrt_scores, kind="stable")
    confidence = float(scores[order[0]] - scores[order[1]]) if order.size > 1 else 0.0
    sqrt_confidence = (
        float(sqrt_scores[sqrt_order[0]] - sqrt_scores[sqrt_order[1]])
        if sqrt_order.size > 1
        else 0.0
    )
    return {
        "best_bin_id": int(order[0]),
        "best_cfo_hz": float(bins[order[0]]),
        "confidence": confidence,
        "sqrt_confidence": sqrt_confidence,
        "ranking": [int(value) for value in order],
        "ranking_bin_ids": [int(value) for value in order],
        "ranking_hz": [float(value) for value in bins[order]],
        "sqrt_ranking": [int(value) for value in sqrt_order],
        "scores": {str(int(cfo)): float(score) for cfo, score in zip(bins, scores, strict=True)},
        "sqrt_cosine_scores": {
            str(int(cfo)): float(score) for cfo, score in zip(bins, sqrt_scores, strict=True)
        },
        "nfft": int(bank["nfft"]),
        "segments": int(bank["segments"]),
    }


def rank_cfo_bins(
    iq: np.ndarray,
    exact_template: np.ndarray,
    sample_rate_hz: float,
    *,
    cfo_bins_hz: np.ndarray = ORIGINAL11_CFO_HZ,
    nfft: int = DEFAULT_NFFT,
    segments: int = DEFAULT_SEGMENTS,
) -> dict:
    """Convenience wrapper around :func:`make_bank` and :func:`propose`."""

    return propose(
        iq,
        make_bank(
            exact_template,
            sample_rate_hz,
            cfo_bins_hz=cfo_bins_hz,
            nfft=nfft,
            segments=segments,
        ),
    )
