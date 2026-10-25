"""Component transformations and serialization; real geometry checks in preparation."""
import unittest
import numpy as np
import components as c


class ComponentTests(unittest.TestCase):
    def common(self):
        return dict(coordinate_widths=[2, 3, 2, 6, 2], selected_coefficients=np.arange(15, dtype=float) + 1,
            true_phases_s=np.array([1., -2.]), original_phase_locations_s=np.array([.1, .2]),
            observations_sha256='control', actual_noise_by_ID={'a':3.}, noise_sigma_by_ID={'a':4.},
            noise_precision_by_track={3:.5}, seed_children=[1,2,3,4], predictive_fragment_bias_hz=[17.],
            inference_model={'nu':3}, inference_powers=[1.])

    def test_orbital_intervention_preserves_receiver_and_source_constants(self):
        common = self.common(); truth = c.changed_truth(common, 'no_orbital_deviations')
        np.testing.assert_array_equal(truth['true_phases_s'], common['original_phase_locations_s'])
        np.testing.assert_array_equal(truth['selected_coefficients'][7:13], 0.)
        np.testing.assert_array_equal(truth['selected_coefficients'][:7], common['selected_coefficients'][:7])
        np.testing.assert_array_equal(truth['selected_coefficients'][-2:], common['selected_coefficients'][-2:])

    def test_receiver_intervention_preserves_phase_shape_and_source_constants(self):
        common = self.common(); truth = c.changed_truth(common, 'no_receiver_deviations')
        np.testing.assert_array_equal(truth['selected_coefficients'][:5], 0.)
        np.testing.assert_array_equal(truth['selected_coefficients'][5:], common['selected_coefficients'][5:])
        np.testing.assert_array_equal(truth['true_phases_s'], common['true_phases_s'])
        self.assertEqual(c.fingerprint(truth['actual_noise_by_ID']), c.fingerprint(common['actual_noise_by_ID']))

    def test_common_random_draws_are_not_mutated(self):
        common = self.common(); before = c.fingerprint(common)
        for intervention in c.INTERVENTIONS: c.changed_truth(common, intervention)
        self.assertEqual(before, c.fingerprint(common))

    def test_saved_json_and_reconstructed_arrays_have_same_fingerprint(self):
        self.assertEqual(c.fingerprint({3:np.array([1., 2.])}), c.fingerprint({'3':[1., 2.]}))


if __name__ == '__main__': unittest.main()
