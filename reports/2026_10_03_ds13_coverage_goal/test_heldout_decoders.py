import unittest
import numpy as np
from heldout_decoders import checked_test_pairs


class HeldoutDecoderTests(unittest.TestCase):
    def test_only_heldout_rows_count(self):
        self.assertEqual(checked_test_pairs([(0,1),(1,2)],np.array([0,1]),np.array([False,True])),[(1,2)])

    def test_satellite_probe_exclusivity(self):
        with self.assertRaises(ValueError):checked_test_pairs([(0,1),(1,1)],np.array([5,5]),np.ones(2,bool))

    def test_distinct_satellites_allowed_simultaneously(self):
        self.assertEqual(len(checked_test_pairs([(0,1),(1,2)],np.array([5,5]),np.ones(2,bool))),2)


if __name__=='__main__':unittest.main()
