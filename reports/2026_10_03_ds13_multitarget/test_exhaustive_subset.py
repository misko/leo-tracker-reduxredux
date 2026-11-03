import unittest
import numpy as np
from exhaustive_subset import exclusive_pairs, group_support, OFFSETS


class SubsetTests(unittest.TestCase):
    def test_support_counts_groups_not_alias_rows(self):
        mask = np.array([[True,False], [True,True], [True,False]])
        np.testing.assert_array_equal(group_support(mask, np.array([1,1,2])), [2,1])

    def test_assignment_exclusivity_and_clutter(self):
        pairs = exclusive_pairs(np.array([[9.,8.], [7.,-1.], [-np.inf,-2.]]))
        self.assertEqual(set(pairs), {(0,1),(1,0)})

    def test_timing_grid(self):
        self.assertEqual(len(OFFSETS), 25)
        self.assertEqual((OFFSETS[0], OFFSETS[-1]), (-3.,3.))


if __name__ == '__main__':
    unittest.main()
