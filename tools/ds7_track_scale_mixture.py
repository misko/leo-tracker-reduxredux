"""Whole-track noise-scale mixture over frozen Doppler candidate banks.

Retains the baseline's penalized, profiled stationary offsets. Scale and
candidate weights are normalized discretely; this is not an integrated
Bayesian evidence calculation over offsets or a satellite identity test.
"""

from __future__ import annotations

import math

import ds7_fast_baseline_adapter as baseline
import numpy as np
from scipy.special import gammaln, logsumexp


def densities(residual, scale):
    return (
        gammaln(2.5)
        - gammaln(2)
        - 0.5 * math.log(4 * math.pi)
        - math.log(scale)
        - 2.5 * np.log1p((residual / scale) ** 2 / 4)
    )


def evaluate(
    tracks, prediction, x, *, gradient=False, held=False, scales=(100.0, 1000.0), priors=(0.9, 0.1)
):
    scales, priors = np.asarray(scales, dtype=float), np.asarray(priors, dtype=float)
    if (
        scales.ndim != 1
        or scales.shape != priors.shape
        or not len(scales)
        or not np.isfinite(scales).all()
        or not np.isfinite(priors).all()
        or np.any(scales <= 0)
        or np.any(priors <= 0)
        or not np.isclose(priors.sum(), 1, rtol=0, atol=1e-12)
    ):
        raise ValueError("positive finite scales and normalized positive priors required")
    total, held_total, derivative, receipts = 0.0, 0.0, np.zeros(3), []
    for track in tracks:
        predicted, visible = prediction(track, x)
        mask = track["mask"]
        residual = track["y"][None, :] - predicted
        scores, offsets, influences, held_densities = [], [], [], []
        for scale, prior in zip(scales, priors, strict=True):
            offset, audits = baseline.fit_stationary_offsets(residual[:, mask], sigma=scale)
            if not all(a["converged"] for a in audits):
                raise RuntimeError("offset stationarity check failed")
            centered = residual - offset[:, None]
            density = densities(centered, scale)
            score = density[:, mask].sum(axis=1) - 0.5 * offset**2 / 1e12 + math.log(prior)
            scores.append(np.where(visible, score, -np.inf))
            offsets.append(offset)
            influences.append(5 * centered[:, mask] / (4 * scale**2 + centered[:, mask] ** 2))
            held_densities.append(density[:, ~mask].sum(axis=1))
        scores = np.asarray(scores)
        normal = float(logsumexp(scores))
        if not math.isfinite(normal):
            raise ValueError("no visible nominee")
        weights = np.exp(scores - normal)
        total += normal - math.log(track["catalogue_size"])
        if gradient:
            influence = np.sum(weights[:, :, None] * np.asarray(influences), axis=0)
            for axis in range(3):
                step = 1e-4 if axis < 2 else 1e-5
                plus, minus = x.copy(), x.copy()
                plus[axis] += step
                minus[axis] -= step
                if axis == 2:
                    plus[axis], minus[axis] = min(5.0, plus[axis]), max(-5.0, minus[axis])
                delta = (prediction(track, plus)[0] - prediction(track, minus)[0]) / (
                    plus[axis] - minus[axis]
                )
                derivative[axis] += float(np.sum(influence * delta[:, mask]))
        if held:
            held_score = float(logsumexp(scores + np.asarray(held_densities)) - normal)
            held_total += held_score
            receipts.append(
                {
                    "track_id": track["track_id"],
                    "held_log_score": held_score,
                    "scale_weights": weights.sum(axis=1).tolist(),
                    "candidate_weights": weights.sum(axis=0).tolist(),
                    "joint_weights": weights.tolist(),
                    "offsets": np.asarray(offsets).tolist(),
                    "training_observations": int(mask.sum()),
                    "held_observations": int((~mask).sum()),
                }
            )
    return {
        "training_log_score": total,
        "gradient": derivative.tolist(),
        "held_log_score": held_total if held else None,
        "tracks": receipts,
    }
