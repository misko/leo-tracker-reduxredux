"""Owned construction checks on actual fast geometry; no position fitting."""

import copy
import unittest
from unittest.mock import patch

import numpy as np

import experiment as e


class SyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = e.context('DS24-0010')

    def test_metadata_order(self):
        self.assertEqual([row['case'] for row in e.select_cases()], ['DS24-0010', 'DS24-0011'])
        self.assertEqual(e.SITES, ((-4., 3.), (4., -3.)))
        self.assertEqual(e.SEEDS, (2026102511, 2026102512))

    def test_noiseless_forward_identity_both_c_arms(self):
        scan, node, entries, truth = e.synthesize(self.d, 0, 'noiseless_null')
        self.assertLess(truth['maximum_forward_identity_error_hz'], 1e-7)
        self.assertTrue(all(value == 0 for value in truth['actual_noise_by_ID'].values()))
        for arm in e.ARMS:
            p = e.build(self.d, scan, node, entries, arm, truth['true_phases_s'])
            closure = e.known_forward_closure(p, np.array(e.SITES[0]), truth)
            self.assertLess(closure['maximum_known_forward_mean_identity_error_hz'], 1e-7)
            self.assertLess(closure['actual_truth_residual_RMS_hz'], 1e-7)

    def test_fixed_seed_and_original_redaction(self):
        before = e.observations_digest(self.d['scan'], set(self.d['base'].members))
        first = e.synthesize(self.d, 0, 'stochastic_seed0')
        again = e.synthesize(self.d, 0, 'stochastic_seed0')
        other = e.synthesize(self.d, 0, 'stochastic_seed1')
        self.assertEqual(first[3]['observations_sha256'], again[3]['observations_sha256'])
        self.assertNotEqual(first[3]['observations_sha256'], other[3]['observations_sha256'])
        self.assertEqual(before, e.observations_digest(self.d['scan'], set(self.d['base'].members)))
        np.testing.assert_array_equal(first[3]['true_phases_s'], again[3]['true_phases_s'])

    def test_labels_IDs_and_aliases_match_in_c_arms(self):
        scan, node, entries, truth = e.synthesize(self.d, 1, 'stochastic_seed0')
        left = e.build(self.d, scan, node, entries, 'c0', truth['true_phases_s'])
        right = e.build(self.d, scan, node, entries, 'fitted_c', truth['true_phases_s'])
        np.testing.assert_array_equal(left.keep, right.keep)
        np.testing.assert_array_equal(left.values, right.values)
        self.assertEqual(left.labels, right.labels)
        self.assertEqual(left.alias, right.alias)
        self.assertEqual(len(truth['native_observation_IDs']), len(set(truth['native_observation_IDs'])))
        for p in (left, right):
            closure = e.known_forward_closure(p, np.array(e.SITES[1]), truth)
            self.assertLess(closure['maximum_known_forward_mean_identity_error_hz'], 1e-7)

    def test_four_independent_reconstructible_random_stream_bindings(self):
        scan, node, entries, truth = e.synthesize(self.d, 0, 'stochastic_seed0')
        seeds = truth['seed_children']
        self.assertEqual(len(seeds), 4)
        self.assertEqual(len(set(seeds)), 4)
        expected = np.random.default_rng(seeds[3]).gamma(2., .5,
            len(truth['noise_precision_by_track']))
        np.testing.assert_array_equal(expected,
            list(truth['noise_precision_by_track'].values()))
        if entries:
            np.testing.assert_array_equal(np.random.default_rng(seeds[2]).normal(0, 300., len(entries)),
                truth['predictive_fragment_bias_hz'])

    def test_out_of_domain_original_location_fails_without_clipping(self):
        changed = dict(self.d, means=np.asarray(self.d['means']).copy())
        changed['means'][0] = 15.01
        with self.assertRaisesRegex(ValueError, 'outside operational'):
            e.truth_components(changed, np.array(e.SITES[0]), 'noiseless_null', 0)

    def test_phase_bound_and_original_validity_remain_prerequisites(self):
        result = dict(gates=dict(tracks=[dict(compatible=True)]), linear_gates=[],
            endpoint_east_north_km=[0., 0.], final_phase_change_s=0., state=dict(phases=[0.]))
        class Problem:
            def state(self, x): return dict(phases=np.array([15.000002]))
            def calculate(self, x): return dict(final_log_precision_change=0.)
        self.assertFalse(e.final_checks(Problem(), [0., 0.], result)['passed'])


if __name__ == '__main__':
    unittest.main()
