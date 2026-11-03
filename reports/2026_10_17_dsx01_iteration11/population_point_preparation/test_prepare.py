"""Synthetic narrow-port tests: no hardware, source replay or real predictors."""
from dataclasses import dataclass
from types import SimpleNamespace
import unittest
import numpy as np
import prepare


def predictions():
    return dict(observation_id=np.array(['a','b','c']),times_s=np.array([0.,1.,2.]),rf_hz=np.full(3,11e9),
        receiver=np.array([0,1,0]),channel=np.array([1,2,1]),train_mask=np.array([True,False,True]),
        held_mask=np.array([False,True,False]),boundary_mask=np.zeros(3,bool),number=np.array([11,33]),
        prediction_hz=np.arange(6.).reshape(3,2),visibility_weight=np.ones((3,2)),detection_probability=np.array([.8,.8]),
        correction_hz=np.array([12.,20.,30.]))


class PreparationTests(unittest.TestCase):
    def test_exact_unique_complement_order_and_rejections(self):
        np.testing.assert_array_equal(prepare.complement_indices([22,11,44,33],[33,11]),[0,2])
        for eligible,selected in [([11,11],[11]),([11,22],[11,11]),([11,22],[99]),([0,22],[22])]:
            with self.assertRaises(ValueError):prepare.complement_indices(eligible,selected)

    def test_metadata_port_ignores_measured_values_and_preserves_receive_conventions(self):
        class MetadataOnly(dict):
            def __getitem__(self,key):
                if key in ['measured_hz','measured_cfo_hz','reference','station_position']:raise AssertionError('Forbidden field')
                return super().__getitem__(key)
        p=MetadataOnly(predictions());a=prepare.project_metadata(p)
        p['measured_hz']=np.full(3,999999.);b=prepare.project_metadata(p)
        for key in ['times_s','rf_hz','receiver','channel','measured_hz']:np.testing.assert_array_equal(getattr(a,key),getattr(b,key))
        np.testing.assert_array_equal(a.receiver,[0,1,0]);self.assertTrue(np.all(a.measured_hz==0))

    def test_metadata_order_and_mask_authorities(self):
        p=predictions();authority=dict(metadata_sha256=prepare.metadata_digest(p))
        prepare.validate_predictions(p,p['number'],authority,expected_rows=3)
        p['times_s']=p['times_s'][::-1]
        with self.assertRaisesRegex(ValueError,'metadata/time'):prepare.validate_predictions(p,p['number'],authority,expected_rows=3)
        p=predictions();p['held_mask'][0]=True
        with self.assertRaisesRegex(ValueError,'partition'):prepare.validate_predictions(p,p['number'],authority,expected_rows=3)

    def test_prior_causal_tle_input_and_utc_authorities_must_match(self):
        tle=dict(sha256='digest',provider='provider',collected_utc_ns=1,payload_sha256='payload')
        b=dict(source_tracking_input_sha256='input',origin_utc_ns=2,prior=dict(radius_km=250),causal_tle=tle)
        d=dict(parent_input_sha256='input',origin_utc_ns=2,causal_tle=tle.copy(),derived_input_sha256='train')
        t=dict(input_sha256='train',provenance=dict(prior=b['prior'],tle_sha256='digest',tle_collected_utc_ns=1,tle_payload_sha256='payload'))
        prepare.validate_authorities(b,d,t)
        d['origin_utc_ns']=3
        with self.assertRaisesRegex(ValueError,'UTC'):prepare.validate_authorities(b,d,t)
        d['origin_utc_ns']=2;d['causal_tle']['provider']='other'
        with self.assertRaisesRegex(ValueError,'TLE'):prepare.validate_authorities(b,d,t)

    def test_predict_only_complement_at_common_tau_and_copy_selected_bytes(self):
        old=predictions();vector=np.arange(10.);arm=dict(vector=vector,nuisance=np.array([1.,2.]),predictions=old)
        meta=prepare.project_metadata(old);bank=SimpleNamespace(numbers=np.array([22,44]));calls=[]
        def predict(b,m,p,point,shifts,derivatives):
            self.assertIs(b,bank);np.testing.assert_array_equal(point,vector[:2]);np.testing.assert_array_equal(shifts,[7.,7.])
            self.assertTrue(derivatives);self.assertTrue(np.all(m.measured_hz==0));calls.append('orbit')
            return np.full((3,2),10.),None,np.zeros((3,2,2)),np.full((3,2),200.)
        def elevation(b,m,p,point,shifts):
            calls.append('elevation');return np.full((3,2),.5),None,None,None
        def horizon(sine,width):
            self.assertEqual(width,1e-5);calls.append('horizon');return sine,None
        result=prepare.predict_arm(bank,object(),meta,arm,SimpleNamespace(predict=predict,elevation=elevation,horizon=horizon))
        self.assertEqual(calls,['orbit','elevation','horizon'])
        np.testing.assert_array_equal(result['unsupported_mean_hz'],10.+old['correction_hz'][:,None]+np.zeros((3,2)))
        np.testing.assert_array_equal(result['unsupported_timing_slope_hz_s'],np.full((3,2),200.))
        for new,source in prepare.SELECTED.items():self.assertEqual(prepare.array_digest(result[new]),prepare.array_digest(old[source]))
        self.assertNotIn('measured_hz',result);self.assertNotIn('unsupported_detection_q',result)


if __name__=='__main__':unittest.main()
