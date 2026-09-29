import copy
import unittest

import numpy as np
from model import build
from test_correction import Tests as CorrectionTests  # noqa: F401
from test_correction import fixture, track
from test_trend_mixture import PolynomialPrediction
from trend_mixture import TrendMixturePosition


class IntegrationTests(unittest.TestCase):
    def fixture(self):
        scan = fixture()
        tracks = []
        for p in scan["pairs"]:
            for rx in (0, 1):
                t = track(p, rx)
                t.update(
                    y=np.array(t["measured_hz"]), mask=np.array(p["training"]), catalogue_size=1
                )
                tracks.append(t)
        return [dict(session_id=scan["session_id"], tracks=tracks)], {scan["session_id"]: scan}

    def test_zero_replay_and_corrected_gradient(self):
        docs, scans = self.fixture()
        x = np.array([0.12, -100.0, 0.0])
        original = TrendMixturePosition(docs, {}, PolynomialPrediction, 0.2)
        neutral, _ = build(docs, scans, {}, PolynomialPrediction, "none")
        self.assertEqual(
            original.evaluate(x, held=True)["score"], neutral.evaluate(x, held=True)["score"]
        )
        for arm in ("symmetric", "rx0_anchor", "rx1_anchor"):
            model, _ = build(docs, scans, {}, PolynomialPrediction, arm)
            outcome = model.evaluate(x)
            for axis in (0, 1):
                delta = np.eye(3)[axis] * 1e-6
                numerical = (
                    model.evaluate(x + delta, gradient=False)["score"]
                    - model.evaluate(x - delta, gradient=False)["score"]
                ) / 2e-6
                self.assertAlmostEqual(numerical, outcome["gradient"][axis], delta=0.002)

    def test_held_cannot_change_training_objective(self):
        docs, scans = self.fixture()
        changed = copy.deepcopy(docs)
        for doc in changed:
            for t in doc["tracks"]:
                t["y"][~t["mask"]] += 1e5
        x = np.array([0.12, -100.0, 0.0])
        for arm in ("symmetric", "rx0_anchor", "rx1_anchor"):
            a, _ = build(docs, scans, {}, PolynomialPrediction, arm)
            b, _ = build(changed, scans, {}, PolynomialPrediction, arm)
            self.assertEqual(a.evaluate(x)["score"], b.evaluate(x)["score"])
            np.testing.assert_array_equal(a.evaluate(x)["gradient"], b.evaluate(x)["gradient"])


if __name__ == "__main__":
    unittest.main()
