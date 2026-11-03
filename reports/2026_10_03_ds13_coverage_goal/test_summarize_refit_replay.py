import unittest
from summarize_refit_replay import changes


class ReplaySummaryTests(unittest.TestCase):
    def test_identity_change_not_counted_as_matched_point(self):
        before=[dict(row_index=0,catalog_number=1,residual_native_hz=10),dict(row_index=1,catalog_number=2,residual_native_hz=20)]
        after=[dict(row_index=0,catalog_number=3,residual_native_hz=0),dict(row_index=1,catalog_number=2,residual_native_hz=5)]
        r=changes(before,after)
        self.assertEqual(r['unchanged_peak_identity'],1);self.assertEqual(r['added_peak_identity'],1)
        self.assertEqual(r['removed_peak_identity'],1);self.assertEqual(r['matched_before_rms_hz'],20)
        self.assertEqual(r['matched_after_rms_hz'],5)


if __name__=='__main__':unittest.main()
