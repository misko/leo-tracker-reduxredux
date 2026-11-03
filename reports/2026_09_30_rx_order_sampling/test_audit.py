import unittest
from audit import endpoint


class EndpointTests(unittest.TestCase):
    def test_missing_opportunities_do_not_become_nondetections(self):
        rows = [dict(prediction_utc_ns=t, status=s) for t, s in
                [(0, 'no_matching_candidate'), (9, 'out_of_scope'), (10, 'unique_hit')]]
        result = endpoint(rows, 10)
        self.assertEqual(result['previous_opportunity_ns'], 0)
        self.assertEqual(result['gap_s'], 1e-8)

    def test_wrong_frozen_endpoint_rejected(self):
        with self.assertRaises(AssertionError):
            endpoint([dict(prediction_utc_ns=10, status='unique_hit')], 11)

    def test_ambiguity_preserved(self):
        rows = [dict(prediction_utc_ns=t, status=s) for t, s in
                [(0, 'ambiguous_candidate'), (10, 'unique_hit'), (20, 'no_matching_candidate')]]
        result = endpoint(rows, 10)
        self.assertEqual(result['previous_status'], 'ambiguous_candidate')
        self.assertEqual(result['post_first_counts']['no_matching_candidate'], 1)
