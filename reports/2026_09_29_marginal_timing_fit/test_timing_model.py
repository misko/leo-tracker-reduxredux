import unittest

import numpy as np
from run import previous
from timing_model import marginal, numerical, training_scores


def fixture():
    grid = np.linspace(-5, 5, 41)
    config = dict(geographic_prior_center_deg=[37.0, -122.0], timing_grid_s=grid.tolist())
    rec, up = numerical.site(37.0, -122.0)
    times = np.array([0.0, 1.0, 2.0, 4.0])
    pos = np.empty((1, 41, 4, 3))
    vel = np.empty_like(pos)
    for j, tau in enumerate(grid):
        pos[0, j] = rec + 700 * up + (times[:, None] + tau) * np.array([3.0, -5.0, 2.0])
        vel[0, j] = [3.0, -5.0, 2.0]
    track = dict(
        track_id="t",
        times_s=times,
        mask=np.array([True, True, True, False]),
        candidate_position_km=pos,
        candidate_velocity_km_s=vel,
        y=np.zeros(4),
    )
    doc = dict(session_id="s", tracks=[track])
    engine = previous.receiver.baseline.Stationary(doc, config)
    track["y"] = (
        engine.prediction(track, np.array([0.3, -0.2, 0.4]))[0][0]
        + 1000
        + np.array([0.0, 3.0, -2.0, 4.0])
    )
    return doc, config


class TimingFitTests(unittest.TestCase):
    def test_training_oracle_derivative_and_held_isolation(self):
        doc, config = fixture()
        factory = previous.receiver.baseline.Stationary
        model = previous.receiver.TrendMixturePosition([doc], config, factory, 0.2)
        x = np.array([0.1, -0.1])
        times = np.array([-3.0, 0.2, 4.0])
        scores, gradients = training_scores(model, x, times)
        for i, t in enumerate(times):
            expected = model.evaluate([*x, t])
            self.assertAlmostEqual(scores[i], expected["score"], places=8)
            np.testing.assert_allclose(gradients[i], expected["gradient"][:2], atol=1e-6)
        score, g = marginal(model, x, 8)
        for axis in range(2):
            p, m = x.copy(), x.copy()
            p[axis] += 0.001
            m[axis] -= 0.001
            numerical_g = (marginal(model, p, 8)[0] - marginal(model, m, 8)[0]) / 0.002
            self.assertAlmostEqual(numerical_g, g[axis], places=6)
        doc["tracks"][0]["y"][-1] += 10000
        changed = previous.receiver.TrendMixturePosition([doc], config, factory, 0.2)
        after, after_g = marginal(changed, x, 8)
        self.assertEqual(score, after)
        np.testing.assert_array_equal(g, after_g)


if __name__ == "__main__":
    unittest.main()
