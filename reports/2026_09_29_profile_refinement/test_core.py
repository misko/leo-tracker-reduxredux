import copy
import unittest

import numpy as np
from core import refine, starts


class Tests(unittest.TestCase):
    def test_joint_quadratic(self):
        target = np.array([1.0, -2.0, 0.123])
        h = np.array([[4.0, 0.0, 1.0], [0.0, 2.0, 0.0], [1.0, 0.0, 3.0]])

        def evaluate(x, gradient=True):
            d = x - target
            return dict(score=-float(d @ h @ d) / 2, gradient=-h @ d)

        r = refine(evaluate, [0.0, 0.0, 0.1])
        self.assertTrue(r["qualified"])
        np.testing.assert_allclose(r["x"], target, atol=1e-5)

    def test_wrong_gradient_rejected(self):
        def evaluate(x, gradient=True):
            return dict(score=-float(np.sum((x - 0.123) ** 2)), gradient=np.zeros(len(x)))

        self.assertFalse(refine(evaluate, [0.5, 0.5, 0.1])["qualified"])

    def test_node_crossing_rejected(self):
        def evaluate(x, gradient=True):
            return dict(score=-float(x @ x), gradient=-2 * x)

        self.assertFalse(refine(evaluate, [0.0, 0.0, 0.0])["qualified"])

    def test_held_isolation(self):
        rows = [
            dict(
                qualified=True,
                radius_km=r,
                score=s,
                held_delta=-s,
                position=[s, 0.0],
                selected=dict(timing=[0.1]),
                axis=0,
                sign=1,
            )
            for r in (0.25, 1.0)
            for s in (1.0, 2.0)
        ]
        expected = starts(rows)
        changed = copy.deepcopy(rows)
        for r in changed:
            r["held_delta"] *= -10000
        self.assertEqual(starts(changed), expected)
        self.assertEqual([r["score"] for r in expected], [2.0, 2.0])
        changed[1]["qualified"] = False
        self.assertEqual(starts(changed)[0]["score"], 1.0)

    def test_missing_radius(self):
        with self.assertRaises(ValueError):
            starts([])


if __name__ == "__main__":
    unittest.main()
