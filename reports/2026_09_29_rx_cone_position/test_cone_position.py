"""Synthetic-bank tests of cone gradients, neutral equivalence and held isolation."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from cone_position import ConePosition
from ds7_baseline_adapter import Stationary, site
from ds789_covariance_position import CovariancePosition


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
    tracks = []
    for rx in (0, 1):
        t = {
            "track_id": str(rx),
            "receiver_id": rx,
            "candidate_position_km": pos.copy(),
            "candidate_velocity_km_s": vel.copy(),
            "mask": np.arange(8) % 3 != 1,
            "times_s": times.copy(),
            "catalogue_size": 100,
        }
        predicted, _ = Stationary({}, config).prediction(t, [0.2, -0.3, 0.1])
        t["y"] = predicted[rx] + np.array([15, -20, 10, 30, -10, -15, 5, 20])
        tracks.append(t)
    return [{"session_id": "synthetic", "tracks": tracks}], config


class ConeTests(unittest.TestCase):
    def test_no_cone_is_exact_original_objective(self):
        docs, config = fixture()
        x = np.array([0.3, -0.4, 0.17])
        old = CovariancePosition(docs, config, 0, Stationary).evaluate(x, held=True)
        new = ConePosition(docs, config, 0, Stationary).evaluate(x, held=True)
        self.assertEqual(old["score"], new["score"])
        np.testing.assert_array_equal(old["gradient"], new["gradient"])
        self.assertEqual(old["rows"], new["rows"])

    def test_enabled_derivatives_for_every_width(self):
        docs, config = fixture()
        x = np.array([0.3, -0.4, 0.17])
        for width in (20, 30, 40, 50):
            model = ConePosition(docs, config, 0, Stationary, width)
            result = model.evaluate(x)
            for axis in range(3):
                step = 1e-3 if axis < 2 else 5e-5
                delta = np.eye(3)[axis] * step
                numerical = (
                    model.evaluate(x + delta, gradient=False)["score"]
                    - model.evaluate(x - delta, gradient=False)["score"]
                ) / (2 * step)
                self.assertLess(abs(numerical - result["gradient"][axis]), 2e-5)

    def test_held_values_and_geometry_do_not_change_training(self):
        docs, config = fixture()
        model = ConePosition(docs, config, 0, Stationary, 20)
        x = np.array([0.3, -0.4, 0.17])
        before = model.evaluate(x)
        track = docs[0]["tracks"][0]
        log_gate = model.log_geometry(track, x)
        track["y"][~track["mask"]] += 100000
        track["candidate_position_km"][:, :, ~track["mask"], 1] += 1000
        after = model.evaluate(x)
        self.assertEqual(before["score"], after["score"])
        np.testing.assert_array_equal(before["gradient"], after["gradient"])
        np.testing.assert_array_equal(log_gate, model.log_geometry(track, x))

    def test_floor_and_shared_rx_control(self):
        docs, config = fixture()
        x = np.array([0.3, -0.4, 0.17])
        normal = ConePosition(docs, config, 0, Stationary, 20)
        swapped = ConePosition(docs, config, 0, Stationary, 20, control="swapped")
        a, b = docs[0]["tracks"]
        np.testing.assert_array_equal(normal.log_geometry(a, x), swapped.log_geometry(b, x))
        for track in (a, b):
            values = normal.log_geometry(track, x)
            self.assertTrue(np.all(values >= np.log(0.01)))
            self.assertTrue(np.all(values <= 0))


if __name__ == "__main__":
    unittest.main()
