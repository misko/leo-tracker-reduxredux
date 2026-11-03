import unittest

from prepare import select_visits
from study import extrapolate


class TrajectoryTests(unittest.TestCase):
    def test_signed_slope_and_constant_offset(self):
        self.assertEqual(extrapolate([1, 3], [100, 80], 4), 70)
        self.assertEqual(extrapolate([1, 3], [1100, 1080], 4) - 1000, 70)

    def test_selection_uses_frozen_masks_and_spacing(self):
        t = dict(times_s=[0, 1, 2.5, 3, 4], training_mask=[True, True, True, False, False])
        self.assertEqual(select_visits(t), (0, 2, 3))
        t["measured_hz"] = [99999, -1e10, 1e10, 0, 0]
        self.assertEqual(select_visits(t), (0, 2, 3))

    def test_unsupported_not_replaced(self):
        t = dict(times_s=[0, 1, 2], training_mask=[True, True, False])
        self.assertIsNone(select_visits(t))


if __name__ == "__main__":
    unittest.main()
