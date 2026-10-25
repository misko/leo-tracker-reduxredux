"""Control-flow checks for bounded research execution, without RF or fits."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('panel_runner', Path(__file__).with_name('runner.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class BoundedExecution(unittest.TestCase):
    def test_existing_result_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'result.json'
            runner.write_new(p, {'value': 1})
            before = p.read_bytes()
            with self.assertRaises(FileExistsError):
                runner.write_new(p, {'value': 2})
            self.assertEqual(before, p.read_bytes())

    def test_expired_budget_does_not_launch(self):
        with patch.object(runner.subprocess, 'Popen') as launch:
            with self.assertRaises(TimeoutError):
                runner.run_command(['unused'], 'unused.log', 0)
            launch.assert_not_called()

    def test_preflight_must_bind_current_protocol(self):
        with patch.object(runner, 'protocol', return_value={}), patch.object(runner, 'read', return_value={'all_passed': True, 'protocol_sha256': 'old'}), patch.object(runner, 'digest', return_value='new'), patch.object(runner, 'write_new') as write:
            with self.assertRaises(ValueError):
                runner.run()
            write.assert_not_called()

    def test_unqualified_preparation_stops_and_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def command(cmd, log, seconds):
                if '--stage' in cmd and cmd[-1] == 'prepare':
                    runner.write_new(root / 'P1/prepared.json', {'status': 'no_active_curvature'})
                return 0
            with patch.object(runner, 'ROOT', root), patch.object(runner, 'protocol', return_value={'per_case_seconds': 5}), patch.object(runner, 'run_command', side_effect=command) as run:
                result = runner.one('P1', time.monotonic() + 10)
            self.assertEqual(result['status'], 'input_unqualified')
            self.assertEqual(run.call_count, 2)
            self.assertEqual(json.loads((root / 'P1/execution.json').read_text()), result)

    def test_stage_timeout_is_recorded_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(runner, 'ROOT', root), patch.object(runner, 'protocol', return_value={'per_case_seconds': 5}), patch.object(runner, 'run_command', side_effect=subprocess.TimeoutExpired('stage', .01)) as run:
                result = runner.one('P1', time.monotonic() + 10)
            self.assertEqual(result['status'], 'execution_failed')
            self.assertEqual(run.call_count, 1)
            self.assertIn('TimeoutExpired', result['stages'][0]['error'])

    def test_live_timeout_terminates_only_child_group(self):
        with tempfile.TemporaryDirectory() as directory:
            # The real unprivileged process-group kill is exercised; the
            # elevated fallback is unnecessary for this synthetic child.
            with patch.object(runner.subprocess, 'run') as fallback:
                with self.assertRaises(subprocess.TimeoutExpired):
                    runner.run_command([sys.executable, '-c', 'import time; time.sleep(5)'],
                                       Path(directory) / 'child.log', .05)
                self.assertEqual(fallback.call_args.args[0][:4], ['sudo', '-n', 'kill', '-KILL'])


if __name__ == '__main__':
    unittest.main()
