"""Independently reconstruct conditional held density after cone reweighting."""

import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from cone_position import ConePosition
from ds7_baseline_adapter import Stationary
from scipy.special import gammaln, logsumexp
from test_cone_position import fixture


def log_t(residual):
    dimension = residual.shape[1]
    q = np.sum(residual**2, axis=1) / 100**2
    return (
        gammaln((4 + dimension) / 2)
        - gammaln(2)
        - dimension / 2 * math.log(4 * math.pi)
        - dimension * math.log(100)
        - (4 + dimension) / 2 * np.log1p(q / 4)
    )


class PredictiveAudit(unittest.TestCase):
    def test_conditional_density_uses_training_geometry_once(self):
        docs, config = fixture()
        x = np.array([0.3, -0.4, 0.17])
        for width in (20, 30, 40, 50):
            model = ConePosition(docs, config, 0, Stationary, width)
            result = model.evaluate(x, held=True)
            for track, row in zip(docs[0]["tracks"], result["rows"], strict=True):
                prediction, visible = Stationary(docs[0], config).prediction(track, x)
                self.assertTrue(visible.all())
                offsets = np.asarray(row["offsets"])
                residual = track["y"][None, :] - prediction - offsets[:, None]
                train_density = log_t(residual[:, track["mask"]]) - offsets**2 / (2e12)
                full_density = log_t(residual) - offsets**2 / (2e12)
                gate = model.log_geometry(track, x)
                expected = logsumexp(full_density + gate) - logsumexp(train_density + gate)
                self.assertLess(abs(expected - row["held_log_score"]), 1e-8)
                expected_weights = np.exp(train_density + gate - logsumexp(train_density + gate))
                np.testing.assert_allclose(row["weights"], expected_weights, atol=1e-10, rtol=1e-10)


if __name__ == "__main__":
    unittest.main()
