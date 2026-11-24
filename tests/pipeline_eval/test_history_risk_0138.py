from pathlib import Path
import subprocess
import sys
import unittest


REPORT = Path(__file__).resolve().parents[2]/'reports/ALGO08/v3'
sys.path.insert(0, str(REPORT))
from history_risk_0138_panel import CASE, PREVIOUS, summarize


class TestHistoryRisk0138(unittest.TestCase):
    def test_saved_worker_imports_leave_installed_bootstrap_facades_unloaded(self):
        code = '''
import runpy
import sys
runpy.run_path(sys.argv[1])
import history_risk_route_trial
import prospective_0316_solver
assert not {'leo.contracts', 'leo.operations', 'leo.storage'} & sys.modules.keys()
'''
        result = subprocess.run([sys.executable, '-IB', '-c', code, str(REPORT/'history_risk_0138.py')],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sixth_pair_keeps_original_five_and_charges_admission(self):
        clock = {'elapsed_s': 3., 'cpu_s': 3.}
        stock = {'elapsed_s': 5., 'cpu_s': 5.}
        stage = dict(preflight={'elapsed_ns': 500_000_000, 'cpu_ns': 500_000_000},
                     sources={'history_risk_route.py': 'router-pin'})
        earlier = dict(case_order=list(PREVIOUS), enrolled={
            key: dict(result=dict(clock=clock, archive_stock_clock=stock), source_stage=stage) for key in PREVIOUS})
        row = dict(case=CASE, clock=clock, archive_stock_clock=stock, saved_only=True, no_waveform=True,
                   named_parity={'complete': True}, prior_named_terminal_equal=True,
                   coverage={key: {'grid_points': 179} for key in ('routed','named')},
                   binding=dict(ordinary_renderer=True, input=dict(issued=6773, portable=['pin'], sources=stage['sources'])))
        combined = summarize(earlier, row, stage, 'sealed')
        self.assertEqual(combined['case_order'], [*PREVIOUS, '0138'])
        self.assertEqual(combined['totals']['elapsed_s']['child']['routed_total_s'], 18.)
        self.assertEqual(combined['totals']['elapsed_s']['preflight_charged']['routed_total_s'], 21.)
        self.assertEqual(combined['totals']['elapsed_s']['preflight_charged']['reference_total_s'], 30.)
        row['binding']['ordinary_renderer'] = False
        with self.assertRaisesRegex(ValueError, 'separate transfer'):
            summarize(earlier, row, stage, 'sealed')


if __name__ == '__main__':
    unittest.main()
