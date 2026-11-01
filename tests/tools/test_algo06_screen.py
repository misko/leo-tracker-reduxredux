"""Scientific guards for catalogue eligibility and grouped comparisons."""
import unittest
import numpy as np
from algo06_science.screen import top_indices,split
from algo06_science.evidence import components,marginal,age_penalty

class ScreeningTests(unittest.TestCase):
    def test_hard_age_bound_even_when_old_fit_is_better(self):
        score=np.array([20.,-100.,30.]);age=np.array([12.,60.,30.])
        self.assertEqual(top_indices(score,age,48),[0,2])
        self.assertEqual(top_indices(score,age,72),[1,0,2])

    def test_recency_can_break_close_fit_but_not_strong_evidence(self):
        age=np.array([20.,72.]);self.assertEqual(top_indices(np.array([1.,0.]),age,72,True)[0],0)
        self.assertEqual(top_indices(np.array([100.,0.]),age,72,True)[0],1)

    def test_whole_blocks_guarded_and_reproducible(self):
        t=np.arange(0.,120.,.5)
        train,held,groups=split(t,20261031)
        self.assertFalse(np.any(train&held));self.assertTrue(train.any() and held.any())
        np.testing.assert_array_equal(train,split(t,20261031)[0])
        for g in groups:self.assertFalse(train[(t>=g*12-2)&(t<(g+1)*12+2)].any())

    def test_held_values_do_not_affect_training_evidence(self):
        t=np.arange(30.);mask=t<20;f=np.tile(t*t,(31,1));y=t*t+5.
        a=components(y,f,np.ones(31,bool),t,[0],1.,mask=mask)
        y[~mask]+=1e6;b=components(y,f,np.ones(31,bool),t,[0],1.,mask=mask)
        np.testing.assert_array_equal(a['loglik'],b['loglik'])
        np.testing.assert_array_equal(a['beta'],b['beta'])

if __name__=='__main__':unittest.main()
