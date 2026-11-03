import inspect
import types
import unittest
from unittest.mock import patch
import numpy as np
import fisher_position
import radius_fisher
from root_cause_8km import design,choose_starts


class RadiusTests(unittest.TestCase):
    def test_solver_only_changes_disk_constants(self):
        source=inspect.getsource(radius_fisher.fit)
        source=source.replace('def fit(objective,start,point,budget_s=20.,fixed=False,radius_km=8.):\n    if not 0 < radius_km <= 8.:raise ValueError("radius must be in (0, 8] km")\n    def disk_feasible(point):\n        return bool(np.dot(point,point)<=radius_km**2+1e-8)',
                              'def fit(objective,start,point,budget_s=20.,fixed=False):')
        source=source.replace('(-radius_km,radius_km)','(-2.,2.)').replace('>=radius_km-1e-5','>=2.-1e-5').replace('radius_km**2-np.dot','4.-np.dot')
        self.assertEqual(source.strip(),inspect.getsource(fisher_position.fit).strip())

    def test_probe_design_reproducible_inside_eight_km(self):
        d=design();np.testing.assert_array_equal(d,design())
        self.assertEqual(len(d),24)
        self.assertTrue(np.all(np.linalg.norm(d,axis=1)<=8+1e-9))
        self.assertEqual(sum(np.isclose(np.linalg.norm(d,axis=1),8)),8)

    def test_invalid_radius_rejected(self):
        with self.assertRaises(ValueError):radius_fisher.fit(None,None,None,radius_km=9)

    def test_extended_disk_reaches_known_quadratic_minimum(self):
        class Objective:
            def __init__(self):
                self.scale=np.ones(8);self.bounds=[(-200,200)]*2+[(None,None)]*4+[(-10,10),(None,None)]
                self.size=7
                self.base=types.SimpleNamespace(satellites=np.array([0]),basis=np.empty((1,0)),
                    minimum_shift_s=-20.,maximum_shift_s=20.,state=lambda v:dict(parameters=np.r_[v[:6],v[6]]))
                self.target=np.array([3.,0.,0.,0.,0.,0.,0.,0.])
            def evaluate(self,v):
                delta=v-self.target;return float(delta@delta/2),delta
            def curvature(self,v):return np.eye(8)
        # Importing timing_model requires the established research model paths.
        from numeric_data import enable_research_model
        enable_research_model()
        with patch('radius_fisher.coordinate',side_effect=lambda p:np.asarray(p)),patch('radius_fisher.coordinate_jacobian',return_value=np.eye(2)):
            small=radius_fisher.fit(Objective(),np.zeros(8),[0.,0.],3.,False,radius_km=2.)
            large=radius_fisher.fit(Objective(),np.zeros(8),[0.,0.],3.,False,radius_km=8.)
        self.assertTrue(small['success']);self.assertTrue(large['success'])
        np.testing.assert_allclose(small['point_km'],[2.,0.],atol=1e-4)
        np.testing.assert_allclose(large['point_km'],[3.,0.],atol=1e-4)
