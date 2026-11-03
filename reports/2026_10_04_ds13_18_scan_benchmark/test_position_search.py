import unittest
import numpy as np
from position_search import subset_rows,point_design,calibration_warning


class PositionTests(unittest.TestCase):
    def test_calibration_warning_is_explicit_and_retained(self):
        record={'arms':{'fitted-c':{'success':False,'nuisance_gradient':.1}}}
        with self.assertRaisesRegex(ValueError,'not converged'):calibration_warning(2,record,False)
        warning=calibration_warning(2,record,True)
        self.assertEqual(warning['fold'],2)
        self.assertIn('not validated',warning['warning'])
        record['arms']['fitted-c']['success']=True
        self.assertIsNone(calibration_warning(2,record,False))
    def test_deterministic_area_design_inside_disk(self):
        p=point_design()
        np.testing.assert_array_equal(p,point_design())
        self.assertTrue(np.all(np.linalg.norm(p,axis=1)<=2+1e-12))
        self.assertEqual(len(p),33)

    def test_satellite_and_window_rankings_have_different_units(self):
        a=[dict(row_index=0,catalog_number=1,residual_hz=20),
           dict(row_index=1,catalog_number=1,residual_hz=20),
           dict(row_index=2,catalog_number=2,residual_hz=1)]
        margin=np.array([.1,.2,.9])
        self.assertEqual(subset_rows(a,margin,'rms',.5),[2])
        self.assertEqual(subset_rows(a,margin,'support',.5),[0,1])
        self.assertEqual(subset_rows(a,margin,'glrt',.5),[1,2])
        for kind in ('rms','support','glrt'):
            self.assertEqual(subset_rows(a,margin,kind,1.),[0,1,2])
