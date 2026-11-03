import unittest
import numpy as np
from activity_prediction import activity_mask


class ActivityPredictionTests(unittest.TestCase):
    def test_requires_same_receiver_and_channel(self):
        m=activity_mask(np.array([10.]),np.array([0]),np.array([1]),[dict(row_index=0,catalog_number=12)],[12],
            np.array([11.,11.,11.]),np.array([0,1,0]),np.array([1,1,2]))
        np.testing.assert_array_equal(m[:,0],[True,False,False])

    def test_radius_boundary_and_no_support(self):
        m=activity_mask(np.array([20.]),np.array([0]),np.array([1]),[dict(row_index=0,catalog_number=12)],[12,13],
            np.array([3.,37.,37.01]),np.zeros(3,int),np.ones(3,int))
        np.testing.assert_array_equal(m,[[True,False],[True,False],[False,False]])

    def test_invalid_source_row_rejected(self):
        with self.assertRaises(ValueError):activity_mask(np.array([20.]),np.array([0]),np.array([1]),[dict(row_index=1,catalog_number=12)],[12],np.array([]),np.array([]),np.array([]))


if __name__=='__main__':unittest.main()
