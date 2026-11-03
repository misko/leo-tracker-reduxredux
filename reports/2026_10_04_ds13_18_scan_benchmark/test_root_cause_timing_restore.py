import types
import unittest
import numpy as np
from root_cause_timing_restore import single_timing_vector


class TimingRestoreTests(unittest.TestCase):
    def test_only_one_total_shift_changes_and_other_parameters_are_frozen(self):
        basis=np.array([[1.,1.],[-1.,1.],[0.,-2.]])/np.sqrt([2.,6.])
        obj=types.SimpleNamespace(size=9,base=types.SimpleNamespace(basis=basis))
        start=np.arange(10,dtype=float);total=np.array([1.,2.,3.])
        vector,changed=single_timing_vector(obj,start,total,1,-5.)
        np.testing.assert_allclose(vector[6]+basis@vector[7:9],[1.,-5.,3.])
        np.testing.assert_array_equal(vector[:6],start[:6]);self.assertEqual(vector[-1],start[-1])
        np.testing.assert_array_equal(total,[1.,2.,3.])
