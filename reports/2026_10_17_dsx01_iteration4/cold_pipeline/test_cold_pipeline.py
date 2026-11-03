from copy import deepcopy
import unittest
import numpy as np
from numpy.testing import assert_allclose,assert_array_equal
from derive import temporal_half,perturb_excluded,payload
from clock_transport import extend_frozen_clock
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1
from leo.analysis.channel_group_calibration import GroupCalibrationFrame
from leo.analysis.frozen_group_calibration import FrozenGroupCalibration
from leo.analysis.sequential_group_calibration import FrozenSequentialCalibration,SequentialShift


def document():
    fs=2_500_000;counter=2**60
    timing=PersistentHopUtcTimingAuthorityV1.from_host_bracket(
        session_id='test',sample_rate_hz=fs,session_start_device_sample_counter=counter,
        begin_before_realtime_ns=10**18,begin_before_monotonic_ns=1000,
        begin_after_realtime_ns=10**18+1000,begin_after_monotonic_ns=2000,
        terminal_realtime_ns=10**18+120_000_000_000,
        terminal_monotonic_ns=120_000_001_000)
    candidate=dict(candidate_rank=0,integer_epoch_sample=1,fractional_epoch_offset_samples=.1,
        fractional_tracking_cfo_hz=100.,fractional_exact_score=3.,fractional_control_score=1.,
        fractional_margin=2.,passed_fractional_margin_gate=True)
    probes=[]
    for i,t in enumerate([1.,59.,59.99,60.,90.,119.]):
        probes.append(dict(visit_index=i,receiver_id=i%2,probe_index=0,probe_start_ms=0,
            channel=i%8+1,edge='lower',actual_rf_hz=11.1e9,valid_start_counter=counter+round(t*fs),
            payload_start_sample=0,candidates=[deepcopy(candidate),dict(candidate,candidate_rank=1)]))
    return dict(last_sample_counter=counter+120*fs,source=dict(session_id='test',capture_mode='adaptive',
        sample_rate_hz=fs,radio_id='test',stream_generation='test',input_manifest_sha256='sha256:'+'0'*64,
        analysis_manifest_sha256='sha256:'+'1'*64,raw_recording_authority_digest='sha256:'+'2'*64,
        timing=timing.model_dump(mode='json'),qualified=True,probes=probes,probe_ms=20))


class ColdPipelineTests(unittest.TestCase):
    def test_true_half_uses_integer_counter_intervals_and_whole_probes(self):
        doc=document();before=deepcopy(doc)
        early,r=temporal_half(doc)
        late,s=temporal_half(doc,direction='late_to_early')
        self.assertEqual(r['cut_s'],60.)
        self.assertEqual([p['visit_index'] for p in early['source']['probes']],[0,1])
        self.assertEqual([p['visit_index'] for p in late['source']['probes']],[3,4,5])
        self.assertEqual(r['boundary_keys'],[(2,0,0)])
        self.assertFalse(set(map(tuple,r['training_keys']))&set(map(tuple,s['training_keys'])))
        self.assertEqual(doc,before)
        self.assertEqual(sum(len(p['candidates']) for p in early['source']['probes']),4)
        for k in ['timing','input_manifest_sha256','analysis_manifest_sha256','raw_recording_authority_digest']:
            self.assertEqual(early['source'][k],doc['source'][k])

    def test_all_excluded_candidate_values_leave_training_bytes_unchanged(self):
        for direction in ['early_to_late','late_to_early']:
            doc=document();derived,r=temporal_half(doc,direction=direction)
            changed=perturb_excluded(doc,r)
            other,s=temporal_half(changed,direction=direction)
            self.assertEqual(payload(derived),payload(other));self.assertEqual(r,s)
            self.assertNotEqual(payload(doc),payload(changed))

    def test_invalid_or_duplicate_probe_authority_is_rejected(self):
        doc=document();doc['source']['probes'].append(deepcopy(doc['source']['probes'][0]))
        with self.assertRaises(ValueError):temporal_half(doc)
        doc=document();doc['source']['probes'][0]['valid_start_counter']=0
        with self.assertRaises(ValueError):temporal_half(doc)

    def test_constant_clock_boundary_extension_retains_affine_slopes_and_train_closure(self):
        common=FrozenGroupCalibration(30.,11.1e9,GroupCalibrationFrame((0,1),(.4,.6)),
            np.array([10.,.2,-20.,-.3,50.]),np.array([[1.,.1],[2.,-.2]]),
            np.array([3.,4.]),np.array([.01,-.02]),np.array([0.,30.,60.]),
            np.array([[1.,4.,2.],[-2.,-5.,3.]]),np.array([[.5,1.,1.5],[2.,-1.,0.]]))
        calibration=FrozenSequentialCalibration(common,SequentialShift((0,1),[7.,-8.]))
        extended=extend_frozen_clock(calibration,-30.,120.)
        times=np.linspace(0,60,19);rf=np.full(19,11.2e9);rx=np.arange(19)%2;high=np.arange(19)%3==0
        assert_array_equal(calibration.predict(times,rf,rx,high),extended.predict(times,rf,rx,high))
        with self.assertRaises(ValueError):calibration.predict([90.],[11.2e9],[0],[True])
        for receiver in [0,1]:
            for high_group in [False,True]:
                before=extended.predict([60.],[11.2e9],[receiver],np.array([high_group]))[0]
                after=extended.predict([90.],[11.2e9],[receiver],np.array([high_group]))[0]
                groups=common.frame.design(np.array([receiver]),np.array([high_group]))
                slope=common.baseline_affine[receiver,1]+common.receiver_rf_coefficients[2*receiver+1]+(groups@common.group_drifts_hz_s)[0]
                self.assertAlmostEqual(after-before,30*slope,places=12)
        assert_array_equal(common.clock_nodes_s,[0.,30.,60.])
        assert_array_equal(extended.common.clock_knots_hz[:,[0,-1]],common.clock_knots_hz[:,[0,-1]])
        self.assertIs(extended.shift,calibration.shift)


if __name__=='__main__':unittest.main()
