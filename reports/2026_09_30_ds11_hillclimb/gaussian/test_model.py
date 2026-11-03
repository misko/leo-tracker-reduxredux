import unittest
import numpy as np
from scipy.stats import norm
from model import profile,GaussianPosition


class LinearGeometry:
    def __init__(self,document,config):
        pass

    def prediction(self,track,x):
        return track['design']@x+track['base'],np.array([True,True])


class GaussianTests(unittest.TestCase):
    def test_profile_is_normalized_and_stationary(self):
        y=np.array([[10.,-70.,80.],[1e5,1e5+40,1e5-60]])
        score,influence,offset=profile(y,200.)
        np.testing.assert_allclose(influence.sum(axis=1),offset/1e12,atol=1e-14)
        expected=norm.logpdf(y-offset[:,None],scale=200.).sum(axis=1)-.5*offset**2/1e12
        np.testing.assert_allclose(score,expected,atol=1e-12)

    def test_profiled_mixture_gradient_and_held_independence(self):
        rng=np.random.default_rng(11)
        track=dict(y=rng.normal(size=12)*100,mask=np.arange(12)%3!=0,
                   design=rng.normal(size=(2,12,3))*70,base=rng.normal(size=(2,12))*50,catalogue_size=200)
        document=dict(tracks=[track])
        model=GaussianPosition([document],{},200.,weights=[.37],factory=LinearGeometry)
        x=np.array([.2,-.3,.4]);result=model.evaluate(x)
        numeric=[(model.evaluate(x+d,False)['score']-model.evaluate(x-d,False)['score'])/2e-5 for d in np.eye(3)*1e-5]
        np.testing.assert_allclose(result['gradient'],numeric,atol=1e-7)
        track['y'][~track['mask']]=1e8
        self.assertEqual(model.evaluate(x)['score'],result['score'])


if __name__=='__main__':
    unittest.main()
