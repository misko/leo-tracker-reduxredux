import unittest
import numpy as np
from two_source_pilot import fit_predict


class PilotPredictionTests(unittest.TestCase):
    def test_test_samples_do_not_change_amplitudes(self):
        x=np.ones((2,10,1),complex);y=np.ones((2,10),complex)*3;train=np.arange(10)<5
        before=fit_predict(y,x,train);y[:,~train]=100
        after=fit_predict(y,x,train)
        np.testing.assert_allclose(before[2],after[2]);self.assertEqual(before[0],after[0])
        self.assertGreater(after[1],before[1])

    def test_known_two_source_recovery(self):
        t=np.arange(30);x=np.stack([np.ones(30),np.exp(2j*np.pi*t/7)],axis=-1)[None]
        beta=np.array([2+1j,1-2j]);y=x@beta
        result=fit_predict(y,x,t<15)
        np.testing.assert_allclose(result[2][0],beta,atol=1e-12)
        self.assertLess(result[1],1e-20)
