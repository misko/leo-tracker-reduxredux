import copy
import importlib.util
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch
import numpy as np
from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score
import timing_search as timing
import adapter


def packet():
    return dict(owner_id='math-unit-owner',target_support=dict(start_counter=3540000,stop_counter=3740000),
        modes=[dict(mode_id='m0',epoch_samples=4321.25,cfo_hz=213456.75,cfo_rate_hz_s=0.,
            reference_offset_s=.01,cfo_half_width_hz=2000.,donors=[dict(observation_id='earlier',
            support=dict(start_counter=0,stop_counter=200000))])])


class TimingTests(unittest.TestCase):
    def test_all_frame_owned_math_matches_public_scorer(self):
        rng=np.random.default_rng(444);z=(rng.normal(size=200000)+1j*rng.normal(size=200000))/np.sqrt(2)
        for edge in ['lower','upper']:
            for epoch in [0.,4321.25,13250.7]:
                p=packet();mode=p['modes'][0];mode['epoch_samples']=epoch
                ownership=timing.partition(len(z),10_000_000,epoch,p['owner_id'])
                own=timing.scores(z,10_000_000,edge,mode,[0],ownership,'all')[0]
                public=conditioned_glrt64_score(z,10_000_000,epoch_sample=int(epoch),
                    fractional_epoch_offset_samples=epoch-int(epoch),acquired_cfo_hz=mode['cfo_hz'],edge=edge)
                self.assertAlmostEqual(own['exact_score'],public.exact_score,places=11)
                self.assertAlmostEqual(own['control_score'],public.control_score,places=11)
                self.assertAlmostEqual(own['tracking_cfo_hz'],public.tracking_cfo_hz,places=5)

    def test_entire_timing_and_mode_bank_has_disjoint_native_ownership(self):
        rate=10_000_000;ownership=timing.partition(200000,rate,4321.25,'ownership-test')
        search=[];confirm=[]
        for epoch in [4321.25,35.8,13250.3,8000.6]:
            for offset in timing.COARSE:
                for group,rows in [('search',search),('confirmation',confirm)]:
                    rows.extend(timing.geometry(200000,rate,(epoch+offset)%(rate/750),ownership,group))
        for a in search:
            self.assertTrue(all(a['sample_stop']<=b['sample_start'] or b['sample_stop']<=a['sample_start'] for b in confirm))

    def test_confirmation_values_do_not_change_selection_receipt(self):
        rng=np.random.default_rng(445);z=rng.normal(size=200000)+1j*rng.normal(size=200000)
        p=packet();ownership=timing.partition(len(z),10_000_000,p['modes'][0]['epoch_samples'],p['owner_id'])
        changed=z.copy()
        for i in ownership['intervals']:
            if i['group']=='confirmation':changed[i['start']:i['stop']]*=73*np.exp(.71j)
        receipts=[]
        a=timing.score_target(z,10_000_000,'lower',p,receipts.append)
        b=timing.score_target(changed,10_000_000,'lower',p,receipts.append)
        self.assertEqual(a['selection_receipt'],b['selection_receipt'])
        self.assertEqual(len(receipts),2);self.assertFalse(receipts[0]['confirmation_accessed'])
        self.assertLessEqual(max(abs(x['score']['offset_samples']) for x in a['exposure']),256)

    def test_absence_and_overlapping_donor_fail_closed(self):
        p=packet();p['modes']=[]
        self.assertEqual(timing.score_target(np.zeros(200000),10_000_000,'lower',p)['status'],'no_donor')
        p=packet();p['modes'][0]['donors'][0]['support']['stop_counter']=3540001
        with self.assertRaisesRegex(ValueError,'overlaps'):
            timing.score_target(np.zeros(200000),10_000_000,'lower',p)

    def test_prediction_reference_mapping_and_response_redaction(self):
        path=Path(__file__).parents[1]/'prediction/example_packet.json';row=json.loads(path.read_text())
        a=adapter.adapt(row);row['target_original']={'winner':-999999}
        self.assertEqual(a,adapter.adapt(row))
        m=a['modes'][0];f=row['forecast']['modes'][0]['full']
        self.assertAlmostEqual(m['epoch_samples'],f['epoch_samples']+f['timing_rate_samples_per_s']*.01)
        self.assertEqual(m['reference_offset_s'],.01)
        self.assertEqual(m['cfo_hz'],f['CFO_hz'])
        self.assertFalse(m['donors'][0]['support']['native_generation_verified'])

    def test_broad_CFO_is_distinct_from_continuity(self):
        mode=packet()['modes'][0]
        a=dict(status='complete',margin=.1,tracking_cfo_hz=mode['cfo_hz']+30000)
        verdict=timing.confirmed(a,mode,a)
        self.assertTrue(verdict['pilot_confirmed']);self.assertFalse(verdict['continuity_compatible'])
        self.assertFalse(verdict['admitted'])

    def test_search_margin_is_diagnostic_not_a_second_confirmation_gate(self):
        mode=packet()['modes'][0]
        confirmation=dict(status='complete',margin=.026,tracking_cfo_hz=mode['cfo_hz'])
        nomination=dict(status='complete',margin=.001,tracking_cfo_hz=mode['cfo_hz'])
        verdict=timing.confirmed(confirmation,mode,nomination)
        self.assertFalse(verdict['search_passed_gate']);self.assertTrue(verdict['admitted'])

    def test_point_selects_best_zero_across_same_modes(self):
        p=packet();p['modes'].append(copy.deepcopy(p['modes'][0]));p['modes'][1]['mode_id']='m1'
        def fake(samples,rate,edge,mode,offsets,ownership,group,cache=None):
            out=[]
            for offset in offsets:
                margin=.08 if mode['mode_id']=='m1' and offset==0 else .1 if mode['mode_id']=='m0' and offset==96 else .01
                out.append(dict(status='complete',offset_samples=int(offset),epoch_samples=4321.25+int(offset),
                    frames=7,margin=margin,tracking_cfo_hz=mode['cfo_hz']))
            return out
        with patch.object(timing,'scores',fake):
            r=timing.score_target(np.zeros(200000),10_000_000,'lower',p)
        self.assertEqual(r['point']['selected']['mode_id'],'m1')
        self.assertEqual(r['point']['selected']['score']['offset_samples'],0)
        self.assertEqual(r['search']['selected']['mode_id'],'m0')


if __name__=='__main__':unittest.main(verbosity=2)
