import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location('age_nuisance_fixture',Path(__file__).with_name('nuisance.py'))
nuisance=importlib.util.module_from_spec(spec);spec.loader.exec_module(nuisance)


def problem():
    return SimpleNamespace(hardware=np.zeros((1,2)),smooth=np.zeros((1,2)),labels=[0,1],supported=[1],members=[0],
        scan=SimpleNamespace(norads=['11','22']),phase_sigma=np.ones(2),rows=[dict(component='f0')],
        mode_metadata={1:dict(mean_motion_sigma_rev_day=2.,inclination_sigma_deg=3.,raan_sigma_deg=4.)},
        calculate=lambda x:dict(coefficient=np.arange(10,dtype=float)),
        state=lambda x:dict(beta=np.array([1.,2.]),phases=np.array([.1,.2]),smooth=np.array([[3.],[4.]])))


class NuisanceTests(unittest.TestCase):
    def test_layout_width_and_identity_coordinate_map(self):
        result=nuisance.snapshot(problem(),[0.,0.],target_family=22,covariance=np.eye(3))
        self.assertEqual(result['layout']['fragment'][1],len(result['coefficient']))
        np.testing.assert_array_equal(result['target_orbit']['original_standardized_coefficient'],[6.,7.,8.])
        np.testing.assert_array_equal(result['target_orbit']['physical_parameter_revision'],[12.,21.,32.])
        self.assertFalse(result['acceptance_gate'])

    def test_cholesky_mapping_restores_original_physical_coordinates(self):
        result=nuisance.snapshot(problem(),[0.,0.],target_family=22,covariance=np.diag([4.,9.,16.]))
        np.testing.assert_array_equal(result['target_orbit']['original_standardized_coefficient'],[12.,21.,32.])

    def test_missing_diagnostics_cannot_gate_candidate(self):
        p=problem();p.calculate=lambda x:dict(coefficient=np.zeros(1))
        result=nuisance.optional_snapshot(p,[0.,0.],target_family=22)
        self.assertEqual(result['status'],'unavailable');self.assertFalse(result['acceptance_gate'])


if __name__=='__main__':unittest.main()
