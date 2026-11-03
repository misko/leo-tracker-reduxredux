import unittest

import numpy as np
from run import split
from scipy.special import ndtr
from timing import log_integral, timing_nodes


class TimingTests(unittest.TestCase):
    def test_uniform_normalization_and_gaussian_integral(self):
        nodes, weights = timing_nodes(32, np.linspace(-5, 5, 41))
        self.assertAlmostEqual(log_integral(np.zeros_like(nodes), weights), 0.0, places=12)
        mean, scale = 0.137, 0.02
        scores = -0.5 * ((nodes - mean) / scale) ** 2
        expected = np.log(
            scale * np.sqrt(2 * np.pi) * (ndtr((5 - mean) / scale) - ndtr((-5 - mean) / scale)) / 10
        )
        self.assertAlmostEqual(log_integral(scores, weights), expected, places=8)
        # One common timing is integrated after the tracks' log scores are summed.
        opposite = -0.5 * ((nodes + mean) / scale) ** 2
        joint = log_integral(scores + opposite, weights)
        independent = log_integral(scores, weights) + log_integral(opposite, weights)
        self.assertLess(joint, independent - 10)

    def test_whole_scan_partition(self):
        docs = [dict(session_id=str(i), y=[i]) for i in range(8)]
        a, b = split(docs, 0)
        self.assertEqual([d["session_id"] for d in a], ["0", "1", "2", "3"])
        self.assertEqual([d["session_id"] for d in b], ["4", "5", "6", "7"])
        b[0]["y"][0] = 999
        self.assertEqual([d["y"][0] for d in a], [0, 1, 2, 3])
        self.assertEqual(split(docs, 1), (b, a))


if __name__ == "__main__":
    unittest.main()
