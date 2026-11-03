import unittest
from types import SimpleNamespace
import numpy as np
from leo.contracts.regional_position import PositionObservations
from timing_batches import batches


class BatchTests(unittest.TestCase):
    def test_time_shift_matches_direct_prediction_with_rf_and_receiver_labels(self):
        obs=PositionObservations(('a','b','c'),np.array([40.,70.,45.]),np.zeros(3),
            np.array([11e9,12e9,11.5e9]),np.array([0,1,0]),np.array([2,4,2]),np.ones(3))
        bank=SimpleNamespace(numbers=np.arange(4));grid=np.array([-1.,-.1,0.,.4,2.])
        def oracle(bank,observations,prior,point,shifts,derivatives=False):
            query=observations.times_s[:,None]+shifts[None,:]
            prediction=query**2*(observations.rf_hz[:,None]/1e9)+observations.receiver[:,None]*30
            return prediction,query>45,None,None
        for start,prediction,visible in batches(oracle,bank,obs,None,[0.,0.],grid,chunk_size=2):
            for i in range(len(prediction)):
                expected,expected_visible,_,_=oracle(bank,obs,None,None,np.full(4,grid[start+i]))
                np.testing.assert_array_equal(prediction[i],expected)
                np.testing.assert_array_equal(visible[i],expected_visible)
        np.testing.assert_array_equal(obs.times_s,[40.,70.,45.])


if __name__=='__main__':unittest.main()
