import unittest
import numpy as np
from joint_tracklets import solve,prune_nonpositive


def proposal(number,rows,offset=0):
    return {'catalog_number':number,'offset_s':offset,'segments':[{'eligible_rows':list(rows),'eligible_residual_native_hz':[0.]*len(rows)}]}


class JointTests(unittest.TestCase):
    def test_pruning_preserves_optimum_on_fixture(self):
        p=[proposal(1,range(10)),proposal(2,range(10),offset=20)]
        kept=prune_nonpositive(p,np.arange(10),.06)
        self.assertEqual(len(kept),1)
        self.assertAlmostEqual(solve(p,np.arange(10),.06)['objective'],solve(kept,np.arange(10),.06)['objective'])

    def test_competing_modes_cannot_both_be_used(self):
        result=solve([proposal(1,range(10)),proposal(1,range(10,20))],np.arange(20),.06)
        self.assertEqual(len(result['assignments']),10)
        self.assertEqual(len({x['proposal'] for x in result['assignments']}),1)

    def test_simultaneous_satellites_and_ten_group_floor(self):
        result=solve([proposal(1,range(10)),proposal(2,range(10,20)),proposal(3,range(20,29))],np.r_[np.arange(10),np.arange(10),np.arange(9)],.06)
        self.assertEqual(len(result['assignments']),20)


if __name__=='__main__':unittest.main()
