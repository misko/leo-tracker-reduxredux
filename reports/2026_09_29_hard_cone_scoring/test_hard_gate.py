"""Verify the exact gate and normalized predictive distribution before data use."""
# ruff: noqa: I001 -- hard_gate must bootstrap the published research dependencies first.

import copy
import math
import unittest

import numpy as np
from hard_gate import HardConeScore
from cones import enu_los
from ds7_baseline_adapter import Stationary, site
from scipy.integrate import quad
from test_contrast_position import fixture
from test_trend_mixture import PolynomialPrediction, toy
from trend_mixture import TrendMixturePosition


class TwoPredictions(PolynomialPrediction):
    def prediction(self, track, local):
        values, _ = super().prediction(track, local)
        second = values[0] + 20 * np.asarray(track["times_s"]) ** 2
        return np.vstack([values[0], second]), np.ones(2, dtype=bool)


class FixedAngles(HardConeScore):
    angle_values = np.array([[10.0, 40.0, 10.0, 10.0, 70.0], [20.0, 20.0, 20.0, 20.0, 0.0]])

    def angles(self, track, local):
        return self.angle_values.copy()


class Tests(unittest.TestCase):
    config = {"timing_grid_s": [-5, 0, 5]}
    x = [4, 280, 0]

    def model(self, docs=None, q=0.2):
        return FixedAngles(
            toy() if docs is None else docs,
            self.config,
            TwoPredictions,
            half_angle_deg=40,
            background_probability=q,
        )

    def test_boundary_is_inclusive_and_whole_track_is_required(self):
        model = self.model()
        track = model.documents[0]["tracks"][0]
        np.testing.assert_array_equal(model.log_geometry(track, self.x), [0.0, 0.0])
        model.angle_values = model.angle_values.copy()
        model.angle_values[0, 1] += 1e-6
        np.testing.assert_array_equal(model.log_geometry(track, self.x), [-np.inf, 0.0])
        row = model.evaluate(self.x, held=True)["rows"][0]
        self.assertEqual(row["candidate_responsibilities"][0], 0)
        self.assertAlmostEqual(row["background_prior_mass"], 0.6)
        self.assertAlmostEqual(
            sum(row["candidate_responsibilities"]) + row["background_responsibility"], 1
        )

    def test_all_inside_matches_no_cone_for_q_endpoints(self):
        for q in (0, 0.2, 1):
            old = TrendMixturePosition(toy(), self.config, TwoPredictions, q).evaluate(
                self.x, False, True
            )
            new = self.model(q=q).evaluate(self.x, held=True)
            self.assertAlmostEqual(old["score"], new["score"], places=10)
            a, b = old["rows"][0], new["rows"][0]
            self.assertAlmostEqual(a["held_log_score"], b["held_log_score"], places=10)
            np.testing.assert_allclose(
                b["candidate_responsibilities"],
                np.array(a["weights_given_signal"]) * a["signal_responsibility"],
                atol=1e-12,
            )

    def test_all_outside_is_pure_background_and_position_independent(self):
        model = self.model()
        model.angle_values = np.full((2, 5), 90.0)
        a = model.evaluate(self.x, held=True)
        b = model.evaluate([-10, 500, 3], held=True)
        self.assertEqual(a["score"], b["score"])
        self.assertEqual(a["rows"], b["rows"])
        self.assertEqual(a["rows"][0]["signal_responsibility"], 0)
        self.assertEqual(a["rows"][0]["background_prior_mass"], 1)

    def test_held_geometry_cannot_change_training_gate_or_frequency_score(self):
        model = self.model()
        a = model.evaluate(self.x, held=True)
        model.angle_values = model.angle_values.copy()
        model.angle_values[:, -1] = [0, 179]
        b = model.evaluate(self.x, held=True)
        self.assertEqual(a["score"], b["score"])
        self.assertEqual(a["rows"], b["rows"])

    def test_held_frequency_changes_only_held_score(self):
        docs = toy()
        changed = copy.deepcopy(docs)
        changed[0]["tracks"][0]["y"][-1] += 1000
        a, b = [self.model(d).evaluate(self.x, held=True) for d in (docs, changed)]
        self.assertEqual(a["score"], b["score"])
        self.assertEqual(
            a["rows"][0]["candidate_responsibilities"], b["rows"][0]["candidate_responsibilities"]
        )
        self.assertNotEqual(a["rows"][0]["held_log_score"], b["rows"][0]["held_log_score"])

    def test_conditional_held_density_integrates_to_one(self):
        docs = toy()

        def density(y):
            docs[0]["tracks"][0]["y"][-1] = y
            model = self.model(docs)
            model.angle_values = np.array(
                [[10.0, 10.0, 10.0, 10.0, 90.0], [80.0, 80.0, 80.0, 80.0, 0.0]]
            )
            return math.exp(model.evaluate(self.x, held=True)["rows"][0]["held_log_score"])

        value, error = quad(density, -np.inf, np.inf, epsabs=1e-9, epsrel=1e-9)
        self.assertAlmostEqual(value, 1, places=7)
        self.assertLess(error, 1e-7)

    def test_empty_horizon_bank_abstains(self):
        class Invisible(TwoPredictions):
            def prediction(self, track, local):
                values, _ = super().prediction(track, local)
                return values, np.zeros(len(values), dtype=bool)

        model = FixedAngles(toy(), self.config, Invisible, half_angle_deg=40)
        with self.assertRaisesRegex(ValueError, "outside conditional-bank domain"):
            model.evaluate(self.x)

    def test_gradient_interface_is_explicitly_unavailable(self):
        with self.assertRaisesRegex(ValueError, "no smooth-gradient"):
            self.model().evaluate(self.x, gradient=True)

    def test_real_geometry_matches_direct_dot_product_threshold(self):
        docs, config = fixture()
        x = [0.3, -0.4, 0.17, 0.27]
        admitted, total = 0, 0
        for width in (20, 30, 40, 50):
            model = HardConeScore(docs, config, Stationary, half_angle_deg=width)
            lat, lon = model.coordinates(x)
            receiver, _ = site(lat, lon)
            result = model.evaluate(x, held=True)
            lookup = {(r["session_id"], r["track_id"]): r for r in result["rows"]}
            for di, doc in enumerate(docs):
                local = [x[0], x[1], x[di + 2]]
                for track in doc["tracks"]:
                    los = enu_los(
                        track["candidate_position_km"],
                        config["timing_grid_s"],
                        local[2],
                        receiver,
                        lat,
                        lon,
                    )
                    dot = los @ model.boresights[int(track["receiver_id"])]
                    expected = np.all(
                        dot[:, track["mask"]] >= math.cos(math.radians(width)), axis=1
                    )
                    actual = np.isfinite(model.log_geometry(track, local))
                    np.testing.assert_array_equal(actual, expected)
                    posterior = np.array(
                        lookup[doc["session_id"], track["track_id"]]["candidate_responsibilities"]
                    )
                    self.assertTrue(np.all(posterior[~expected] == 0))
                    admitted += int(expected.sum())
                    total += len(expected)
        self.assertGreater(admitted, 0)
        self.assertLess(admitted, total)


if __name__ == "__main__":
    unittest.main()
