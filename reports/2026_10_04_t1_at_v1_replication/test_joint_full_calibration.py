import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from joint_full_calibration import (JointReceiverObjective,CalibrationObjective,
                                    spline_features,spline_prior,receiver_spline)


class JointReceiverTests(unittest.TestCase):
    def test_features_are_receiver_specific_and_reconstruct_knots(self):
        t=np.tile(receiver_spline.NODES,2);rx=np.repeat([0,1],11)
        beta=np.arange(18.).reshape(2,9)
        x=spline_features(t,rx)
        np.testing.assert_allclose(x@beta.ravel(),(beta@receiver_spline.NULL.T).ravel())
        np.testing.assert_array_equal(x[:11,9:],0.)
        np.testing.assert_array_equal(x[11:,:9],0.)
        with self.assertRaises(ValueError):spline_features([10.],[2])

    def test_zero_centered_prior_gradient_and_hessian(self):
        beta=np.linspace(-40.,50.,18)
        value,g=spline_prior(beta);self.assertGreater(value,0.)
        for i in range(18):
            delta=np.eye(18)[i]*1e-4
            fd=(spline_prior(beta+delta)[0]-spline_prior(beta-delta)[0])/2e-4
            self.assertAlmostEqual(g[i],fd,places=8)
        np.testing.assert_allclose(spline_prior(np.zeros(18))[1],0.)

    def test_objective_adds_prior_exactly_once_to_tail(self):
        obj=JointReceiverObjective.__new__(JointReceiverObjective);obj.size=8
        obj.precision=np.zeros((19,19))
        obj.precision[1:10,1:10]=receiver_spline.PRECISION
        obj.precision[10:,10:]=receiver_spline.PRECISION
        vector=np.r_[np.zeros(8),500.,np.arange(18.)]
        with patch.object(CalibrationObjective,'evaluate',return_value=(7.,np.zeros(27))), \
             patch.object(CalibrationObjective,'curvature',return_value=np.zeros((27,27))):
            value,g=obj.evaluate(vector);h=obj.curvature(vector)
        penalty,pg=spline_prior(vector[9:])
        self.assertAlmostEqual(value,7.+penalty)
        np.testing.assert_array_equal(g[:9],0.)
        np.testing.assert_allclose(g[9:],pg)
        np.testing.assert_allclose(h[8:,8:],obj.precision)
        np.testing.assert_array_equal(h[:8],0.)


if __name__=='__main__':unittest.main()
