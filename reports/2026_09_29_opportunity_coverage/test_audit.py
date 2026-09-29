import unittest

from audit import union_length


class CoverageTests(unittest.TestCase):
    def test_overlaps_not_double_counted(self):
        self.assertEqual(union_length([(10, 30), (0, 20), (5, 8)]), 30)

    def test_gaps_not_observed(self):
        self.assertEqual(union_length([(0, 20), (120, 140)]), 40)
        self.assertEqual(union_length([]), 0)

    def test_invalid_interval(self):
        with self.assertRaises(ValueError):
            union_length([(3, 3)])
