import unittest

import numpy as np
from run import TrendMixturePosition, full_score, partition


class Prediction:
    def __init__(self, doc, config):
        pass

    def prediction(self, track, x):
        t = np.array(track["times_s"])
        return np.array([x[0] * t + x[1] * t * t + x[2] * t]), np.array([True])


class HoldoutTests(unittest.TestCase):
    def test_opposite_receiver_cannot_change_source_score_or_gradient(self):
        docs = [
            dict(
                session_id="s",
                tracks=[
                    dict(
                        receiver_id=i,
                        track_id=str(i),
                        times_s=[0.0, 1.0, 3.0],
                        y=np.array([100.0, 120.0, 145.0]),
                        mask=np.array([True, True, False]),
                    )
                    for i in (0, 1)
                ],
            )
        ]
        source, target = partition(docs, 0)
        self.assertEqual([t["receiver_id"] for t in source[0]["tracks"]], [0])
        self.assertEqual([t["receiver_id"] for t in target[0]["tracks"]], [1])
        model = TrendMixturePosition(source, {}, Prediction, 0.2)
        x = np.array([10.0, 0.1, 0.2])
        original = model.evaluate(x)
        target_before = full_score(TrendMixturePosition(target, {}, Prediction, 0.2), x)
        target[0]["tracks"][0]["y"][1] += 10000
        changed = TrendMixturePosition(partition(docs, 0)[0], {}, Prediction, 0.2).evaluate(x)
        self.assertEqual(original["score"], changed["score"])
        np.testing.assert_array_equal(original["gradient"], changed["gradient"])
        self.assertNotEqual(
            target_before, full_score(TrendMixturePosition(target, {}, Prediction, 0.2), x)
        )


if __name__ == "__main__":
    unittest.main()
