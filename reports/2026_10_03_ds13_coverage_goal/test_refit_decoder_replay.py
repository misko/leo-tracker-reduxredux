import unittest
from refit_decoder_replay import inputs


class RefitReplayTests(unittest.TestCase):
    def fixtures(self):
        original=dict(original_train_rows=[0],original_test_rows=[1],arms={})
        refit=dict(original_train_rows=[0],original_test_rows=[1],arms={})
        for arm in ('fitted-c','zero-c'):
            original['arms'][arm]=dict(chosen_modes=[dict(catalog_number=12,satellite_index=0,total_timing_s=2.,offset_s=1.5,segments=['stale'])])
            refit['arms'][arm]=dict(catalog_numbers=[12],parameters=[0]*6+[3.],coefficient=[0.])
        return original,refit

    def test_updates_timing_and_removes_stale_segments(self):
        old,new=self.fixtures();r=inputs(old,new);m=r['arms']['fitted-c']['chosen_modes'][0]
        self.assertEqual(m['total_timing_s'],3.);self.assertEqual(m['offset_s'],2.5)
        self.assertNotIn('segments',m);self.assertIn('segments',old['arms']['fitted-c']['chosen_modes'][0])

    def test_changed_rows_or_identities_rejected(self):
        old,new=self.fixtures();new['original_test_rows']=[2]
        with self.assertRaises(ValueError):inputs(old,new)
        old,new=self.fixtures();new['arms']['fitted-c']['catalog_numbers']=[13]
        with self.assertRaises(ValueError):inputs(old,new)


if __name__=='__main__':unittest.main()
