import unittest
from raw_partner_audit import census


class PartnerTests(unittest.TestCase):
    def test_reused_track_candidates_count_once(self):
        a=dict(projected_candidate_id='a',integer_epoch_sample=10,fractional_epoch_offset_samples=0.,passed_fractional_margin_gate=True)
        b=dict(a,projected_candidate_id='b')
        doc=dict(tracks=[dict(candidate_ids=['a']),dict(candidate_ids=['a'])],opportunities=[dict(source_window=dict(sample_rate_hz=5000000),receivers=dict(rx0=dict(candidates=[a]),rx1=dict(candidates=[b])))])
        result=census(doc,.03)
        self.assertEqual(result['unique_retained_candidate_counts'],{'raw_only_timing_partner':1})
        doc['tracks'].append(dict(candidate_ids=['b']))
        self.assertEqual(census(doc,.03)['unique_retained_candidate_counts'],{'retained_timing_partner':2})
