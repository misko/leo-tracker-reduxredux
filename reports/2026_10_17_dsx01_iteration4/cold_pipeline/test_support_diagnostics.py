from types import SimpleNamespace
import unittest
import numpy as np
from support_diagnostics import support


class SupportTests(unittest.TestCase):
    def test_nearest_residual_ignores_below_horizon_alternatives(self):
        terms=SimpleNamespace(residual_hz=np.array([[1.,700.],[3.,800.]]),
            responsibilities=np.array([[0.,.1],[0.,0.]]),clutter_probability=np.array([.9,1.]))
        visibility=np.array([[0.,1.],[0.,0.]])
        result=support(terms,visibility,np.array([.5,.6]),np.ones(2,bool))
        self.assertEqual(result['rows_with_any_selected_visible'],1)
        self.assertEqual(result['nearest_visible_within_125_hz'],0)
        self.assertEqual(result['nearest_visible_residual_hz']['median'],700.)
        self.assertEqual(result['no_visible_selected_rows'],1)

    def test_empty_time_bin_is_explicit_and_does_not_invent_support(self):
        terms=SimpleNamespace(residual_hz=np.ones((2,2)),responsibilities=np.zeros((2,2)),clutter_probability=np.ones(2))
        result=support(terms,np.ones((2,2)),np.array([.5,.6]),np.zeros(2,bool))
        self.assertEqual(result['observations'],0);self.assertEqual(result['associated'],0)
        self.assertIsNone(result['nearest_visible_residual_hz'])


if __name__=='__main__':unittest.main()
