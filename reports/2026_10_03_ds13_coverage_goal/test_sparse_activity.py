import unittest
import numpy as np
from sparse_activity import decode,matching


class ActivityTests(unittest.TestCase):
    def test_many_candidates_and_simultaneous_start(self):
        gain=np.full((4,100),-np.inf);gain[[0,2],7]=20;gain[[1,3],80]=20
        result=decode(np.array([0,0,1,1]),np.array([0,0,1,1]),np.zeros(4,int),np.ones(4,int),gain,np.ones_like(gain,bool),.06)
        self.assertEqual(set(result),{(0,7),(1,80),(2,7),(3,80)})

    def test_peak_and_satellite_exclusivity(self):
        score,pairs=matching(np.array([[9.,8.],[7.,-1.]]))
        self.assertEqual(score,15.)
        self.assertEqual(set(pairs),{(0,1),(1,0)})


if __name__=='__main__':unittest.main()
