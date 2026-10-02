import copy
import unittest
from export_quality_overlay_hypotheses import bind


class BindingTests(unittest.TestCase):
    def fixture(self):
        header = dict(session_id='s', manifest_sha256='m', analysis_manifest_sha256='a', start_utc_ns=100)
        frozen = dict(header, tracks=[dict(track_id='t', times_s=[1.], measured_hz=[20.],
            visits=[3], receiver_id=0, channel=2, rf_hz=1000)])
        projected = dict(header, tracks=[dict(track_id='t', points=[dict(candidate_id='c',
            support_center_utc_ns=1000000100, measured_cfo_hz=19., normalized_dealiased_cfo_hz=20., visit_index=3,
            receiver_id=0, channel=2, actual_rf_hz=1000)])])
        return frozen, projected

    def test_exact_join(self):
        a,b = self.fixture()
        self.assertEqual(bind(a,b)['matched_samples'], 1)

    def test_reject_corruption(self):
        a,b = self.fixture()
        for field in ('normalized_dealiased_cfo_hz', 'support_center_utc_ns', 'visit_index', 'receiver_id', 'actual_rf_hz'):
            bad = copy.deepcopy(b)
            bad['tracks'][0]['points'][0][field] += 1
            with self.assertRaises(ValueError): bind(a,bad)
        for field in ('session_id', 'manifest_sha256', 'analysis_manifest_sha256'):
            bad = copy.deepcopy(b); bad[field] = 'wrong'
            with self.assertRaises(ValueError): bind(a,bad)

    def test_reject_missing_duplicate(self):
        a,b = self.fixture()
        bad = copy.deepcopy(b); bad['tracks'] = []
        with self.assertRaises(ValueError): bind(a,bad)
        b['tracks'] *= 2
        with self.assertRaises(ValueError): bind(a,b)

    def test_preserve_overlap_between_hypotheses(self):
        a,b = self.fixture()
        a['tracks'].append(dict(a['tracks'][0],track_id='other'))
        b['tracks'].append(dict(b['tracks'][0],track_id='other'))
        result = bind(a,b)
        self.assertEqual(result['matched_samples'],2)
        self.assertEqual(result['unique_candidates'],1)


if __name__ == '__main__': unittest.main()
