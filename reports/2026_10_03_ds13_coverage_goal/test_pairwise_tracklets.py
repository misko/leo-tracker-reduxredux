import unittest
import numpy as np
from pairwise_tracklets import best_pair,validate


def mode(number,proposal,rows,gain):
    rows=np.array(rows)
    return dict(number=number,proposal=proposal,penalty=1.,segments=[(0,rows,np.zeros(len(rows)),np.full(len(rows),gain))])


class PairwiseTests(unittest.TestCase):
    def test_joint_mode_change_and_exclusivity(self):
        groups=np.arange(20);times=np.arange(20,dtype=float)
        left=[mode(1,0,range(20),1.),mode(1,1,range(10),2.)]
        right=[mode(2,2,range(10,20),2.)]
        result,score=best_pair(left,right,np.zeros(20,bool),groups,times)
        self.assertEqual({r['proposal'] for r in result},{1,2})
        self.assertEqual(score,24.)
        self.assertEqual(len(validate({r['catalog_number']:r for r in result},groups,times)),20)

    def test_other_ownership_cannot_be_stolen(self):
        occupied=np.ones(20,bool)
        result,score=best_pair([mode(1,0,range(20),3.)],[],occupied,np.arange(20),np.arange(20))
        self.assertEqual(result,[]);self.assertEqual(score,0.)
