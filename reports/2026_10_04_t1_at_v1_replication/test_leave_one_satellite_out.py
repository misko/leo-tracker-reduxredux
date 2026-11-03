import unittest
from types import SimpleNamespace
import numpy as np
from leave_one_satellite_out import delete_satellite,remap_start


class DeletionTests(unittest.TestCase):
    def test_remove_both_receivers_and_bank_without_mutating_source(self):
        d=SimpleNamespace(times=np.arange(4.),owners=np.array([11,22,11,33]),
                          receiver=np.array([0,0,1,1]),numbers=np.array([11,22,33]),
                          position=np.ones((3,2,3)),velocity=np.ones((3,2,3)),
                          initial=np.arange(9.))
        reduced,keep,ids=delete_satellite(d,11)
        np.testing.assert_array_equal(reduced.owners,[22,33])
        np.testing.assert_array_equal(reduced.numbers,[22,33])
        np.testing.assert_array_equal(reduced.initial,np.r_[np.arange(6.),7.,8.])
        self.assertEqual(len(d.times),4)
        again,_,_=delete_satellite(d,22)
        np.testing.assert_array_equal(again.owners,[11,11,33])

    def test_baseline_preserves_all_windows_and_unknown_satellite_rejected(self):
        d=SimpleNamespace(times=np.arange(3.),owners=np.array([11,22,11]),
                          numbers=np.array([11,22]),position=np.ones((2,2,3)),
                          velocity=np.ones((2,2,3)),initial=np.arange(8.))
        baseline,keep,ids=delete_satellite(d,None)
        np.testing.assert_array_equal(baseline.initial,d.initial)
        np.testing.assert_array_equal(baseline.times,d.times)
        self.assertTrue(keep.all())
        with self.assertRaises(ValueError):delete_satellite(d,33)

    def test_timing_remap_preserves_remaining_total_shifts(self):
        basis=np.array([[1.],[-1.]])/np.sqrt(2)
        obj=SimpleNamespace(bounds=[(None,None)]*6+[(-10.,10.)],base=SimpleNamespace(basis=basis))
        record=dict(parameters=np.r_[np.arange(6.),1.,2.,3.],coefficient=50.)
        start=remap_start(obj,record,np.array([0,2]),'fitted-c')
        np.testing.assert_allclose(start[6]+basis@start[7:-1],[1.,3.])
        self.assertEqual(start[-1],50.)


if __name__=='__main__':unittest.main()
