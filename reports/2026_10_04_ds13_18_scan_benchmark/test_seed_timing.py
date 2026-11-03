import unittest
import numpy as np
from seed_timing_variant import timing_seed


class TimingSeedTests(unittest.TestCase):
    def test_weighted_median_preserves_relative_timing(self):
        tracks=[dict(satellite_index=0,offset_s=-6.,accepted=True,source_groups=80),
                dict(satellite_index=0,offset_s=-20.,accepted=True,source_groups=20),
                dict(satellite_index=1,offset_s=0.,accepted=True,source_groups=90)]
        seed,ids=timing_seed(tracks,3)
        self.assertEqual(ids,[0,1])
        np.testing.assert_array_equal(seed,[-3.,3.,0.])
        self.assertEqual(seed[0]-seed[1],-6.)

    def test_unaccepted_seed_does_not_enter_mean(self):
        seed,ids=timing_seed([dict(satellite_index=0,offset_s=4.,accepted=True,source_groups=10),
                              dict(satellite_index=1,offset_s=-20.,accepted=False,source_groups=100)],2)
        np.testing.assert_array_equal(seed,[0.,0.])
        self.assertEqual(ids,[0])
