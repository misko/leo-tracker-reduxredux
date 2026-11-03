"""Smooth frequency likelihood; confidence cutoffs are reporting-only."""

from __future__ import annotations

import numpy as np


class SoftLikelihood:
    def __init__(self, prepared, detection_probability, clutter_rate=2.0):
        self.prepared = prepared
        self.alias_hz = prepared.alias_hz
        self.detection_probability = detection_probability
        self.clutter_rate = clutter_rate
        self.last_result = None

    def evaluate(self, predicted, visible, *, sigma_hz, return_gradient=False,
                 return_precision=False):
        result = self.prepared.evaluate(
            predicted, visible, sigma_hz=sigma_hz,
            detection_probability=self.detection_probability,
            clutter_rate=self.clutter_rate, implementation="batched",
            return_gradient=return_gradient, return_precision=return_precision,
        )
        self.last_result = result
        return result


def confident_matches(measured, predicted, posterior, alias_hz, cutoff_hz,
                      minimum_probability=0.8):
    measured = np.asarray(measured, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    posterior = np.asarray(posterior, dtype=float)
    if (predicted.ndim != 2 or predicted.shape != posterior.shape
            or predicted.shape[0] != len(measured) or predicted.shape[1] < 1
            or not np.isfinite(cutoff_hz) or cutoff_hz <= 0
            or not np.isfinite(alias_hz) or alias_hz <= 0
            or not 0 < minimum_probability <= 1):
        raise ValueError("invalid match reporting inputs")
    residual = (measured[:, None] - predicted + alias_hz / 2) % alias_hz - alias_hz / 2
    best = posterior.argmax(axis=1)
    indices = np.arange(len(measured))
    probability = posterior[indices, best]
    distance = np.abs(residual[indices, best])
    accepted = (probability >= minimum_probability) & (distance <= cutoff_hz)
    return {
        "semantics": "row-level posterior winner, not an additional training gate",
        "minimum_probability": minimum_probability,
        "cutoff_hz": cutoff_hz,
        "confident_rows": int(accepted.sum()),
        "confident_rows_per_satellite": np.bincount(
            best[accepted], minlength=predicted.shape[1]),
        "median_absolute_residual_hz": (
            float(np.median(distance[accepted])) if accepted.any() else None),
    }
