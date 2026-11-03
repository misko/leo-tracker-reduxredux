import unittest
from audit_alternative_tracks import split_support


class SupportTests(unittest.TestCase):
    def test_multiple_peaks_do_not_add_probe_support(self):
        result=split_support([0]*20+[6],[1]*20+[2])
        self.assertEqual(len(result),2)
        self.assertFalse(any(r['meets_support_gate'] for r in result))

    def test_long_support(self):
        result=split_support(list(range(12)),list(range(12)))
        self.assertEqual(result[0]['distinct_groups'],12)
        self.assertTrue(result[0]['meets_support_gate'])

    def test_bad_shape(self):
        with self.assertRaises(ValueError):split_support([0,1],[0])
