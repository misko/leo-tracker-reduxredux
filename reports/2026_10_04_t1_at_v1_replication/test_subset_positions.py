import unittest
import numpy as np
from subset_positions import choose, design


class SubsetTests(unittest.TestCase):
    def setUp(self):
        self.owners = np.array([1,1,1,2,2,3])
        self.rows = np.arange(6)
        self.margins = np.array([.1,.9,.7,.2,.8,.6])
        self.times = np.array([0.,1.,2.,3.,4.,5.])
        self.rms = {1:30.,2:20.,3:10.}

    def select(self, ranking, fraction):
        return choose(self.owners,self.rows,self.margins,self.times,self.rms,ranking,fraction)

    def test_satellite_ranking_vs_window_ranking(self):
        numbers,keep = self.select('rms',.5)
        self.assertEqual(numbers,[2,3])
        self.assertEqual(self.rows[keep].tolist(),[3,4,5])
        numbers,keep = self.select('support',.5)
        self.assertEqual(numbers,[1,2])
        self.assertEqual(sum(keep),5)
        numbers,keep = self.select('glrt',.5)
        self.assertEqual(numbers,[1,2,3])
        self.assertEqual(self.rows[keep].tolist(),[1,2,4])

    def test_all_rankings_agree_at_100_percent(self):
        for ranking in ('rms','support','glrt'):
            numbers,keep = self.select(ranking,1.)
            self.assertEqual(numbers,[1,2,3])
            self.assertTrue(keep.all())

    def test_reproducible_bounded_design(self):
        points = np.asarray(design())
        np.testing.assert_array_equal(points,design())
        self.assertEqual(points.shape,(20,2))
        self.assertTrue(np.all(np.linalg.norm(points,axis=1)<=2+1e-12))

    def test_cumulative_threshold_includes_boundary_and_can_be_empty(self):
        numbers,keep=self.select('rms-cut',20)
        self.assertEqual(numbers,[2,3])
        self.assertEqual(keep.tolist(),[False,False,False,True,True,True])
        numbers,keep=self.select('rms-cut',5)
        self.assertEqual(numbers,[])
        self.assertFalse(keep.any())


if __name__ == '__main__': unittest.main()
