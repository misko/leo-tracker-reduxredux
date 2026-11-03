import unittest
import numpy as np
from model import design,likelihood,source_weights


class ModelTests(unittest.TestCase):
    def test_gradient_and_zero_geometry(self):
        los=np.array([[.3,0,.9],[-.2,0,.8],[.1,0,.7]])
        x=design(los,[0,1,0],[0,1,1],'signed');p=np.linspace(-.2,.2,9);hit=np.array([1,0,1]);w=np.array([.5,1,.5])
        scores,g=likelihood(p,x,hit,w)
        finite=np.array([(w@likelihood(p+np.eye(9)[i]*1e-5,x,hit,w)[0]-w@likelihood(p-np.eye(9)[i]*1e-5,x,hit,w)[0])/2e-5 for i in range(9)])
        np.testing.assert_allclose(g,finite,atol=1e-8)
        p[-1]=0
        np.testing.assert_allclose(likelihood(p,x,hit,w)[0],likelihood(p[:-1],x[:,:8],hit,w)[0])
        a=likelihood(p,x,np.zeros(3),w)[0];b=likelihood(p,x,np.ones(3),w)[0]
        np.testing.assert_allclose(np.exp(a)+np.exp(b),1.)

    def test_source_balancing_excludes_held(self):
        np.testing.assert_array_equal(source_weights(['a','a','b','a'],[1,1,1,0]),[.5,.5,1.,0.])
