import unittest
from types import SimpleNamespace
import numpy as np
from full_data_calibration import supported_rows,validate_scope,FullCalibration
from full_data_localization import transferred


class FullCalibrationTests(unittest.TestCase):
    def test_full_scope_rejects_holdouts_and_missing_windows(self):
        d=SimpleNamespace(original_rows=np.arange(5),group=np.arange(5),sources={'input':'hash'})
        r=dict(fit_original_rows=list(range(5)),evaluation_original_rows=list(range(5)),heldout_original_rows=[],observations=d.sources)
        validate_scope(r,d)
        with self.assertRaises(ValueError):validate_scope(dict(r,fit_original_rows=[0,1,2,3]),d)
        with self.assertRaises(ValueError):validate_scope(dict(r,heldout_original_rows=[4]),d)

    def test_support_gate_is_quality_not_time_fold(self):
        probability=np.array([[.9,.1],[.7,.3],[.1,.9],[.9,.1]])
        visible=np.array([[True,True],[True,True],[True,False],[True,True]])
        residual=np.array([[20.,0.],[0.,0.],[0.,0.],[601.,0.]])
        mask,owner=supported_rows(probability,visible,residual)
        np.testing.assert_array_equal(mask,[True,False,False,False])
        np.testing.assert_array_equal(owner,[0,0,1,0])

    def test_baseline_has_one_receiver_line_and_no_rf_term(self):
        cal=FullCalibration.__new__(FullCalibration)
        cal.data=SimpleNamespace(receiver=np.array([0,1,0]),times=np.array([140.,150.,160.]))
        cal.correction=np.array([1.,2.,3.])
        cal.record={'arms':{'fitted-c':{'parameters':[0.,0.,10.,2.,20.,3.],'coefficient':999.}}}
        np.testing.assert_allclose(cal.receiver_baseline('fitted-c'),[-9.,22.,33.])

    def test_localization_transfer_remaps_satellite_ids_without_changing_rf(self):
        record=dict(parameters=np.r_[np.zeros(6),[-2.,3.]],coefficient=17.,point_km=[0.,0.])
        old=SimpleNamespace(numbers=np.array([100,200]))
        data=SimpleNamespace(numbers=np.array([200,300,100]),initial=np.r_[np.zeros(6),[8.,9.,10.]])
        result=transferred(record,data,old,np.array([1.,2.,3.,4.]))
        np.testing.assert_allclose(result['parameters'],np.r_[[0.,0.,1.,2.,3.,4.],[3.,9.,-2.]])
        self.assertEqual(result['coefficient'],17.)


if __name__=='__main__':unittest.main()
