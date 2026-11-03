"""CFO-invariant folded-lag timing proposal prototype.

The estimator ranks epochs relative to the supplied pilot period.  It is a
host-side discovery diagnostic, not a GLRT recovery result.  The circular
template lag assumes that the pilot wraps exactly; at most ``lag`` cells per
physical frame violate that assumption when rounded frame spacing inserts a
sample, so those boundary cells are a documented approximation.
"""

from __future__ import annotations

import numpy as np


LAGS = (1, 3, 5)
FRAMES = 16


def frame_offsets(rate_hz: float, count: int, frames: int = FRAMES) -> np.ndarray:
    """Return original physical frame starts, rounded independently."""

    return np.asarray(
        [round(frame * rate_hz / 750.0) for frame in range(frames) if round(frame * rate_hz / 750.0) < count],
        dtype=np.int64,
    )


def _fold(iq: np.ndarray, period: int, offsets: np.ndarray, lag: int = 0) -> np.ndarray:
    total = np.zeros(period, dtype=np.complex128 if lag else np.float64)
    support = np.zeros(period, dtype=np.int64)
    for start in offsets:
        valid = min(period, iq.size - int(start))
        if lag:
            valid = min(valid, iq.size - int(start) - lag)
            if valid > 0:
                x = iq[start : start + valid]
                total[:valid] += iq[start + lag : start + lag + valid] * np.conj(x)
        elif valid > 0:
            total[:valid] += np.abs(iq[start : start + valid]) ** 2
        if valid > 0:
            support[:valid] += 1
    return np.divide(total, support, out=np.zeros_like(total), where=support > 0)


def _correlate(observed: np.ndarray, reference: np.ndarray, *, magnitude: bool) -> tuple[np.ndarray, np.ndarray]:
    observed = observed - np.mean(observed)
    reference = reference - np.mean(reference)
    norm = float(np.linalg.norm(observed) * np.linalg.norm(reference))
    if not np.isfinite(norm) or norm <= np.finfo(float).tiny:
        correlation = np.zeros(observed.size, dtype=np.complex128)
    else:
        correlation = np.fft.ifft(np.fft.fft(observed) * np.conj(np.fft.fft(reference))) / norm
    score = np.abs(correlation) if magnitude else np.real(correlation)
    return np.asarray(score, dtype=float), correlation


def _percentile_rank(score: np.ndarray) -> np.ndarray:
    """Map a fixed score vector to [0,1] ranks; flat evidence maps to zero."""

    if not np.all(np.isfinite(score)) or float(np.ptp(score)) <= 16 * np.finfo(float).eps * max(float(np.max(np.abs(score))), 1.0):
        return np.zeros_like(score)
    order = np.argsort(score, kind="stable")
    ranks = np.empty(score.size, dtype=float)
    ranks[order] = np.arange(score.size, dtype=float)
    return ranks / max(score.size - 1, 1)


def propose(iq: np.ndarray, template: np.ndarray, rate_hz: float) -> dict:
    """Return three lag scores, signed power score, and their percentile sum.

    Lag correlation magnitude removes the constant CFO phase.  The returned
    complex correlations preserve that phase: at a proposed epoch,
    ``angle(correlation)/(2*pi*lag/rate_hz)`` estimates CFO modulo
    ``rate_hz/lag``.  No baseline labels, coordinates, or prior hits enter.
    """

    samples = np.asarray(iq, dtype=np.complex128).reshape(-1)
    pilot = np.asarray(template, dtype=np.complex128).reshape(-1)
    period = int(round(rate_hz / 750.0))
    if not np.isfinite(rate_hz) or rate_hz <= 0 or pilot.size != period:
        raise ValueError("template length must equal round(rate_hz / 750)")
    if samples.size == 0:
        raise ValueError("iq must not be empty")
    offsets = frame_offsets(rate_hz, samples.size)

    scores: dict[str, np.ndarray] = {}
    correlations: dict[str, np.ndarray] = {}
    components = []
    for lag in LAGS:
        folded = _fold(samples, period, offsets, lag)
        reference = np.roll(pilot, -lag) * np.conj(pilot)
        score, correlation = _correlate(folded, reference, magnitude=True)
        scores[f"lag{lag}"] = score
        correlations[f"lag{lag}"] = correlation
        components.append(_percentile_rank(score))

    folded_power = _fold(samples, period, offsets)
    reference_power = np.abs(pilot) ** 2
    power, power_correlation = _correlate(folded_power, reference_power, magnitude=False)
    scores["power"] = power
    correlations["power"] = power_correlation
    components.append(_percentile_rank(power))
    scores["combined"] = np.sum(components, axis=0)
    return {"scores": scores, "correlations": correlations}
