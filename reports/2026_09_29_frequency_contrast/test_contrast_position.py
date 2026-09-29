"""Independent matrix/integration checks and synthetic geographic derivatives."""

import copy
import math
import sys
import unittest
from pathlib import Path

import numpy as np
from scipy.integrate import quad
from scipy.special import logsumexp
from scipy.stats import multivariate_t

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from contrast_position import ContrastPosition, contrast_density
from ds7_baseline_adapter import Stationary, site


def matrix_density(residual, anchor, scale):
    n = len(residual)
    indices = [i for i in range(n) if i != anchor]
    d = np.eye(n)[indices] - np.eye(n)[anchor]
    return multivariate_t.logpdf(d @ residual, shape=scale**2 * d @ d.T, df=4)


def fixture():
    grid = np.array([-5.0, 0.0, 5.0])
    times = np.arange(8.0)
    pos = np.empty((2, 3, 8, 3))
    vel = np.zeros_like(pos)
    rec, _ = site(0, 0)
    for c, east in enumerate((-200.0, 200.0)):
        for i, tau in enumerate(grid):
            pos[c, i, :, 0] = rec[0] + 600
            pos[c, i, :, 1] = east + 7.5 * (times + tau)
            pos[c, i, :, 2] = 100 + 0.5 * (times + tau)
            vel[c, i, :, 1] = 7.5
            vel[c, i, :, 2] = 0.5
    config = {"geographic_prior_center_deg": [0, 0], "timing_grid_s": grid.tolist()}
    docs = []
    for di in (0, 1):
        tracks = []
        for rx in (0, 1):
            track = {
                "track_id": str(rx),
                "receiver_id": rx,
                "candidate_position_km": pos.copy(),
                "candidate_velocity_km_s": vel.copy(),
                "mask": np.arange(8) % 3 != 1,
                "times_s": times.copy(),
                "catalogue_size": 100,
            }
            predicted, _ = Stationary({}, config).prediction(track, [0.2, -0.3, 0.1 + 0.2 * di])
            track["y"] = predicted[rx] + np.array([15, -20, 10, 30, -10, -15, 5, 20]) + 12 * di
            tracks.append(track)
        docs.append({"session_id": f"synthetic-{di}", "tracks": tracks})
    return docs, config


class DensityTests(unittest.TestCase):
    def test_matrix_density_and_every_anchor(self):
        rng = np.random.default_rng(1234)
        for n in (2, 3, 7):
            residual = rng.normal(size=(3, n)) * 4 + 7
            actual, _ = contrast_density(residual, scale=2.5)
            for k, r in enumerate(residual):
                for anchor in range(n):
                    self.assertAlmostEqual(actual[k], matrix_density(r, anchor, 2.5), places=11)

    def test_flat_offset_integration_including_normalization(self):
        for r in (np.array([1.0, -2, 3]), np.array([4.0, 2, -1, 0, 3])):
            shape = np.eye(len(r)) * 2.5**2
            integral, error = quad(
                lambda offset, r=r, shape=shape: float(
                    np.exp(multivariate_t.logpdf(r - offset, shape=shape, df=4))
                ),
                -np.inf,
                np.inf,
                epsabs=1e-12,
                epsrel=1e-10,
            )
            density, _ = contrast_density(r[None, :], scale=2.5)
            self.assertLess(error, 1e-10)
            self.assertAlmostEqual(math.log(integral), density[0], places=9)

    def test_conditional_mixture_integrates_to_one(self):
        predictions = np.array([[0.0, 1, 2], [1.0, -1, 0]])
        y = np.array([5.0, -3, 0])
        log_prior = np.log([0.4, 0.6])
        training, _ = contrast_density((y[None, :] - predictions)[:, :2], scale=2)
        normal = logsumexp(training + log_prior)

        def predictive(value):
            observed = y.copy()
            observed[2] = value
            joint, _ = contrast_density(observed[None, :] - predictions, scale=2)
            return float(np.exp(logsumexp(joint + log_prior) - normal))

        integral, error = quad(predictive, -np.inf, np.inf, epsabs=1e-10, epsrel=1e-10)
        self.assertAlmostEqual(integral, 1, places=9)
        self.assertLess(error, 1e-8)

    def test_density_prediction_derivative(self):
        r = np.array([[3.0, -2, 4, 1], [1.0, 2, -3, 5]])
        _, influence = contrast_density(r, scale=2)
        for axis in range(r.shape[1]):
            d = np.eye(r.shape[1])[axis] * 1e-5
            numeric = (contrast_density(r - d, 2)[0] - contrast_density(r + d, 2)[0]) / 2e-5
            np.testing.assert_allclose(numeric, influence[:, axis], rtol=1e-8, atol=1e-9)
        np.testing.assert_allclose(influence.sum(axis=1), 0, atol=1e-14)


