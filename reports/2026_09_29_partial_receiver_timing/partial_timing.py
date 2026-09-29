"""Profile a common receiver difference and penalize its recording deviations."""

import numpy as np


class PartialTiming:
    def __init__(self, model, recordings, sigma_s):
        if not np.isfinite(sigma_s) or sigma_s <= 0:
            raise ValueError("Penalty scale must be finite and positive")
        self.model = model
        self.recordings = recordings
        self.sigma_s = sigma_s

    def coordinates(self, x):
        return self.model.coordinates(x)

    def evaluate(self, x, gradient=True, held=False):
        x = np.asarray(x, dtype=float)
        n = self.recordings
        if x.shape != (2 + 2 * n,):
            raise ValueError("Expected E/N and two timings per recording")
        result = self.model.evaluate(x, gradient=gradient, held=held)
        differences = x[2 + n :] - x[2 : 2 + n]
        residual = differences - differences.mean()
        penalty = float(residual @ residual / (2 * self.sigma_s**2))
        derivative = np.array(result["gradient"], copy=True)
        if gradient:
            derivative[2 : 2 + n] += residual / self.sigma_s**2
            derivative[2 + n :] -= residual / self.sigma_s**2
        return {
            **result,
            "score": result["score"] - penalty,
            "raw_training_log_score": result["score"],
            "penalty": penalty,
            "gradient": derivative,
            "common_difference_s": float(differences.mean()),
            "difference_rms_s": float(np.sqrt(np.mean(residual**2))),
        }

    def value_gradient(self, x):
        result = self.evaluate(x)
        return -result["score"], -result["gradient"]
