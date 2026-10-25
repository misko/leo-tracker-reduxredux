"""Generating interventions and factorial bookkeeping, no position fits."""
import unittest
import numpy as np
import factorial as f


class FactorialTests(unittest.TestCase):
    def common(self):
        return dict(coordinate_widths=[2, 3, 2, 6, 2], selected_coefficients=np.arange(15.) + 1,
            true_phases_s=np.array([1., -2.]), original_phase_locations_s=np.array([.1, .2]),
            observations_sha256='old', actual_noise_by_ID={'a':3.}, noise_sigma_by_ID={'a':4.},
            noise_precision_by_track={3:.5}, seed_children=[1,2,3,4], predictive_fragment_bias_hz=[17.],
            inference_model={'nu':3}, inference_powers=[1.])

    def test_phase_only_preserves_all_coefficients_and_noise(self):
        c = self.common(); t = f.changed_truth(c, 'phase_at_causal_mean')
        np.testing.assert_array_equal(t['true_phases_s'], [.1, .2])
        np.testing.assert_array_equal(t['selected_coefficients'], c['selected_coefficients'])
        self.assertEqual(t['preserved_draw_sha256']['actual_noise_by_ID'], f.fingerprint(c['actual_noise_by_ID']))

    def test_shape_only_preserves_nonlinear_phase_and_other_blocks(self):
        c = self.common(); t = f.changed_truth(c, 'shape_zero')
        np.testing.assert_array_equal(t['true_phases_s'], c['true_phases_s'])
        np.testing.assert_array_equal(t['selected_coefficients'][7:13], 0.)
        np.testing.assert_array_equal(t['selected_coefficients'][:7], c['selected_coefficients'][:7])
        np.testing.assert_array_equal(t['selected_coefficients'][13:], c['selected_coefficients'][13:])

    def test_original_draws_are_immutable(self):
        c = self.common(); before = f.fingerprint(c)
        for method in f.INTERVENTIONS: f.changed_truth(c, method)
        self.assertEqual(f.fingerprint(c), before)

    def test_unknown_cell_is_rejected(self):
        with self.assertRaises(ValueError): f.changed_truth(self.common(), 'known_phase_inference')

    def test_vector_contrast_detects_interaction_and_reconstructs_total(self):
        from summarize import contrasts
        g = {'00':np.array([1.,2.]), '01':np.array([3.,4.]), '10':np.array([6.,8.]), '11':np.array([10.,15.])}
        c = contrasts(g)
        np.testing.assert_array_equal(c['interaction'], [2.,5.])
        np.testing.assert_array_equal(c['marginal_phase_removal'] + c['marginal_shape_removal'], g['00'] - g['11'])

    def test_missing_cell_never_imputes_a_contrast(self):
        from summarize import contrasts
        with self.assertRaises(KeyError): contrasts({'00':1., '01':2., '11':3.})


if __name__ == '__main__': unittest.main()
