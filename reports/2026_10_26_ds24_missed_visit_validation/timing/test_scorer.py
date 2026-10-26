import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
import scorer
import reader


def packet():
    point=dict(epoch_samples=4321.25,cfo_hz=213456.75,cfo_rate_hz_s=0.,reference_offset_s=.01,
        cfo_half_width_hz=4500.,timing_reference_offset_s=.01,timing_rate_samples_s=100.)
    return dict(header=dict(source_id='unit-source',receiver_id=0,sample_rate_hz=10_000_000),
        prediction_id='unit',target_support=dict(start_counter=3540000,stop_counter=3740000),
        status='linear_fallback',primary_hypothesis_id='earlier/m0',
        donors=[dict(start_counter=0,stop_counter=200000)],
        methods={name:copy.deepcopy(point) for name in scorer.METHODS})


class FullWindowTests(unittest.TestCase):
    def test_no_donor_is_explicit(self):
        p=packet();p.update(status='no_donor',methods={},donors=[])
        r=scorer.score_packet(np.zeros(200000),10_000_000,'lower',p)
        self.assertEqual(r['methods'],{});self.assertEqual(r['independent_added_Doppler_points'],0)

    def test_points_are_passed_directly_and_identical_controls_are_not_rescored(self):
        p=packet();captured=[]
        def fake(z,rate,edge,point,offsets,ownership,group,cache):
            captured.append(point['epoch_samples'])
            return [dict(status='complete',margin=.1,tracking_cfo_hz=point['cfo_hz']+2*scorer.BIN_HZ)]
        with patch.object(scorer.math,'scores',fake):r=scorer.score_packet(np.zeros(200000),10_000_000,'lower',p)
        self.assertEqual(captured,[4321.25]);self.assertEqual(r['distinct_fullwindow_scores'],1)
        self.assertAlmostEqual(r['methods']['linear']['frequency_innovation_hz'],2*scorer.BIN_HZ)

    def test_a_passing_control_cannot_rescue_operational_quadratic(self):
        p=packet();p['methods']['quadratic_or_fallback']['epoch_samples']+=5
        def fake(z,rate,edge,point,offsets,ownership,group,cache):
            return [dict(status='complete',margin=.1 if point['epoch_samples']==4321.25 else .001,tracking_cfo_hz=point['cfo_hz'])]
        with patch.object(scorer.math,'scores',fake):r=scorer.score_packet(np.zeros(200000),10_000_000,'lower',p)
        self.assertTrue(r['methods']['linear']['admitted']);self.assertFalse(r['operational_admitted'])

    def test_fullwindow_zero_rate_matches_public_frequency_and_scores(self):
        rng=np.random.default_rng(610);z=rng.normal(size=200000)+1j*rng.normal(size=200000)
        for edge in ['lower','upper']:
            r=scorer.score_packet(z,10_000_000,edge,packet())['methods']['linear']['score']
            p=conditioned_glrt64_score(z,10_000_000,epoch_sample=4321,fractional_epoch_offset_samples=.25,acquired_cfo_hz=213456.75,edge=edge)
            self.assertAlmostEqual(r['margin'],p.margin,places=11)
            self.assertAlmostEqual(r['tracking_cfo_hz'],p.tracking_cfo_hz,places=5)

    def test_fabricated_predictor_interface_has_no_extra_midpoint_advance(self):
        row=json.loads((Path(__file__).parents[1]/'prediction/example_packet.json').read_text())['rows'][0]
        self.assertIn('methods',row)
        captured=[]
        def fake(z,rate,edge,point,offsets,ownership,group,cache):
            captured.append(point['epoch_samples'])
            return [dict(status='complete',margin=.1,tracking_cfo_hz=point['cfo_hz'])]
        with patch.object(scorer.math,'scores',fake):r=scorer.score_packet(np.zeros(200000),10_000_000,'lower',row)
        self.assertEqual(r['methods']['linear']['point']['epoch_samples'],row['methods']['linear']['epoch_samples'])
        self.assertEqual(r['methods']['legacy_adapter_linear']['point']['epoch_samples'],row['methods']['legacy_adapter_linear']['epoch_samples'])

    def test_reader_reuses_parity_but_still_exhausts_current_native_source(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'index';path.write_bytes(b'public-index-unit')
            acquisition=dict(sample_start=1,sample_end=11,generation=2);target=dict(channel=5)
            window=SimpleNamespace(iq_sha256='iq',acquisition=acquisition,target=target,sample_rate_hz=10_000_000,samples=np.zeros((10,2,2)))
            authority=dict(index_path=str(path),index_sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest(),
                index=dict(iq_sha256='iq',acquisition=acquisition),target=target,sample_rate_hz=10_000_000,
                segment={},local_sequence=0)
            finished=[]
            def windows():yield window;finished.append(True)
            port=SimpleNamespace(windows=windows,receiver_ids=(0,1))
            prior=dict(request_id='unit',status='complete',public_source_parity=dict(full_reader_exhausted=True,IQ_sha256='iq',parity={'0':{'all_passed':True},'1':{'all_passed':True}}))
            with patch('leo.storage.fast_scan.FastSegmentSource',return_value=port):
                w,ids,values,receipt=reader.open_verified(dict(request_id='unit',raw_authority=authority),prior)
            self.assertEqual(finished,[True]);self.assertEqual(receipt['repeated_blind_acquisition_calls'],0)
            self.assertTrue(receipt['round1_paired_candidate_parity_reused'])

    def test_control_carrier_and_counter_reference_are_target_midpoint(self):
        import study
        a=study.generate_wave('lower',213456.75,0.,100.,8.)
        b=study.generate_wave('lower',213456.75,2000.,100.,8.)
        dt=np.arange(200000)/10_000_000-.01
        np.testing.assert_allclose(b,a*np.exp(1j*np.pi*2000*dt*dt),atol=1e-10)
        p=study.control_packet('unit','lower',2000.,750.,.5)
        ref=p['truth_reference_metadata']
        self.assertEqual(ref['target_reference_counter']-ref['earlier_reference_counter'],3540000)
        self.assertEqual(ref['reference_gap_seconds'],.354)
        self.assertAlmostEqual(p['methods']['linear']['cfo_hz']-750.,213456.75+2000*.354)


if __name__=='__main__':unittest.main(verbosity=2)
