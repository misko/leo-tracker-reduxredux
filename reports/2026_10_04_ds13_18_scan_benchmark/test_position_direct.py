import unittest
import numpy as np
import types
from unittest.mock import patch
from position_direct import coordinate_jacobian,disk_feasible,fit


class DirectPositionTests(unittest.TestCase):
    def synthetic_fit(self,target,fixed=False):
        base=types.SimpleNamespace(satellites=[0],basis=np.zeros((1,0)),minimum_shift_s=-20.,maximum_shift_s=20.,
                                   state=lambda v:dict(parameters=v))
        target=np.r_[target,np.zeros(6)]
        objective=types.SimpleNamespace(base=base,size=7,scale=np.ones(8),bounds=[(-100.,100.)]*8,
                                        evaluate=lambda v:(float(np.sum((v-target)**2)),2*(v-target)))
        module=types.SimpleNamespace(DeadlineReached=type('DeadlineReached',(Exception,),{}))
        with patch.dict('sys.modules',{'timing_model':module}), patch('position_direct.coordinate',side_effect=lambda p:np.asarray(p)):
            return fit(objective,np.zeros(8),[0.,0.],budget_s=1.,fixed=fixed)

    def test_direct_interior_optimum(self):
        result=self.synthetic_fit([.3,-.4])
        self.assertTrue(result['success'])
        np.testing.assert_allclose(result['point_km'],[.3,-.4],atol=1e-5)

    def test_boundary_kkt_is_not_full_gradient_zero(self):
        result=self.synthetic_fit([3.,0.])
        self.assertTrue(result['success'])
        np.testing.assert_allclose(result['point_km'],[2.,0.],atol=1e-5)
        self.assertGreater(abs(result['position_gradient_per_km'][0]),1.)

    def test_fixed_probe_does_not_move_toward_target(self):
        result=self.synthetic_fit([.3,-.4],fixed=True)
        self.assertTrue(result['success'])
        self.assertEqual(result['point_km'],[0.,0.])

    def test_disk_rejects_square_corners(self):
        self.assertTrue(disk_feasible([2.,0.]))
        self.assertFalse(disk_feasible([2.,2.]))

    def test_chain_rule_coordinate_jacobian(self):
        matrix=np.array([[2.,3.],[-1.,4.]])
        with patch('position_direct.coordinate',side_effect=lambda p:matrix@p+[7.,8.]):
            np.testing.assert_allclose(coordinate_jacobian([.2,-.3]),matrix,atol=1e-10)
