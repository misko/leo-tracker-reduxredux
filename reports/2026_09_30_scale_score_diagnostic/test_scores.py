import unittest
import numpy as np
from scores import predictive


class ScoreTest(unittest.TestCase):
    def test_one_held_matches_joint(self):
        y=np.array([20.,-30.,40.]);t=np.arange(3.)
        out=predictive(y,t,[True,True,False],np.array([t,-t]),np.array([True,True]),120.)
        self.assertAlmostEqual(out['joint'],out['marginal_sum'],places=11)

    def test_batch_equals_separate_held_predictions(self):
        y=np.array([20.,-30.,40.,70.,15.]);t=np.arange(5.);mask=np.array([True,False,True,False,True])
        pred=np.array([t,-t]);visible=np.array([True,False])
        out=predictive(y,t,mask,pred,visible,73.)
        for index,j in enumerate(np.flatnonzero(~mask)):
            keep=np.r_[np.flatnonzero(mask),j]
            one=predictive(y[keep],t[keep],[True,True,True,False],pred[:,keep],visible,73.)
            self.assertAlmostEqual(one['joint'],out['individual'][index],places=11)
        changed=y.copy();changed[~mask]=1e9
        self.assertEqual(predictive(changed,t,mask,pred,visible,73.)['training'],out['training'])


if __name__=='__main__':unittest.main()
