"""Frozen density-weighted likelihood with unchanged clock and timing priors."""

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_08_position_error_iter10"))
from timing_fit import JointClockObjective  # noqa: E402

from leo.analysis.hard60_score import ALIAS_HZ, predict_orbits  # noqa: E402


def density_weights(observations, groups, power):
    groups = np.asarray(groups)
    if groups.shape != observations.times_s.shape or power not in (0, 0.5, 1):
        raise ValueError("invalid fixed density groups or power")
    keys = np.column_stack(
        [
            groups,
            observations.receiver,
            observations.channel,
            np.floor(observations.times_s / 5).astype(int),
        ]
    )
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    weights = counts[inverse].astype(float) ** -power
    weights[groups == 0] = 1.0
    return weights * len(weights) / weights.sum()


class WeightedClockObjective(JointClockObjective):
    def __init__(self, base, nodes, knots, weights):
        super().__init__(base, nodes, knots, 4)
        self.weights = np.asarray(weights, float)
        if (
            self.weights.shape != base.observations.times_s.shape
            or not np.all(np.isfinite(self.weights))
            or np.any(self.weights <= 0)
        ):
            raise ValueError("one positive finite weight per observation required")

    def evaluate_joint(self, vector, clock):
        value, gradient, clock_gradient, terms = super().evaluate_joint(vector, clock)
        relative = self.basis @ vector[8:]
        _, visible, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], vector[7] + relative
        )
        q = self.score.detection_budget / len(self.bank.numbers)
        logp0 = -self.score.clutter_rate + visible.sum(axis=1) * np.log1p(-q)
        nll = -(
            logp0
            - np.log(-np.expm1(logp0))
            + np.log(self.score.clutter_rate / ALIAS_HZ / terms.clutter_probability)
        )
        delta = (self.weights - 1)[:, None] * terms.prediction_gradient
        shift = np.sum(delta * timing, axis=0)
        gradient[:2] += np.einsum("nk,nki->i", delta, spatial)
        gradient[2:7] += self.design.T @ delta.sum(axis=1)
        gradient[7] += shift.sum()
        gradient[8:] += self.basis.T @ shift
        clock_gradient += self.clock_design.T @ delta.sum(axis=1)
        change = float((self.weights - 1) @ nll)
        return value + change, gradient, clock_gradient, replace(terms, nll=terms.nll + change)
