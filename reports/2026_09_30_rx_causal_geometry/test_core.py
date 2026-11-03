import unittest
import numpy as np
from core import objective,log_probabilities,design


class ModelTests(unittest.TestCase):
    def test_gradient(self):
        rng=np.random.default_rng(21);x=rng.normal(size=(9,4,5));offset=np.log(np.full((9,4),.25));y=np.arange(9)%4;b=rng.normal(size=5)
        analytic=objective(b,x,offset,y)[1];numeric=[]
        for k in range(5):
            step=np.zeros(5);step[k]=1e-6
            numeric.append((objective(b+step,x,offset,y)[0]-objective(b-step,x,offset,y)[0])/2e-6)
        np.testing.assert_allclose(analytic,numeric,atol=1e-7)

    def test_zero_correction_preserves_baseline(self):
        p=np.array([[.1,.2,.3,.4]])
        np.testing.assert_allclose(np.exp(log_probabilities(np.zeros(5),np.ones((1,4,5)),np.log(p))),p)

    def test_signed_controls_preserve_other_features(self):
        lane={'geometry':np.arange(18.).reshape(3,2,3),'prior':np.log([.2,.3,.5]),'visible':np.ones((3,2),bool),'roles':np.array(['reception','held_frequency','held_frequency'])}
        original=design(lane)
        for control in ('swap','reverse','permute'):
            np.testing.assert_equal(original[...,:4],design(lane,control)[...,:4])
        np.testing.assert_equal(original[...,4],-design(lane,'swap')[...,4])
