"""Checks for conditional row deletion and matched scientific evaluation."""
import unittest
import numpy as np
from experiment import subset
from leo.contracts.regional_position import PositionObservations

class SubsetTests(unittest.TestCase):
    def test_keeps_matching_original_rows(self):
        obs=PositionObservations(('a','b','c'),np.array([0.,1.,2.]),np.array([3.,4.,5.]),np.array([1e9,2e9,3e9]),np.array([0,1,0]),np.array([4,5,6]),np.array([7.,8.,9.]))
        got=subset(obs,np.array([True,False,True]))
        self.assertEqual(got.window_ids,('a','c'))
        for name in ('times_s','measured_hz','rf_hz','receiver','channel','margin'):
            np.testing.assert_array_equal(getattr(got,name),getattr(obs,name)[[0,2]])
        self.assertFalse(got.times_s.flags.writeable)

if __name__=='__main__': unittest.main()
