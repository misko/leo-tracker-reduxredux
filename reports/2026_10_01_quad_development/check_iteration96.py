"""Cold cap-only pilot with successful controls preceding unresolved singles."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys

from run_window import prepare_window
from regression_batch import digest, execute, verify_sources
from screen_seed_prefix import sealed
from failure_composition_checks import process_ok
from iteration96_checks import compare

HERE = Path(__file__).resolve().parent
CONTROLS = ('DS9-B01-S1', 'DS10-B01-S1', 'DS11-B01-S1')
FAILURES = ('DS9-B05-S2', 'DS9-B05-S3', 'DS11-B04-S1')


def parent_path(unit):
    campaign = 'one-start-blas-cold-v1' if unit in CONTROLS else 'failure-composition-cold-v1'
    return HERE/campaign/unit/'blas'/(unit+'.json')


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('unit', choices=CONTROLS+FAILURES)
    args = parser.parse_args()
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        parent_file = parent_path(args.unit)
        parent = sealed(parent_file)
        assert parent['best']['converged'] == (args.unit in CONTROLS)
        frozen = sealed(parent_file.parent/'sources.json')
        sources, inputs = dict(frozen['source_sha256']), dict(frozen['inputs'])
        verify_sources(parent['source_sha256']); verify_sources(parent['inputs'])
        for filename in ('sources.json', 'evaluation.json', args.unit+'.launch.json', 'audit-launch.json'):
            path = parent_file.parent/filename
            value = sealed(path); inputs[str(path)] = digest(path)
            if filename == 'evaluation.json':
                assert len(value['rows']) == 1 and value['rows'][0]['accepted'] == (args.unit in CONTROLS)
                assert value['rows'][0]['receipt_sha256'] == digest(parent_file)
            if filename.endswith('launch.json'):
                assert process_ok(value)
        inputs[str(parent_file)] = digest(parent_file)
        summary_path = HERE/'failure-composition-summary-v1.json'
        summary = sealed(summary_path)
        assert {r['unit'] for r in summary['rows']} == set(FAILURES)
        assert all(r['failure_preserved'] for r in summary['rows'])
        for key in ('sources', 'inputs', 'frozen_sources_and_inputs'):
            verify_sources(summary[key])
        inputs[str(summary_path)] = digest(summary_path)
        if args.unit in FAILURES:
            for unit in CONTROLS:
                path = HERE/'iteration96-v1'/unit/'comparison.json'
                gate = sealed(path)
                assert gate['unit'] == unit and gate['policy_equivalent'] and gate['accepted']
                gate_freeze = sealed(path.parent/'sources.json')
                verify_sources(gate_freeze['source_sha256']); verify_sources(gate_freeze['inputs'])
                inputs[str(path)] = digest(path)
        binding, scans, _, _, _ = prepare_window(args.unit)
        assert binding == parent['binding']
        for _, height, _ in scans:
            inputs[height.input_bindings['grid_path']] = height.input_bindings['grid_sha256']
        for name in ('check_iteration96.py', 'run_seed_limit_96.py', 'run_one_start_blas_96.py',
                     'iteration96_checks.py', 'failure_composition_checks.py', 'test_iteration96_checks.py',
                     'test_iteration96_worker.py', 'ITERATION96_PLAN.md', 'evaluate_variant.py', 'evaluate_pilot.py'):
            sources[str(HERE/name)] = digest(HERE/name)
        verify_sources(sources); verify_sources(inputs)
        directory = HERE/'iteration96-v1'/args.unit
        directory.mkdir(parents=True, exist_ok=False)
        freeze = directory/'sources.json'
        save(freeze, dict(source_sha256=sources, inputs=inputs, units=[binding]))
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                   PYTHONPATH=str(HERE.parents[1]/'src'))
        output = directory/(args.unit+'.json')
        launch = execute([sys.executable, str(HERE/'run_one_start_blas_96.py'), args.unit,
                          '--seed-limit', '1', '--output', str(output)], directory, args.unit, timeout_s=90, env=env)
        verify_sources(sources); verify_sources(inputs)
        launch.update(freeze_sha256=digest(freeze), receipt_sha256=digest(output) if output.exists() else None)
        save(output.with_suffix('.launch.json'), launch)
        audit = execute([sys.executable, str(HERE/'evaluate_variant.py'), str(directory)],
                        directory, 'audit', timeout_s=90, env=env)
        save(directory/'audit-launch.json', audit)
        evaluation = sealed(directory/'evaluation.json') if (directory/'evaluation.json').exists() else None
        receipt = sealed(output) if output.exists() else None
        checks = compare(parent, receipt)
        complete = process_ok(launch) and process_ok(audit)
        rows = evaluation['rows'] if evaluation else []
        accepted = complete and len(rows) == 1 and rows[0]['unit'] == args.unit and rows[0]['accepted']
        verify_sources(sources); verify_sources(inputs)
        result = dict(unit=args.unit, parent_path=str(parent_file), parent_sha256=digest(parent_file),
            launch=launch, audit_launch=audit, evaluation=evaluation, checks=checks,
            processes_completed=complete, policy_equivalent=complete and all(checks.values()), accepted=accepted,
            qualification='96-iteration cold pilot; same model and total budget. Historical64-iteration comparator. '
            'Controls plus failure-selected singles; reference scoring only after numerical acceptance.')
        save(directory/'comparison.json', result)
        print(json.dumps(dict(unit=args.unit, accepted=accepted, policy_equivalent=result['policy_equivalent'], checks=checks)), flush=True)


if __name__ == '__main__':
    main()
