import unittest
import types
from pathlib import Path
from unittest.mock import patch
import numpy as np
from satellite_gradients import components,run


class GradientAttributionTests(unittest.TestCase):
    def test_failed_calibration_requires_explicit_forwarded_opt_in(self):
        for permit in (False,True):
            with patch('satellite_gradients.prepare',side_effect=ValueError('inspection only')) as prepare:
                with self.assertRaisesRegex(ValueError,'inspection only'):
                    run(Path('/scan'),Path('/output'),permit_calibration_warning=permit)
                self.assertEqual(prepare.call_args.kwargs,{'permit_calibration_warning':permit})

    def test_soft_components_sum_with_receiver_partition(self):
        design=np.arange(24,dtype=float).reshape(6,4)/10
        jac=types.SimpleNamespace(transpose_multiply=lambda w:design.T@w)
        gradient=np.arange(6,dtype=float).reshape(3,2)/3
        coordinate=np.array([[1.,.2],[.1,1.]])
        rows=components(jac,gradient,np.ones((3,2))/2,np.array([0,1,0]),[101,102],coordinate)
        total=np.sum([[r['east_per_100m'],r['north_per_100m']] for r in rows],axis=0)
        np.testing.assert_allclose(total,coordinate.T@(design.T@(-gradient.ravel()))[:2]/10)
        self.assertAlmostEqual(sum(r['effective_window_support'] for r in rows),3.)
