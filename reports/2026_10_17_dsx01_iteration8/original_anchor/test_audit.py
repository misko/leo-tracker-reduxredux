import unittest

import numpy as np
from audit import paired


class PairTests(unittest.TestCase):
    def test_losses_identity_switches_and_intersection_rms(self):
        old = dict(associated=np.array([True, True, False]), residual_hz=np.array([20., 30., 900.]),
                   number=np.array([1, 2, 3]), row_nll=np.array([1., 2., 3.]))
        new = dict(associated=np.array([True, False, True]), residual_hz=np.array([10., 900., 40.]),
                   number=np.array([3, 2, 3]), row_nll=np.array([.5, 2.5, 2.5]))
        row = paired(np.ones(3, bool), old, new)
        self.assertEqual((row['new'], row['lost'], row['retained_identity_changes']), (1, 1, 1))
        self.assertEqual(row['intersection_original_rms_hz'], 20.)
        self.assertEqual(row['intersection_current_rms_hz'], 10.)

    def test_misaligned_states_are_not_silently_compared(self):
        state = dict(associated=np.array([True]), residual_hz=np.array([1.]),
                     number=np.array([1]), row_nll=np.array([1.]))
        with self.assertRaises(ValueError):
            paired(np.ones(2, bool), state, state)


if __name__ == '__main__':
    unittest.main()
