"""Classification checks preserve ACF and all other original primitives."""
import unittest
import audit


class ClassificationTests(unittest.TestCase):
    def test_acf_alone_is_distinct_from_multiple_failures(self):
        self.assertEqual(audit.category(dict(profile_lag1_acf=False, RMS=True)), 'ACF_only')
        self.assertEqual(audit.category(dict(profile_lag1_acf=False, RMS=False)), 'ACF_and_other')
        self.assertEqual(audit.category(dict(profile_lag1_acf=True, RMS=False)), 'other_only')
        self.assertEqual(audit.category(dict(profile_lag1_acf=True, RMS=True)), 'all_observed_primitive_checks_pass')

    def test_original_sample_size_bound_and_no_amplitude_waiver(self):
        diagnostics = dict(mean_z=0., slope_z=0., quadratic_bic_gain=0., maximum_step_z=0., lag1_acf=.5)
        self.assertTrue(audit.flags(diagnostics, 16)['lag1_acf'])
        self.assertFalse(audit.flags(diagnostics, 100)['lag1_acf'])
        self.assertEqual(audit.category(audit.flags(diagnostics, 100)), 'ACF_only')


if __name__ == '__main__': unittest.main()
