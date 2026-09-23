"""Bounded orbital-rate state interpolation for research joint estimators.

Inputs are exact propagated states at candidate-specific orbital phases but
common rate nodes. Interpolation is not an accuracy certificate: callers must
check independent exact states and replay fitted rates before reporting a fit.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ


def lagrange_weights_and_derivatives(nodes, rates):
    """Polynomial weights and analytic derivatives, including at exact nodes."""
    nodes = np.asarray(nodes, dtype=float)
    rates = np.asarray(rates, dtype=float)
    if (
        nodes.ndim != 1
        or not 2 <= len(nodes) <= 5
        or not np.all(np.isfinite(nodes))
        or np.any(np.diff(nodes) <= 0)
        or rates.ndim != 1
        or not np.all(np.isfinite(rates))
        or np.any(rates < nodes[0])
        or np.any(rates > nodes[-1])
    ):
        raise ValueError("finite ordered nodes and bounded one-dimensional rates required")
    weights = np.ones((len(nodes), len(rates)))
    derivatives = np.zeros_like(weights)
    for j in range(len(nodes)):
        others = [k for k in range(len(nodes)) if k != j]
        for k in others:
            weights[j] *= (rates - nodes[k]) / (nodes[j] - nodes[k])
        for k in others:
            term = np.full(len(rates), 1.0 / (nodes[j] - nodes[k]))
            for m in others:
                if m != k:
                    term *= (rates - nodes[m]) / (nodes[j] - nodes[m])
            derivatives[j] += term
    return weights, derivatives


@dataclass(frozen=True)
class OrbitRateStateGrid:
    """Exact input nodes: node × candidate × observation × ECEF coordinate."""

    rate_nodes_s_h: np.ndarray
    position_nodes_km: np.ndarray
    velocity_nodes_km_s: np.ndarray

    def __post_init__(self):
        nodes = np.asarray(self.rate_nodes_s_h, dtype=float)
        position = np.asarray(self.position_nodes_km, dtype=float)
        velocity = np.asarray(self.velocity_nodes_km_s, dtype=float)
        lagrange_weights_and_derivatives(nodes, nodes)
        if (
            position.ndim != 4
            or position.shape != velocity.shape
            or position.shape[0] != len(nodes)
            or position.shape[-1] != 3
            or min(position.shape[1:3]) < 1
            or not np.all(np.isfinite(position))
            or not np.all(np.isfinite(velocity))
        ):
            raise ValueError("finite matching node/candidate/observation/xyz states required")
        object.__setattr__(self, "rate_nodes_s_h", nodes)
        object.__setattr__(self, "position_nodes_km", position)
        object.__setattr__(self, "velocity_nodes_km_s", velocity)

    def evaluate(self, rates_s_h):
        """Return position, velocity and their derivatives per second/hour."""
        rates = np.asarray(rates_s_h, dtype=float)
        if rates.shape != (self.position_nodes_km.shape[1],):
            raise ValueError("one rate per candidate required")
        weights, derivatives = lagrange_weights_and_derivatives(self.rate_nodes_s_h, rates)
        return tuple(
            np.einsum("nc,nctd->ctd", factor, states, optimize=True)
            for factor, states in (
                (weights, self.position_nodes_km),
                (weights, self.velocity_nodes_km_s),
                (derivatives, self.position_nodes_km),
                (derivatives, self.velocity_nodes_km_s),
            )
        )


def doppler_and_rate_derivative(receiver_ecef_km, position, velocity, dp_dr, dv_dr):
    """ECEF Doppler and exact chain-rule derivative of interpolated states."""
    delta = np.asarray(position) - np.asarray(receiver_ecef_km)
    velocity = np.asarray(velocity)
    distance = np.linalg.norm(delta, axis=-1)
    if np.any(distance <= 0) or not np.all(np.isfinite(distance)):
        raise ValueError("finite nonzero satellite-receiver distance required")
    radial_product = np.sum(delta * velocity, axis=-1)
    scale = -REFERENCE_RF_HZ / LIGHT_KM_S
    derivative = (
        np.sum(np.asarray(dp_dr) * velocity + delta * np.asarray(dv_dr), axis=-1) / distance
        - radial_product * np.sum(delta * np.asarray(dp_dr), axis=-1) / distance**3
    )
    return scale * radial_product / distance, scale * derivative
