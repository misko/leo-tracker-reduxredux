import unittest
import types
import numpy as np
from unittest.mock import patch
from fisher_position import fit


class FisherPositionTests(unittest.TestCase):
    def solve(self,target,fixed=False,timing_target=0.):
        base=types.SimpleNamespace(satellites=[0],basis=np.zeros((1,0)),minimum_shift_s=-20.,maximum_shift_s=20.,
                                   state=lambda v:dict(parameters=v))
        target=np.r_[target,np.zeros(6)];target[6]=timing_target
        objective=types.SimpleNamespace(base=base,size=7,scale=np.ones(8),bounds=[(-100.,100.)]*8,
                    evaluate=lambda v:(float(np.sum((v-target)**2)),2*(v-target)),curvature=lambda v:2*np.eye(8))
        module=types.SimpleNamespace(DeadlineReached=type('DeadlineReached',(Exception,),{}))
        with patch.dict('sys.modules',{'timing_model':module}),patch('fisher_position.coordinate',side_effect=lambda p:np.asarray(p)),patch('fisher_position.coordinate_jacobian',return_value=np.eye(2)):
            return fit(objective,np.zeros(8),[0.,0.],2.,fixed)

    def test_interior(self):
        result=self.solve([.3,-.4]);self.assertTrue(result['success'])
        np.testing.assert_allclose(result['point_km'],[.3,-.4],atol=1e-4)

    def test_disk_boundary_and_monotone_actual_objective(self):
        result=self.solve([3.,0.]);self.assertTrue(result['success'])
        np.testing.assert_allclose(result['point_km'],[2.,0.],atol=1e-4)
        self.assertTrue(np.all(np.diff([r['objective'] for r in result['trace']])<=0))

    def test_fixed_position(self):
        result=self.solve([.3,-.4],True);self.assertTrue(result['success'])
        self.assertEqual(result['point_km'],[0.,0.])

    def test_total_timing_boundary(self):
        result=self.solve([0.,0.],True,timing_target=30.);self.assertTrue(result['success'])
        self.assertAlmostEqual(result['vector'][6],20.,places=4)
