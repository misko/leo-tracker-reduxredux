import importlib.util
import unittest
import tempfile
import json
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

    def test_failed_baseline_candidate_is_report_only_not_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'baseline.json').write_text(json.dumps({'status':'failed','protocol_sha256':'frozen'}))
            phases,hashes=report.load_phases(root,'frozen')
            self.assertEqual(phases['candidate']['status'],'not-run-baseline-failed')
            self.assertTrue(phases['candidate']['report_only'])
            self.assertNotIn('candidate',hashes)
            self.assertFalse((root/'candidate.json').exists())

    def test_complete_baseline_missing_candidate_remains_pending(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'baseline.json').write_text(json.dumps({'status':'complete','protocol_sha256':'frozen'}))
            with self.assertRaises(RuntimeError):report.load_phases(root,'frozen')

    def test_solver_success_does_not_hide_unqualified_regional_attempt(self):
        member=dict(label='synthetic',session_id='synthetic',source_version='hard60')
        candidate=dict(status='complete',regions={'direct105:test':dict(
            recovery={'result':{'status':'qualified'}},finals=[dict(
                arm='fitted-c',start='association',reason=None,
                fit=dict(converged=False,stationarity=.02,stop_reason='nonstationary-solver-status-0'))])})
        row=report.comparison(member,{'status':'complete'},candidate,{})
        attempt=row['recovered_regions'][0]['finals'][0]
        self.assertFalse(attempt['qualified'])
        self.assertEqual(attempt['stop_reason'],'nonstationary-solver-status-0')


if __name__=='__main__':unittest.main()
