import unittest
import numpy as np
from feasible_tracklets import select
from test_joint_tracklets import proposal


class FeasibleTests(unittest.TestCase):
    def test_exclusive_timing_and_peaks(self):
        p=[proposal(1,range(10)),proposal(1,range(10,20)),proposal(2,range(10,20))]
        result=select(p,np.r_[np.arange(10),np.arange(10)],np.r_[np.arange(10),np.arange(10)],.06)
        self.assertEqual(len(result['assignments']),20)
        self.assertEqual(len({r['row_index'] for r in result['assignments']}),20)

    def test_split_cannot_create_short_fragment(self):
        result=select([proposal(1,range(12))],np.arange(12),np.r_[np.arange(6),20+np.arange(6)],.06)
        self.assertEqual(result['assignments'],[])


if __name__=='__main__':unittest.main()
