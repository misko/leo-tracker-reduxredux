import unittest

import numpy as np
from transfer import offset_and_predictions


class TransferTests(unittest.TestCase):
    def test_offset_and_shared_trajectory(self):
        common = np.arange(80) * 3.0
        f = np.array([common, common + 47])
        offset, mad, predictions = offset_and_predictions(f)
        self.assertEqual(offset, 47)
        self.assertEqual(mad, 0)
        np.testing.assert_array_equal(predictions["blend"], predictions["own"])
        self.assertFalse(np.array_equal(predictions["shuffled"], predictions["own"]))

    def test_held_changes_cannot_fit_offset(self):
        f = np.array([np.arange(80) * 1.0, np.arange(80) + 23.0])
        a = offset_and_predictions(f)
        f[:, 30:] += np.arange(50) * np.array([[2], [3]])
        b = offset_and_predictions(f)
        self.assertEqual(a[:2], b[:2])

    def test_offset_robust_to_training_outlier(self):
        f = np.zeros((2, 80))
        f[1] += 17
        f[1, 4] += 1000
        offset, mad, _ = offset_and_predictions(f)
        self.assertEqual(offset, 17)
        self.assertEqual(mad, 0)


if __name__ == "__main__":
    unittest.main()
