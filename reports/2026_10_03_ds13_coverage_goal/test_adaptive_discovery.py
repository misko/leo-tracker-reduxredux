import unittest
import numpy as np
from adaptive_discovery import root_offsets,timing_modes,coherent_segments


class DiscoveryTests(unittest.TestCase):
    def test_root_recovers_between_grid_samples(self):
        root,ok=root_offsets(3.,np.array([2350.]),np.array([5000.]),np.array([True]))
        self.assertTrue(ok[0]);self.assertAlmostEqual(root[0],3.47)

    def test_duplicate_votes_do_not_manufacture_support(self):
        self.assertEqual(timing_modes(np.zeros(100),np.zeros(100)),[])
        self.assertTrue(timing_modes(np.zeros(10),np.arange(10)))

    def test_coherence_requires_ten_groups(self):
        rows=np.arange(20);t=rows*.5;g=rows//3;rx=np.zeros(20,int);ch=np.ones(20,int);r=np.zeros(20)
        self.assertEqual(coherent_segments(rows,t,g,rx,ch,r),[])
        self.assertEqual(len(coherent_segments(rows,t,rows,rx,ch,r)),1)

    def test_gaps_split_tracks(self):
        rows=np.arange(12);t=np.r_[np.arange(6),20+np.arange(6)]
        self.assertEqual(coherent_segments(rows,t,rows,np.zeros(12,int),np.ones(12,int),np.zeros(12)),[])


if __name__=='__main__':unittest.main()
