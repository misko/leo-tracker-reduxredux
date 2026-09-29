"""Independent tests of cone/trend probability routing and geographic derivatives."""

import copy
import math
import unittest

import numpy as np
from cone_trend import ConeTrendPosition, routed_log_prior
from ds7_baseline_adapter import Stationary
from scipy.integrate import quad
from test_contrast_position import fixture
from test_trend_mixture import PolynomialPrediction, toy
from trend_mixture import TrendMixturePosition


class ConstantCone(ConeTrendPosition):
    compatibility = 0.05

    def log_geometry(self, track, local):
        count = self.models[0].prediction(track, local)[0].shape[0]
        value = math.log(self.compatibility) if self.compatibility else -np.inf
        return np.full(count, value)


class Tests(unittest.TestCase):
    def test_prior_mass_and_invisible_candidates(self):
        for q in (0, 0.2, 1):
            for g in (np.ones(3), np.zeros(3), np.array([0.2, 0.8, 0.5])):
                with np.errstate(divide="ignore"):
                    prior = np.exp(routed_log_prior(np.log(g), [True, True, False], q))
                expected = [
                    (1 - q) * g[0] / 2,
                    (1 - q) * g[1] / 2,
                    0,
                    q + (1 - q) * (1 - (g[0] + g[1]) / 2),
                ]
                np.testing.assert_allclose(prior, expected, atol=1e-15)
                self.assertAlmostEqual(prior.sum(), 1, places=14)
        with self.assertRaisesRegex(ValueError, "outside conditional-bank domain"):
            routed_log_prior(np.zeros(2), [False, False], 0.2)

    def test_no_cone_replays_prior_mixture(self):
        docs, config = fixture()
        x = [0.3, -0.4, 0.17, 0.27]
        for q in (0, 0.2, 1):
            old = TrendMixturePosition(docs, config, Stationary, q).evaluate(x, held=True)
            new = ConeTrendPosition(docs, config, Stationary, background_probability=q).evaluate(
                x, held=True
            )
            self.assertAlmostEqual(old["score"], new["score"], places=10)
            np.testing.assert_allclose(old["gradient"], new["gradient"], atol=1e-10, rtol=1e-10)
            for a, b in zip(old["rows"], new["rows"], strict=True):
                self.assertAlmostEqual(a["held_log_score"], b["held_log_score"], places=10)
                self.assertAlmostEqual(
                    a["signal_responsibility"], b["signal_responsibility"], places=12
                )

    def test_zero_cone_has_only_background_and_zero_force(self):
        docs, config = fixture()
        model = ConstantCone(docs, config, Stationary)
        model.compatibility = 0
        a = model.evaluate([0.3, -0.4, 0.17, 0.27], held=True)
        b = model.evaluate([3, -3, 1.1, -1.1], held=True)
        self.assertEqual(a["score"], b["score"])
        np.testing.assert_array_equal(a["gradient"], np.zeros(4))
        self.assertTrue(all(r["background_prior_mass"] == 1 for r in a["rows"]))
        self.assertTrue(all(r["signal_responsibility"] == 0 for r in a["rows"]))
        self.assertEqual(
            [r["held_log_score"] for r in a["rows"]], [r["held_log_score"] for r in b["rows"]]
        )

    def test_common_factor_attenuates_instead_of_cancelling(self):
        docs, config = fixture()
        docs = [docs[0]]
        docs[0]["tracks"] = docs[0]["tracks"][:1]
        x = [0.3, -0.4, 0.17]
        model = ConstantCone(docs, config, Stationary)
        old = TrendMixturePosition(docs, config, Stationary, 0.2).evaluate(x, held=True)
        new = model.evaluate(x, held=True)
        effective_q = 1 - 0.8 * model.compatibility
        equivalent = TrendMixturePosition(docs, config, Stationary, effective_q).evaluate(
            x, held=True
        )
        self.assertAlmostEqual(new["score"], equivalent["score"], places=10)
        np.testing.assert_allclose(new["gradient"], equivalent["gradient"], atol=1e-10)
        a, b = old["rows"][0]["signal_responsibility"], new["rows"][0]["signal_responsibility"]
        self.assertLess(b, a)
        self.assertGreater(np.linalg.norm(old["gradient"]), 1e-6)
        np.testing.assert_allclose(new["gradient"], old["gradient"] * (b / a), atol=1e-10)

    def test_held_prediction_integrates_to_one(self):
        docs = toy()
        config = {"timing_grid_s": [-5, 0, 5]}

        def density(y):
            docs[0]["tracks"][0]["y"][-1] = y
            model = ConstantCone(docs, config, PolynomialPrediction)
            row = model.evaluate([4, 280, 0], False, True)["rows"][0]
            return math.exp(row["held_log_score"])

        value, error = quad(density, -np.inf, np.inf, epsabs=1e-9, epsrel=1e-9)
        self.assertAlmostEqual(value, 1, places=7)
        self.assertLess(error, 1e-7)

    def test_all_widths_and_position_timing_derivatives(self):
        docs, config = fixture()
        x = np.array([0.3, -0.4, 0.17, 0.27])
        for width in (20, 30, 40, 50):
            model = ConeTrendPosition(docs, config, Stationary, width)
            result = model.evaluate(x)
            for axis in range(len(x)):
                step = 0.001 if axis < 2 else 0.00005
                delta = np.eye(len(x))[axis] * step
                numeric = (
                    model.evaluate(x + delta, False)["score"]
                    - model.evaluate(x - delta, False)["score"]
                ) / (2 * step)
                self.assertLess(abs(numeric - result["gradient"][axis]), 2e-5)

    def test_background_weight_derivative_is_required(self):
        class FlatPrediction(PolynomialPrediction):
            def prediction(self, track, x):
                return np.zeros((2, len(track["y"]))), np.ones(2, dtype=bool)

        class VariableCone(ConeTrendPosition):
            def log_geometry(self, track, local):
                return np.array([-np.logaddexp(0, -local[0]), math.log(0.5)])

        model = VariableCone(toy(), {"timing_grid_s": [-5, 0, 5]}, FlatPrediction)
        x = np.array([0.3, 0, 0])
        a = model.evaluate(x)
        delta = np.array([1e-4, 0, 0])
        finite = (
            model.evaluate(x + delta, False)["score"] - model.evaluate(x - delta, False)["score"]
        ) / 2e-4
        self.assertLess(finite, -0.01)
        self.assertAlmostEqual(finite, a["gradient"][0], places=7)
        # Frequency is position-independent. Satellite-weight-only derivatives
        # are positive here; the correct negative sign requires background mass.

    def test_held_values_and_geometry_do_not_change_training(self):
        docs, config = fixture()
        changed = copy.deepcopy(docs)
        for doc in changed:
            for track in doc["tracks"]:
                track["y"][~track["mask"]] += 10000
                track["candidate_position_km"][:, :, ~track["mask"], 1] += 1000
        x = [0.3, -0.4, 0.17, 0.27]
        for width in (20, 30, 40, 50):
            a = ConeTrendPosition(docs, config, Stationary, width).evaluate(x, held=True)
            b = ConeTrendPosition(changed, config, Stationary, width).evaluate(x, held=True)
            self.assertEqual(a["score"], b["score"])
            np.testing.assert_array_equal(a["gradient"], b["gradient"])
            for r, s in zip(a["rows"], b["rows"], strict=True):
                self.assertEqual(r["candidate_responsibilities"], s["candidate_responsibilities"])
                self.assertNotEqual(r["held_log_score"], s["held_log_score"])

    def test_receiver_swap_and_copointed_symmetry(self):
        docs, config = fixture()
        changed = copy.deepcopy(docs)
        for doc in changed:
            for track in doc["tracks"]:
                track["receiver_id"] = 1 - track["receiver_id"]
        x = [0.3, -0.4, 0.17, 0.27]
        for width in (20, 30, 40, 50):
            for left, right in (("nominal", "swapped"), ("copointed", "copointed")):
                a = ConeTrendPosition(docs, config, Stationary, width, left).evaluate(x, held=True)
                b = ConeTrendPosition(changed, config, Stationary, width, right).evaluate(
                    x, held=True
                )
                self.assertEqual(a["score"], b["score"])
                np.testing.assert_array_equal(a["gradient"], b["gradient"])
                self.assertEqual(a["rows"], b["rows"])


if __name__ == "__main__":
    unittest.main()
