import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('pilot_report',Path(__file__).with_name('report.py'))
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)


class ReportTest(unittest.TestCase):
    def rows(self):
        return [dict(label=str(i),baseline_status='complete',candidate_status='complete',arms={a:dict(baseline={'error_km':i+1},candidate={'error_km':i+.5},error_delta_km=-.5) for a in report.ARMS}) for i in range(5)]

    def test_complete_pilot_metrics(self):
        result=report.aggregate(self.rows())['fitted-c']
        self.assertEqual(result['matched_complete'],5)
        self.assertEqual(result['baseline']['mean_km'],3)
        self.assertEqual(result['candidate']['mean_km'],2.5)
        self.assertEqual(result['regressions'],[])

    def test_failed_member_not_excluded(self):
        rows=self.rows();rows[0]['candidate_status']='failed'
        result=report.aggregate(rows)['fitted-c']
        self.assertEqual(result['full_membership'],5)
        self.assertEqual(result['failures_or_missing'],1)
        self.assertTrue(result['full_pilot_metrics_withheld'])
        self.assertNotIn('candidate',result)

    def test_regression_is_reported(self):
        rows=self.rows();rows[2]['arms']['zero-c']['error_delta_km']=2
        self.assertEqual(report.aggregate(rows)['zero-c']['regressions'],[{'label':'2','delta_km':2}])


if __name__=='__main__':unittest.main()
