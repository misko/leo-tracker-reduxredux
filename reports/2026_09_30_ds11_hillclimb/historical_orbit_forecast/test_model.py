import unittest
import numpy as np
from model import bounded,fit


class ForecastTests(unittest.TestCase):
    def test_joint_bounds_preserve_direction(self):
        x=np.array([[10.,0,0,.02,0,0],[0,0,0,0,0,0]])
        np.testing.assert_allclose(bounded(x)[0],x[0]*.25)
        self.assertFalse(bounded(x)[1].any())

    def test_known_coefficient_and_rotation(self):
        rng=np.random.default_rng(42);x=rng.normal(size=(30,6));x[:,3:]*=.001
        y=-.3*bounded(x);out=fit(x,y)
        self.assertTrue(out['qualified']);self.assertAlmostEqual(out['alpha'],-.3,places=6)
        rotation=np.array([[0.,1,0],[-1,0,0],[0,0,1.]])
        rotate=lambda a:np.column_stack((a[:,:3]@rotation,a[:,3:]@rotation))
        self.assertAlmostEqual(fit(rotate(x),rotate(y))['alpha'],out['alpha'],places=6)

    def test_training_bound_is_not_extrapolated(self):
        x=np.array([[1.,0,0,.001,0,0]])
        result=fit(x,3*x)
        self.assertEqual(result['alpha'],1.)
        self.assertTrue(result['qualified'])
