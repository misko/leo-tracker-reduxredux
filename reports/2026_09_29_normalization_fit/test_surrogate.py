import sys
import unittest
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from surrogate import FrozenDenominator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "2026_09_29_unassociated_trend"))
from trend_mixture import TrendMixturePosition, contrast_density  # noqa: E402


class Engine:
    def __init__(self, doc, config):
        pass

    def prediction(self, track, x):
        times = track["times_s"]
        slope = 60 * x[0] + 20 * x[1] + 5 * x[2]
        return np.array([slope * times, (slope + 80) * times]), np.array([True, True])


class SurrogateTest(unittest.TestCase):
    def test_direct_density_gradient_and_restoration(self):
        track = dict(
            track_id="test",
            mask=np.array([True, True, True, False]),
            times_s=np.arange(4.0),
            y=np.array([10.0, 100, 130, 280]),
        )
        base = TrendMixturePosition([dict(session_id="test", tracks=[track])], {}, Engine, 0.2)
        backgrounds = dict(base.background)
        model = FrozenDenominator(base, {(0, 0): 500})
        x = np.array([0.5, 0.3, 0.2])
        out = model.evaluate(x, held=True)
        prediction, _ = base.models[0].prediction(track, x)
        direct = []
        for mask, bg in zip((track["mask"], np.ones(4, bool)), backgrounds[0, 0], strict=True):
            density, _ = contrast_density((track["y"][None, :] - prediction)[:, mask])
            direct.append(
                float(
                    np.logaddexp(np.log(0.8) + logsumexp(density) - np.log(500), np.log(0.2) + bg)
                )
            )
        self.assertAlmostEqual(out["score"], direct[0], places=12)
        self.assertAlmostEqual(out["rows"][0]["training_log_score"], direct[0], places=12)
        self.assertAlmostEqual(
            out["score"] + out["rows"][0]["held_log_score"], direct[1], places=12
        )
        for axis in range(3):
            plus, minus = x.copy(), x.copy()
            plus[axis] += 1e-5
            minus[axis] -= 1e-5
            fd = (
                model.evaluate(plus, gradient=False)["score"]
                - model.evaluate(minus, gradient=False)["score"]
            ) / 2e-5
            self.assertAlmostEqual(out["gradient"][axis], fd, places=7)
        self.assertEqual(base.background, backgrounds)


if __name__ == "__main__":
    unittest.main()
