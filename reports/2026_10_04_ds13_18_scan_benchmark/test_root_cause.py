import types
import unittest
import numpy as np
from root_cause import delete_satellite, remap_start


class RootCauseTests(unittest.TestCase):
    def data(self):
        d = types.SimpleNamespace(numbers=np.array([1,2,3]), initial=np.arange(9.),
            position=np.arange(18).reshape(3,2,3), velocity=np.zeros((3,2,3)))
        for key in ('times','measured','rf','receiver','channel','group','margin','original_rows'):
            setattr(d,key,np.arange(4))
        return d

    def test_deletion_removes_owned_windows_and_only_requested_bank_member(self):
        d=self.data(); r,keep,ids=delete_satellite(d,np.array([1,2,1,3]),1)
        np.testing.assert_array_equal(r.original_rows,[1,3])
        np.testing.assert_array_equal(r.numbers,[2,3])
        np.testing.assert_array_equal(r.initial,np.r_[np.arange(6),7,8])
        np.testing.assert_array_equal(d.numbers,[1,2,3])
        self.assertFalse(np.shares_memory(r.measured,d.measured))

    def test_baseline_keeps_exact_membership(self):
        d=self.data();r,keep,ids=delete_satellite(d,np.array([1,2,1,3]),None)
        self.assertTrue(keep.all());np.testing.assert_array_equal(r.initial,d.initial)

    def test_warm_start_preserves_total_timing(self):
        basis=np.array([[1.],[-1.]])/np.sqrt(2)
        obj=types.SimpleNamespace(base=types.SimpleNamespace(basis=basis))
        record=dict(parameters=[0,0,10,.5,20,-.5,2,4,6],coefficient=123)
        vector=remap_start(obj,record,np.array([0,2]),'fitted-c')
        np.testing.assert_allclose(vector[6]+basis@vector[7:-1],[2,6])
        self.assertEqual(vector[-1],123)
        self.assertEqual(remap_start(obj,record,np.array([0,2]),'zero-c')[-1],0)

    def test_empty_deletion_rejected(self):
        with self.assertRaises(ValueError):delete_satellite(self.data(),np.ones(4),1)


if __name__=='__main__':unittest.main()
