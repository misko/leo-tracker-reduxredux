import unittest
from audit_peak_provenance import pair_metadata, distance


class ProvenanceTests(unittest.TestCase):
    def test_circular_epoch_and_frequency(self):
        self.assertAlmostEqual(distance(999.9, .1, 1000), .2)
        a = dict(probe_key=[1, 0, 2], tracking_cfo_hz=10., fractional_epoch_samples=999.9,
                 integer_epoch_sample=1000, candidate_rank=1, residual_class='zero',
                 candidate_id='a', fractional_margin=.7)
        b = dict(a, fractional_epoch_samples=.1, candidate_id='b', candidate_rank=2)
        result = pair_metadata(a, b, 1000)
        self.assertAlmostEqual(result['frame_epoch_distance_samples'], .2)
        self.assertFalse(result['same_candidate_rank'])
        self.assertEqual(result['candidate_ids'], ['a', 'b'])
        self.assertEqual(a['candidate_id'], 'a')

    def test_cross_probe_rejected(self):
        with self.assertRaises(ValueError):
            pair_metadata({'probe_key':[1]}, {'probe_key':[2]}, 1000)
