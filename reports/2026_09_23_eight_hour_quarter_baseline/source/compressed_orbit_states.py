"""Time-compressed bounded orbital-rate states for research fits."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from leo.analysis.research.orbit_rate_states import lagrange_weights_and_derivatives


@dataclass(frozen=True)
class CompressedOrbitRateStateGrid:
    """Chebyshev coefficients: rate node × candidate × coefficient × ECEF coordinate."""

    rate_nodes_s_h: np.ndarray
    time_s: np.ndarray
    time_interval_s: np.ndarray
    position_coefficients_km: np.ndarray
    velocity_coefficients_km_s: np.ndarray
    _time_basis: np.ndarray = field(init=False, repr=False)

    def __post_init__(self):
        nodes = np.asarray(self.rate_nodes_s_h, dtype=float)
        times = np.asarray(self.time_s, dtype=float)
        interval = np.asarray(self.time_interval_s, dtype=float)
        position = np.asarray(self.position_coefficients_km, dtype=float)
        velocity = np.asarray(self.velocity_coefficients_km_s, dtype=float)
        lagrange_weights_and_derivatives(nodes, nodes)
        if (
            times.ndim != 1
            or len(times) < 1
            or not np.all(np.isfinite(times))
            or interval.shape != (2,)
            or not np.all(np.isfinite(interval))
            or interval[1] <= interval[0]
            or np.any(times < interval[0])
            or np.any(times > interval[1])
        ):
            raise ValueError("finite times inside a positive interpolation interval required")
        if (
            position.ndim != 4
            or position.shape != velocity.shape
            or position.shape[0] != len(nodes)
            or position.shape[-1] != 3
            or min(position.shape[1:3]) < 1
            or position.shape[2] > len(times)
            or not np.all(np.isfinite(position))
            or not np.all(np.isfinite(velocity))
        ):
            raise ValueError("finite matching node/candidate/coefficient/xyz arrays required")
        object.__setattr__(self, "rate_nodes_s_h", nodes)
        object.__setattr__(self, "time_s", times)
        object.__setattr__(self, "time_interval_s", interval)
        object.__setattr__(self, "position_coefficients_km", position)
        object.__setattr__(self, "velocity_coefficients_km_s", velocity)
        object.__setattr__(self, "_time_basis", self._basis(times))

    def _basis(self, times):
        times = np.asarray(times, dtype=float)
        if (
            times.ndim != 1
            or not np.all(np.isfinite(times))
            or np.any(times < self.time_interval_s[0])
            or np.any(times > self.time_interval_s[1])
        ):
            raise ValueError("time extrapolation and nonfinite times are not allowed")
        x = 2 * (times - self.time_interval_s[0]) / np.ptp(self.time_interval_s) - 1
        return np.polynomial.chebyshev.chebvander(
            x, self.position_coefficients_km.shape[2] - 1
        )

    def evaluate(self, rates_s_h):
        """Evaluate at the fixed observed times supplied at construction."""
        return self._evaluate_basis(rates_s_h, self._time_basis)

    def evaluate_at(self, rates_s_h, time_s):
        """Evaluate within the fitted time interval; extrapolation is forbidden."""
        return self._evaluate_basis(rates_s_h, self._basis(time_s))

    def _evaluate_basis(self, rates_s_h, basis):
        rates = np.asarray(rates_s_h, dtype=float)
        if rates.shape != (self.position_coefficients_km.shape[1],):
            raise ValueError("one rate per candidate required")
        weights, derivatives = lagrange_weights_and_derivatives(self.rate_nodes_s_h, rates)
        outputs = []
        for factor, coefficients in (
            (weights, self.position_coefficients_km),
            (weights, self.velocity_coefficients_km_s),
            (derivatives, self.position_coefficients_km),
            (derivatives, self.velocity_coefficients_km_s),
        ):
            candidate_coefficients = np.einsum("nc,nckd->ckd", factor, coefficients)
            outputs.append(np.einsum("tk,ckd->ctd", basis, candidate_coefficients))
        return tuple(outputs)
