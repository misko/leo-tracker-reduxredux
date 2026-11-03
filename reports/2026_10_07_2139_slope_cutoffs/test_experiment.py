"""Focused scientific checks for pair residual and fixed trial definitions."""
import unittest
from types import SimpleNamespace
import numpy as np
import experiment as e


class Checks(unittest.TestCase):
    def test_pair_residual_recovers_differential_slope_and_c_cancels(self):
        times=np.repeat(np.arange(10,dtype=float),2)
        rx=np.tile([0,1],10);channels=np.ones(20,dtype=int)
        design=np.column_stack([rx==0,(rx==0)*times,rx==1,(rx==1)*times,np.repeat(np.arange(10),2)])
        v=np.zeros(9);v[2:7]=[15,2,75,5,80]
        common_signal=np.repeat(30*np.sin(np.arange(10)),2)
        obs=SimpleNamespace(measured_hz=design@v[2:7]+common_signal,times_s=times,channel=channels)
        obj=SimpleNamespace(observations=obs,baseline=np.zeros(20),design=design)
        pairs=np.arange(20).reshape(-1,2)
        exact=e.pair_metrics(obj,v,pairs)
        self.assertLess(exact['median_absolute_residual_hz'],1e-8)
        bad=v.copy();bad[5]=1;bad[6]=999
        metric=e.pair_metrics(obj,bad,pairs)
        self.assertAlmostEqual(metric['robust_residual_slope_hz_s'],4,places=7)
        self.assertAlmostEqual(metric['median_absolute_residual_hz'],18,places=7)

    def test_projection_changes_only_slopes_and_never_input(self):
        v=np.array([0,0,12,-129,35,119,700,0,0.],float);old=v.copy()
        p=e.project(v,30,250,[0,0])
        expected=old.copy();expected[[3,5]]=[-30,30]
        np.testing.assert_array_equal(p,expected);np.testing.assert_array_equal(v,old)

    def test_selection_uses_score_not_pair_residual_or_truth(self):
        a=dict(arm='zero-c',feasible=True,basin='a',origin='x',selection_score=10,horizontal_error_m=1,pair_clock=0)
        b=dict(a,selection_score=9,horizontal_error_m=5000,pair_clock=1000)
        self.assertIs(e.choose([a,b],'zero-c'),b)


if __name__=='__main__':unittest.main(verbosity=2)
