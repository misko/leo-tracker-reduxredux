import unittest
import numpy as np
from compare_decoders import coherence_filter


class ComparisonTests(unittest.TestCase):
    def test_no_cross_receiver_support_pooling(self):
        pairs=[(r,0) for r in range(12)]
        kept,_=coherence_filter(pairs,np.arange(12),np.r_[np.zeros(6),np.ones(6)],np.ones(12))
        self.assertEqual(kept,[])

    def test_ten_coherent_groups_kept(self):
        pairs=[(r,0) for r in range(10)]
        kept,segments=coherence_filter(pairs,np.arange(10),np.zeros(10),np.ones(10))
        self.assertEqual(kept,pairs);self.assertEqual(len(segments),1)


if __name__=='__main__':unittest.main()
