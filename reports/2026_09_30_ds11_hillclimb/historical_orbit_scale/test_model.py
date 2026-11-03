import unittest
import numpy as np
from scipy.stats import multivariate_t
from model import scores,fit


class ScaleTests(unittest.TestCase):
    def test_normalized_density_and_gradient(self):
        vectors=np.array([[1.,2,3],[0,1,-2.]])
        ages=np.array([.5,2]);p=np.array([.3,.8])
        s,g=scores(p,ages,vectors,True)
        sigma=np.exp(p[0]+p[1]*np.log1p(ages))
        expected=[multivariate_t.logpdf(v,shape=np.eye(3)*q*q,df=4) for v,q in zip(vectors,sigma)]
        np.testing.assert_allclose(s,expected,atol=1e-12)
        for i in range(2):
            step=np.eye(2)[i]*1e-5
            np.testing.assert_allclose((scores(p+step,ages,vectors,True)[0]-scores(p-step,ages,vectors,True)[0])/2e-5,g[:,i],atol=1e-8)

    def test_constant_nested_and_rotation_invariance(self):
        v=np.array([[1,2,3],[4,5,6.]])
        s=scores([.5],[0,4],v,False)[0]
        np.testing.assert_allclose(s,scores([.5,0],[0,4],v,True)[0])
        np.testing.assert_allclose(s,scores([.5],[0,4],v[:,[2,0,1]],False)[0])

    def test_synthetic_age_effect_recovered(self):
        rng=np.random.default_rng(4);age=rng.uniform(0,3,4000)
        v=rng.normal(size=(len(age),3))/np.sqrt(rng.chisquare(4,len(age))[:,None]/4)
        v*=np.exp(.4+.8*np.log1p(age))[:,None]
        out=fit(age,v,np.ones(len(age)),True)['selected']
        self.assertIsNotNone(out)
        np.testing.assert_allclose(out['parameters'],[.4,.8],atol=.1)
