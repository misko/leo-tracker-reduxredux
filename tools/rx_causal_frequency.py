"""Causal circular frequency predictor with no satellite information."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

BIRTH_WEIGHT = 0.2
OBSERVATION_SIGMA_HZ = 500.0
MAX_HISTORY_AGE_S = 10.0
VELOCITY_PRIOR_SD_HZ_S = 5_000.0
ACCELERATION_SD_HZ_S = 500.0


def _wrapped(value, period):
    return np.remainder(value + period / 2.0, period) - period / 2.0


def _wrapped_phase_density(points, mean, sigma, period):
    """Evaluate a wrapped Gaussian as density with respect to unit phase."""
    delta = _wrapped(np.asarray(points, dtype=float) - mean, period)
    ratio = sigma / period
    if ratio < 0.2:
        images = max(1, int(math.ceil(8.0 * ratio)) + 1)
        offsets = np.arange(-images, images + 1, dtype=float) * period
        values = np.exp(-0.5 * ((delta[..., None] + offsets) / sigma) ** 2).sum(axis=-1)
        return period * values / (sigma * math.sqrt(2.0 * math.pi))
    # The Fourier representation converges quickly for broad wrapped normals.
    first = math.exp(-2.0 * math.pi**2 * ratio**2)
    if first < 1e-15:
        return np.ones_like(delta)
    terms = max(1, int(math.ceil(math.sqrt(-math.log(1e-15) / (2 * math.pi**2 * ratio**2)))))
    harmonic = np.arange(1, terms + 1, dtype=float)
    coefficients = np.exp(-2.0 * math.pi**2 * ratio**2 * harmonic**2)
    angle = 2.0 * math.pi * delta[..., None] * harmonic / period
    return 1.0 + 2.0 * np.sum(coefficients * np.cos(angle), axis=-1)


class CausalFrequencyPredictor:
    """Maintain the last two nonempty candidate windows for one receiver."""

    def __init__(self, period_hz: float):
        if not math.isfinite(period_hz) or period_hz <= 0:
            raise ValueError("period_hz must be positive and finite")
        self.period_hz = float(period_hz)
        self._clock: float | None = None
        self._history: list[tuple[float, NDArray[np.float64]]] = []

    def _points(self, candidates: ArrayLike) -> NDArray[np.float64]:
        values = np.asarray(candidates, dtype=float)
        if values.ndim != 1 or not np.all(np.isfinite(values)):
            raise ValueError("candidates must be a finite one-dimensional array")
        return np.remainder(values, self.period_hz)

    def _history_candidates(self, candidates: ArrayLike) -> NDArray[np.float64]:
        values = self._points(candidates)
        return np.asarray(sorted(set(values.tolist())), dtype=float)

    def _components(self, time_s: float):
        receipt = {
            "settings": {
                "uniform_birth_weight": BIRTH_WEIGHT,
                "observation_sigma_hz": OBSERVATION_SIGMA_HZ,
                "max_history_age_s": MAX_HISTORY_AGE_S,
                "velocity_prior_sd_hz_s": VELOCITY_PRIOR_SD_HZ_S,
                "acceleration_sd_hz_s": ACCELERATION_SD_HZ_S,
            },
            "history_times_s": [time for time, _ in self._history],
            "history_candidate_counts": [len(values) for _, values in self._history],
        }
        if not self._history or time_s - self._history[-1][0] > MAX_HISTORY_AGE_S:
            receipt.update({"mode": "uniform", "components": []})
            return [], receipt
        last_time, last = self._history[-1]
        horizon = time_s - last_time
        if len(self._history) < 2 or time_s - self._history[-2][0] > MAX_HISTORY_AGE_S:
            sigma = math.hypot(OBSERVATION_SIGMA_HZ, VELOCITY_PRIOR_SD_HZ_S * horizon)
            components = [
                {"mean_hz": float(value), "sigma_hz": sigma, "weight": 1.0 / len(last)}
                for value in last
            ]
            receipt.update(
                {
                    "mode": "one_history",
                    "forecast_horizon_s": horizon,
                    "components": components,
                }
            )
            return components, receipt
        previous_time, previous = self._history[-2]
        gap = last_time - previous_time
        if gap <= 0:
            raise ValueError("nonempty history timestamps must be strictly increasing")
        means, log_weights = [], []
        for previous_value in previous:
            for last_value in last:
                velocity = float(_wrapped(last_value - previous_value, self.period_hz) / gap)
                means.append(float(np.remainder(last_value + velocity * horizon, self.period_hz)))
                log_weights.append(-0.5 * (velocity / VELOCITY_PRIOR_SD_HZ_S) ** 2)
        log_weights = np.asarray(log_weights)
        shifted_weights = np.exp(log_weights - np.max(log_weights))
        weights = shifted_weights / shifted_weights.sum()
        ratio = horizon / gap
        sigma = math.sqrt(
            OBSERVATION_SIGMA_HZ**2 * (1.0 + ratio**2 + (1.0 + ratio) ** 2)
            + (ACCELERATION_SD_HZ_S * horizon) ** 2
        )
        components = [
            {"mean_hz": mean, "sigma_hz": sigma, "weight": float(weight)}
            for mean, weight in zip(means, weights, strict=True)
        ]
        receipt.update(
            {
                "mode": "two_history",
                "forecast_horizon_s": horizon,
                "history_gap_s": gap,
                "components": components,
            }
        )
        return components, receipt

    def density_at(self, time_s: float, candidates: ArrayLike):
        """Return phase densities and a receipt without updating history."""
        if not math.isfinite(time_s):
            raise ValueError("time_s must be finite")
        if self._clock is not None and time_s <= self._clock:
            raise ValueError("times must be strictly increasing")
        points = self._points(candidates)
        components, receipt = self._components(float(time_s))
        density = np.ones(len(points)) * BIRTH_WEIGHT
        if components:
            signal = np.zeros(len(points))
            for component in components:
                signal += component["weight"] * _wrapped_phase_density(
                    points,
                    component["mean_hz"],
                    component["sigma_hz"],
                    self.period_hz,
                )
            density += (1.0 - BIRTH_WEIGHT) * signal
        else:
            density[:] = 1.0
        if not np.all(np.isfinite(density)) or np.any(density <= 0):
            raise ArithmeticError("predictive phase density must be finite and strictly positive")
        receipt["scored_time_s"] = float(time_s)
        receipt["scored_candidate_count"] = len(points)
        return density, receipt

    def score_then_update(self, time_s: float, candidates: ArrayLike):
        """Score from prior history, then consume the current candidate set."""
        points = self._points(candidates)
        values = self._history_candidates(candidates)
        density, receipt = self.density_at(time_s, points)
        self._clock = float(time_s)
        if len(values):
            self._history.append((float(time_s), values.copy()))
            self._history = self._history[-2:]
        return density, receipt
