import copy
import unittest
import complete


class CompleteTests(unittest.TestCase):
    def test_native_fallback_and_unavailable_are_distinct(self):
        request = dict(case='case',role='target',native_observation_id='id',complete_owner='owner',probe=dict(time_s=1.),original_observation=dict(measured_cfo_hz=100.))
        record = dict(status='complete',refinement=dict(numerical_frequency_qualified=False,numerical_margin_qualified=True,corrected_tracking_cfo_hz=120.))
        row=complete.correction(request,record,False)
        self.assertEqual(row['corrected_cfo_hz'],100.)
        self.assertTrue(row['payload_and_parity_complete'])
        missing=complete.correction(request,dict(status='failed',error='parity'),False)
        self.assertFalse(missing['payload_and_parity_complete'])
        self.assertEqual(missing['corrected_cfo_hz'],100.)

    def test_qualified_delta_is_not_wrapped(self):
        request = dict(case='case',role='target',native_observation_id='id',complete_owner='owner',probe=dict(time_s=1.),original_observation=dict(measured_cfo_hz=-220000.))
        record = dict(status='complete',refinement=dict(numerical_frequency_qualified=True,numerical_margin_qualified=True,corrected_tracking_cfo_hz=-219923.))
        row=complete.correction(request,record,True)
        self.assertEqual(row['correction_delta_hz'],77.)
        self.assertEqual(row['corrected_cfo_hz'],-219923.)

    def test_previous_reuse_requires_all_original_fields(self):
        keys=('case','role','complete_owner','native_observation_id','original_observation','tracking','source_input','source_session_id','recording_id','raw_recording_authority_digest','probe','original_candidate')
        request={k:k for k in keys}
        request['raw_authority']={k:k for k in ('segment','segment_manifest_sha256','index_path','index_sha256','local_sequence','index','target','sample_rate_hz','receiver_ids')}
        previous=copy.deepcopy(request)
        self.assertTrue(complete.reuse_matches(request,previous))
        previous['tracking']='changed'
        self.assertFalse(complete.reuse_matches(request,previous))

    def test_one_physical_window_can_have_two_receiver_ids(self):
        a=dict(case='case',probe=dict(visit_index=4,probe_index=0,window_start_counter=100,receiver_id=0))
        b=copy.deepcopy(a);b['probe']['receiver_id']=1
        self.assertEqual(complete.physical_key(a),complete.physical_key(b))


if __name__=='__main__':unittest.main()