class PositionTests(unittest.TestCase):
    def test_all_position_and_recording_timing_derivatives(self):
        docs, config = fixture()
        model = ContrastPosition(docs, config, Stationary)
        x = np.array([0.3, -0.4, 0.17, 0.27])
        result = model.evaluate(x)
        for axis in range(len(x)):
            step = 1e-3 if axis < 2 else 5e-5
            d = np.eye(len(x))[axis] * step
            numeric = (
                model.evaluate(x + d, False)["score"] - model.evaluate(x - d, False)["score"]
            ) / (2 * step)
            self.assertLess(abs(numeric - result["gradient"][axis]), 2e-5)

    def test_frequency_translation_invariance(self):
        docs, config = fixture()
        shifted = copy.deepcopy(docs)
        for doc in shifted:
            for track in doc["tracks"]:
                track["y"] += 1e6
        x = [0.3, -0.4, 0.17, 0.27]
        a = ContrastPosition(docs, config, Stationary).evaluate(x, held=True)
        b = ContrastPosition(shifted, config, Stationary).evaluate(x, held=True)
        self.assertAlmostEqual(a["score"], b["score"], places=7)
        np.testing.assert_allclose(a["gradient"], b["gradient"], atol=1e-7, rtol=0)
        for r0, r1 in zip(a["rows"], b["rows"], strict=True):
            self.assertAlmostEqual(r0["held_log_score"], r1["held_log_score"], places=7)
            np.testing.assert_allclose(r0["weights"], r1["weights"], atol=1e-9, rtol=0)

    def test_held_data_isolation(self):
        docs, config = fixture()
        model = ContrastPosition(docs, config, Stationary)
        x = [0.3, -0.4, 0.17, 0.27]
        before = model.evaluate(x, held=True)
        for doc in docs:
            for track in doc["tracks"]:
                track["y"][~track["mask"]] += 10000
                track["candidate_position_km"][:, :, ~track["mask"], 1] += 1000
        after = model.evaluate(x, held=True)
        self.assertEqual(before["score"], after["score"])
        np.testing.assert_array_equal(before["gradient"], after["gradient"])
        for a, b in zip(before["rows"], after["rows"], strict=True):
            self.assertEqual(a["weights"], b["weights"])
            self.assertNotEqual(a["held_log_score"], b["held_log_score"])

    def test_held_matrix_replay_for_every_training_anchor(self):
        docs, config = fixture()
        x = np.array([0.3, -0.4, 0.17, 0.27])
        result = ContrastPosition(docs, config, Stationary).evaluate(x, held=True)
        self.assertAlmostEqual(
            result["score"], sum(r["training_log_score"] for r in result["rows"]), places=10
        )
        for di, doc in enumerate(docs):
            for track in doc["tracks"]:
                row = next(
                    r
                    for r in result["rows"]
                    if r["session_id"] == doc["session_id"] and r["track_id"] == track["track_id"]
                )
                prediction, visible = Stationary({}, config).prediction(track, [*x[:2], x[di + 2]])
                residual = track["y"][None, :] - prediction
                indices = np.flatnonzero(track["mask"])
                for local_anchor, global_anchor in enumerate(indices):
                    train = np.array(
                        [matrix_density(r[indices], local_anchor, 100) for r in residual]
                    )
                    joint = np.array([matrix_density(r, global_anchor, 100) for r in residual])
                    train, joint = (
                        np.where(visible, train, -np.inf),
                        np.where(visible, joint, -np.inf),
                    )
                    self.assertAlmostEqual(
                        logsumexp(joint) - logsumexp(train), row["held_log_score"], places=9
                    )
                    np.testing.assert_allclose(
                        np.exp(train - logsumexp(train)), row["weights"], atol=1e-10
                    )


if __name__ == "__main__":
    unittest.main()
