"""Requires NumPy (deployed analysis environment); no RF/database access."""
import importlib.util
import math
from pathlib import Path
import unittest
import numpy as np
from conservative import blend, lse

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('grouped_robust_core',HERE.parent/'2026_09_27_roof_location_geometry/robust_core.py')
robust=importlib.util.module_from_spec(spec);spec.loader.exec_module(robust)


class Tests(unittest.TestCase):
    def test_shortlist_and_cfo_ignore_held_values(self):
        t=np.arange(8.)
        pred=np.array([t,2*t,t*t,-t])
        measured=t+100.;mask=np.array([1,1,1,1,0,0,0,0],bool)
        def fit(y):return robust.train_shortlist(pred,y,mask,np.ones(4,bool),scale_hz=1.,df=2.)
        a=fit(measured);changed=measured.copy();changed[~mask]+=1e7
        self.assertEqual(a,fit(changed))
        self.assertEqual(a['training_observations'],4)

    def test_regularized_rx_uses_training_likelihood_once(self):
        p=np.log([.8,.2]);rx=np.log([.25,.75]);held=np.log([.1,.9])
        q=p+rx;q-=lse(q)
        uniform=[-math.log(2)]*2
        a=blend(p.tolist(),uniform,.5);b=blend(q.tolist(),uniform,.5)
        self.assertAlmostEqual(math.exp(lse([v+f for v,f in zip(a,held)])),.38)
        # RX posterior = (4/7, 3/7); uniform blend = (15/28,13/28).
        expected=(15*.1+13*.9)/28
        self.assertAlmostEqual(math.exp(lse([v+f for v,f in zip(b,held)])),expected)


if __name__=='__main__':unittest.main()
