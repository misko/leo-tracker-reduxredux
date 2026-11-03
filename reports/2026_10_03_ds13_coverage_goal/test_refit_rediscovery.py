import unittest
from refit_rediscovery import calibration_input


class RediscoveryInputTests(unittest.TestCase):
    def test_arm_specific_refit_and_convergence_preserved(self):
        refit=dict(original_train_rows=[1],original_test_rows=[2],arms={'zero-c':dict(catalog_numbers=[12],parameters=[0]*7,coefficient=[0.],attempts=[dict(success=False)])})
        r=calibration_input(refit,'zero-c')
        self.assertEqual(r['catalog_numbers'],[12]);self.assertEqual(set(r['arms']),{'zero-c'})
        self.assertEqual(r['arms']['zero-c']['rf_coefficient_hz_per_ghz'],[0.])
        self.assertFalse(r['arms']['zero-c']['attempts'][-1]['success'])


if __name__=='__main__':unittest.main()
