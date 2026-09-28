import unittest
from source_continuity_math import alias_check,cross_channel_difference


class Tests(unittest.TestCase):
    def test_alias_scale_and_integer(self):
        s=11.2e9/10e9
        row={'actual_rf_hz':10e9,'source_cfo_hz':123.,'normalized_cfo_hz':s*(123-2/4.4e-6)}
        self.assertEqual(alias_check([row])['alias_indices'],[2])
        row['normalized_cfo_hz']+=100
        with self.assertRaises(ValueError):alias_check([row])

    def test_interpolation_offset_and_no_extrapolation(self):
        make=lambda t,f:{'utc_ns':int(t*1e9),'normalized_cfo_hz':f}
        right=[make(0,0),make(1,10),make(2,20)]
        left=[make(-1,-5),make(.5,10),make(1.5,20),make(3,35)]
        out=cross_channel_difference(left,right)
        self.assertEqual(out['points'],2)
        self.assertEqual(out['constant_difference_hz'],5)
        self.assertEqual(out['difference_rms_after_constant_hz'],0)
        self.assertFalse(cross_channel_difference(left,right,max_gap_s=.5)['supported'])


if __name__=='__main__':unittest.main()
