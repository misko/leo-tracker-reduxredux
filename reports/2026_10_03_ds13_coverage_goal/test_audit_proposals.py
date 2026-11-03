import unittest
from audit_proposals import maximum_group_pairs


class MatchingTests(unittest.TestCase):
    def test_alternative_peaks_do_not_count_twice(self):
        self.assertEqual(len(maximum_group_pairs({0:{10},1:{10}})),1)

    def test_multiple_satellites_per_group(self):
        self.assertEqual(set(maximum_group_pairs({0:{10,20},1:{10}})),{(0,20),(1,10)})

    def test_empty(self):
        self.assertEqual(maximum_group_pairs({}),[])


if __name__=='__main__':unittest.main()
