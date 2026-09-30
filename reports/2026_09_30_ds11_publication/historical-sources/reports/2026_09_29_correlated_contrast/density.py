"""Normalized t4 anchored contrasts with a correlated measurement scale."""

import math

import numpy as np


class ContrastDensity:
    def __init__(self, times, decay_s, noise_scale=100.0, slope_scale=0.0):
        times = np.asarray(times, dtype=float)
        if times.ndim != 1 or len(times) < 2 or not np.isfinite(times).all():
            raise ValueError("Require at least two finite times")
        if not all(np.isfinite(v) for v in (decay_s, noise_scale, slope_scale)):
            raise ValueError("Require finite scale parameters")
        if decay_s < 0 or noise_scale <= 0 or slope_scale < 0:
            raise ValueError("Invalid scale parameters")
        self.n = len(times)
        self.dimension = self.n - 1
        identity = np.eye(self.n)
        covariance = (
            identity
            if decay_s == 0
            else (0.8 * np.exp(-abs(times[:, None] - times[None, :]) / decay_s) + 0.2 * identity)
        )
        d = identity[1:] - identity[0]
        chol = np.linalg.cholesky(noise_scale**2 * (d @ covariance @ d.T))
        # Transform frequencies directly to whitened anchored differences.
        self.whiten = np.linalg.solve(chol, d)
        self.logdet = float(2 * np.log(np.diag(chol)).sum())
        drift = slope_scale * (self.whiten @ (times - times[0]))
        norm2 = float(drift @ drift)
        self.ratio = 1 + norm2
        self.direction = drift / math.sqrt(norm2) if norm2 else np.zeros(self.dimension)
        self.logdet += math.log1p(norm2)
        self.constant = (
            math.lgamma((4 + self.dimension) / 2)
            - math.lgamma(2)
            - 0.5 * (self.dimension * math.log(4 * math.pi) + self.logdet)
        )

    def __call__(self, residual):
        residual = np.asarray(residual, dtype=float)
        if residual.ndim != 2 or residual.shape[1] != self.n or not np.isfinite(residual).all():
            raise ValueError("Require finite candidate-by-observation residuals")
        z = (residual - residual[:, :1]) @ self.whiten.T
        along = z @ self.direction
        perpendicular = z - along[:, None] * self.direction
        q = np.sum(perpendicular**2, axis=1) + along**2 / self.ratio
        projected = perpendicular + (along / self.ratio)[:, None] * self.direction
        density = self.constant - (4 + self.dimension) / 2 * np.log1p(q / 4)
        influence = (projected @ self.whiten) * ((4 + self.dimension) / (4 + q))[:, None]
        return density, influence
