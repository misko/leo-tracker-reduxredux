import unittest
import numpy as np
from root_cause_geometry import profile_information


class GeometryTests(unittest.TestCase):
    def test_schur_removes_only_nuisance_explainable_information(self):
        h=np.array([[4.,0.,1.],[0.,9.,2.],[1.,2.,2.]])
        p=profile_information(h,[2])
        np.testing.assert_allclose(p,[[3.5,-1.],[-1.,7.]])
        self.assertTrue(np.all(np.linalg.eigvalsh(p)>0))

    def test_no_coupling_leaves_position_information(self):
        np.testing.assert_allclose(profile_information(np.diag([3.,5.,9.]),[2]),np.diag([3.,5.]))
