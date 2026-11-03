import unittest
import numpy as np
from discovery import roots, timing_modes


class DiscoveryTests(unittest.TestCase):
    def test_root_sign_and_gate(self):
        root,ok=roots(1.,np.array([100.,100.,0.]),np.array([-100.,0.,10.]),np.array([True,True,False]))
        self.assertEqual(root[0],0.)
        self.assertEqual(ok.tolist(),[True,False,False])

    def test_candidate_copies_cannot_create_timing_support(self):
        self.assertEqual(timing_modes(np.zeros(100),np.zeros(100,int)),[])
        self.assertEqual(timing_modes(np.zeros(10),np.arange(10)),[0.])

    def test_distinct_timing_modes_remain(self):
        self.assertEqual(set(timing_modes(np.r_[np.zeros(10),np.ones(10)],np.tile(np.arange(10),2))),{0.,1.})

    def test_no_root_outside_search_range(self):
        _,ok=roots(20.,np.array([10.]),np.array([10.]),np.array([True]))
        self.assertFalse(ok[0])
