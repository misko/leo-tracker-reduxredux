import copy
import unittest

import numpy as np
from study import prediction, predictor


def case(identity, rx):
    t = np.linspace(0, 30, 61)
    return dict(
        session_id="s",
        track_id=identity,
        receiver_id=rx,
        rf_hz=11.2e9,
        number=1,
        times=t.tolist(),
        mask=(np.arange(len(t)) % 3 != 2).tolist(),
        residual=(7 + 2 * t + 0.15 * t * t).tolist(),
    )


class TransferTests(unittest.TestCase):
    def test_correction_preserves_training_intercept_and_slope(self):
        target = case("t", 0)
        mask = np.asarray(target["mask"], bool)
        times = np.asarray(target["times"])[mask]
        correction = (prediction(target, 123) - prediction(target, 0))[mask]
        self.assertAlmostEqual(float(correction.sum()), 0, places=9)
        self.assertAlmostEqual(float((times - times.mean()) @ correction), 0, places=9)

    def test_recovers_shared_curvature_with_separate_linear_terms(self):
        target, donor = case("t", 0), case("d", 1)
        t = np.array(donor["times"])
        donor["residual"] = (80 - 4 * t + 0.15 * t * t).tolist()
        fit = predictor(target, [donor], True)
        np.testing.assert_allclose(
            prediction(target, fit["coefficient"]), target["residual"], atol=1e-9
        )

    def test_held_mutation_does_not_change_prediction(self):
        target, donor = case("t", 0), case("d", 1)
        before = predictor(target, [donor], True)
        expected = prediction(target, before["coefficient"])
        for c in (target, donor):
            for i, m in enumerate(c["mask"]):
                if not m:
                    c["residual"][i] += 1e8
        self.assertEqual(before, predictor(target, [donor], True))
        np.testing.assert_allclose(expected, prediction(target, before["coefficient"]))

    def test_candidate_receiver_and_rf_support(self):
        target, donor = case("t", 0), case("d", 1)
        self.assertIsNone(predictor(target, [donor], False))
        for key, value in [("receiver_id", 0), ("rf_hz", 10e9), ("session_id", "other")]:
            changed = copy.deepcopy(donor)
            changed[key] = value
            self.assertIsNone(predictor(target, [changed], True))


if __name__ == "__main__":
    unittest.main()
