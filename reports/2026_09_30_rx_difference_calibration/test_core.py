import copy
import unittest
import numpy as np
from core import pair,density


def cases():
    t=np.arange(24.)
    a=dict(session_id='s',rf_hz=1.,number=2,receiver_id=0,times=t.tolist(),mask=(t%3!=2).tolist(),residual=(t*.2+np.sin(t)).tolist())
    b=dict(a,receiver_id=1,residual=(t*.2-np.sin(t)).tolist())
    return a,b


class TestPair(unittest.TestCase):
    def test_shared_signal_cancels(self):
        a,b=cases();original=pair(a,b)
        ramp=np.arange(24.)*100
        a['residual']=(np.array(a['residual'])+ramp).tolist()
        b['residual']=(np.array(b['residual'])+ramp).tolist()
        got=pair(a,b)
        np.testing.assert_allclose(got['held'],original['held'],atol=1e-12)
        self.assertAlmostEqual(got['feature'],original['feature'])

    def test_held_values_do_not_change_training_feature(self):
        a,b=cases();original=pair(a,b)
        changed=copy.deepcopy(a)
        changed['residual'][2::3]=[1e8]*8
        got=pair(changed,b)
        self.assertEqual(got['center'],original['center'])
        self.assertEqual(got['feature'],original['feature'])
        b['rf_hz']=2.
        self.assertIsNone(pair(a,b))

    def test_likelihood_gradient(self):
        p=np.array([2.,.3]);errors=np.array([-100.,-3.,0.,20.]);features=np.array([1.,3.,10.,50.])
        _,g=density(p,errors,features)
        for i in range(2):
            d=np.zeros(2);d[i]=1e-6
            fd=(density(p+d,errors,features)[0]-density(p-d,errors,features)[0])/2e-6
            np.testing.assert_allclose(fd,g[:,i],atol=1e-8)


if __name__=='__main__':
    unittest.main()
