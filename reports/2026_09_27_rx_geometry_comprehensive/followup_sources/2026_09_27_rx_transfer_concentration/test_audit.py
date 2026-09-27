import copy
import unittest
from audit import describe, summarize, audit


def row():
    posterior = {'candidate_ids': [1, 2], 'probabilities': [.5, .5], 'map_candidate_id': 1}
    return {'session_id': 's', 'track_id': 't', 'direction': 'A_to_B', 'candidate_ids': [1,2],
            'weight_seconds': 2, 'held_count': 1, 'held_frequency_log_likelihood': [-1., -2.],
            'normal': {'baseline_mean_nll': 1.4, 'reception_mean_nll': 1.3,
                       'improvement_baseline_minus_reception': .1,
                       'baseline_conditioning_posterior': posterior,
                       'reception_conditioning_posterior': copy.deepcopy(posterior)}}


class Tests(unittest.TestCase):
    def test_ceiling_and_weight(self):
        r = describe(row())
        self.assertAlmostEqual(r['held_oracle_gain'], .4)
        self.assertEqual(r['total_variation'], 0)
        self.assertAlmostEqual(summarize([r], 4)['contribution_to_full_gain'], .05)

    def test_reject_gain_mismatch(self):
        r = row(); r['normal']['reception_mean_nll'] = 2
        with self.assertRaises(ValueError): describe(r)

    def test_reject_better_than_oracle(self):
        r = row(); r['normal']['reception_mean_nll'] = .5
        r['normal']['improvement_baseline_minus_reception'] = .9
        with self.assertRaises(ValueError): describe(r)

    def test_reject_duplicates(self):
        with self.assertRaises(ValueError): audit([row(), row()])

    def test_empty_partition(self):
        self.assertIsNone(summarize([], 1)['weighted_gain'])
        self.assertEqual(summarize([], 1)['contribution_to_full_gain'], 0)


if __name__ == '__main__': unittest.main()
