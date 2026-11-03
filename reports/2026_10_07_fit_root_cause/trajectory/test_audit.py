import unittest
import numpy as np
from audit import physical_callback

class CallbackAuditTest(unittest.TestCase):
    def test_zero_arm_decoding_restores_fixed_coordinate(self):
        initial=np.arange(10,dtype=float);z=np.arange(9,dtype=float)
        v=physical_callback(z,'zero-c','original',initial)
        self.assertEqual(v[6],0)
        self.assertEqual(v[7],6)
        self.assertEqual(v[8],7)
        self.assertEqual(initial[6],6)
    def test_scaling_perturbation_is_optimizer_coordinates_only(self):
        initial=np.zeros(10);z=np.ones(10)
        original=physical_callback(z,'fitted-c','original',initial)
        changed=physical_callback(z,'fitted-c','cscale20',initial)
        self.assertEqual(changed[6],20)
        np.testing.assert_array_equal(np.delete(changed,6),np.delete(original,6))
        np.testing.assert_allclose(physical_callback(z,'fitted-c','allscale01',initial),original*.1)

if __name__=='__main__':unittest.main()
