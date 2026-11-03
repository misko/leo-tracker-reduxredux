import unittest
from summarize_heldout_decoders import matched_residuals


class MatchedResidualTests(unittest.TestCase):
    def test_different_membership_and_identity_excluded(self):
        def r(row,sat,e):return dict(row_index=row,catalog_number=sat,residual_native_hz=e)
        result=matched_residuals([r(1,10,3),r(2,10,100),r(3,10,500)],
            [r(1,10,4),r(2,20,200),r(4,10,1000)])
        self.assertEqual(result,dict(points=1,fitted_rms_hz=3.,zero_rms_hz=4.))

    def test_empty_intersection_is_not_zero_error(self):
        self.assertIsNone(matched_residuals([],[])['fitted_rms_hz'])


if __name__=='__main__':unittest.main()
