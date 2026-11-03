import unittest
from render_leaderboard import aggregate,method_gains


class LeaderboardTests(unittest.TestCase):
    def test_score_can_improve_with_fewer_windows(self):
        rows=[dict(scan='N08',split='validation',arm='fitted-c',method=m,
                   denominator=3000,assigned=n,satellites=s,objective=n-10*s)
              for m,n,s in [('greedy',2811,25),('replacement',2811,25),('alternatives',2800,23)]]
        gains=method_gains(rows)
        self.assertEqual(gains[0]['objective_change'],0)
        self.assertEqual(gains[1]['assigned_change'],-11)
        self.assertEqual(gains[1]['satellites_change'],-2)
        self.assertEqual(gains[1]['objective_change'],9)
        for bad in (rows[:-1],rows+[rows[0]],rows[:2]+[dict(rows[2],denominator=2999)]):
            with self.assertRaises(ValueError):method_gains(bad)

    def test_rounding_cannot_turn_coverage_into_threshold_success(self):
        rows=self.fixture()
        for r in rows:r['coverage']=.899999
        for r in aggregate(rows):self.assertEqual(r['scans_at_least_90_percent'],0)

    def fixture(self):
        return [dict(scan=n,split='locked_test',method='alternatives',arm=a,coverage=.8 if n=='a' else .6,
                     satellites=20,position_error_m=100 if n=='a' else 0,
                     position_eligible=n=='a' or a=='fitted-c',boundary=False)
                for n in ('a','b') for a in ('fitted-c','zero-c')]

    def test_same_eligible_scans_in_both_rf_arms(self):
        results=aggregate(self.fixture())
        self.assertEqual(len(results),2)
        for r in results:
            self.assertEqual(r['common_eligible_scans'],['a'])
            self.assertEqual(r['paired_eligible_median_error_m'],100)
            self.assertAlmostEqual(r['equal_scan_mean_coverage'],.7)
        self.assertEqual(results[1]['position_ineligible'],1)

    def test_missing_and_duplicate_rf_rows_rejected(self):
        rows=self.fixture()
        for value in (rows[:-1],rows+[rows[0]]):
            with self.assertRaises(ValueError):aggregate(value)

    def test_pending_positions_do_not_count_as_zero(self):
        rows=self.fixture()
        for r in rows:r.update(position_error_m=None,position_eligible=None)
        for r in aggregate(rows):
            self.assertEqual(r['position_scans'],0)
            self.assertIsNone(r['paired_eligible_median_error_m'])
            self.assertIsNone(r['descriptive_all_result_median_distance_m'])
