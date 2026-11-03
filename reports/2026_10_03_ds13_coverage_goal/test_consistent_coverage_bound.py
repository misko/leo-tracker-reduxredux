import unittest
import numpy as np
from consistent_coverage_bound import solve


def mode(number,rows):return dict(catalog_number=number,segments=[dict(eligible_rows=rows)])


class ConsistentBoundTests(unittest.TestCase):
    def test_cannot_switch_timing_between_probes(self):
        r=solve([mode(1,[0]),mode(1,[1])],np.array([0,1]),2)
        self.assertEqual(r['incumbent_count'],1);self.assertAlmostEqual(r['upper_bound'],1)

    def test_distinct_satellites_concurrent_but_peaks_exclusive(self):
        r=solve([mode(1,[0,1]),mode(2,[1])],np.array([0,0]),2)
        self.assertEqual(r['incumbent_count'],2);self.assertAlmostEqual(r['upper_bound'],2)

    def test_one_peak_per_satellite_probe(self):
        r=solve([mode(1,[0,1])],np.array([0,0]),2)
        self.assertEqual(r['incumbent_count'],1)


if __name__=='__main__':unittest.main()
