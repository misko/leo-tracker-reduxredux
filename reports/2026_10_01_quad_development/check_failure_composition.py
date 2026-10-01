"""Fresh paired inference preserving unresolved first-start outcomes."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys

from run_window import prepare_window
from regression_batch import digest, execute, verify_sources
from screen_seed_prefix import sealed
from failure_composition_checks import comparison_checks

HERE = Path(__file__).resolve().parent
ORDERS = {'DS9-B05-S2': ('original', 'blas'), 'DS9-B05-S3': ('blas', 'original'),
          'DS11-B04-S1': ('original', 'blas')}


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit', choices=ORDERS)
    args = parser.parse_args()
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        replay_path = HERE/'first-start-complete-v1.json'
        replay = sealed(replay_path)
        assert {r['unit'] for r in replay['rows'] if r['size'] == 1
                and not r['first']['accepted']} == set(ORDERS)
        for key in ('sources', 'inputs', 'frozen_sources_and_inputs'):
            verify_sources(replay[key])
        binding, scans, _, _, _ = prepare_window(args.unit)
        parent_path = HERE/'independent-v2'/binding['block_id']/(args.unit+'.json')
        parent = sealed(parent_path)
        sources, inputs = dict(parent['source_sha256']), dict(parent['inputs'])
        inputs.update({str(parent_path): digest(parent_path), str(replay_path): digest(replay_path)})
        for _, height, _ in scans:
            inputs[height.input_bindings['grid_path']] = height.input_bindings['grid_sha256']
        for name in ('one-start-blas-cold-summary-v1.json', 'one-start-blas-window-pair-summary-v1.json',
                     'one-start-blas-window-quad-summary-v1.json'):
            path = HERE/name
            prior = sealed(path)
            assert len(prior['rows']) == 3 and all(r['both_accepted_equivalent'] for r in prior['rows'])
            for key in ('sources', 'inputs', 'frozen_sources_and_inputs'):
                verify_sources(prior[key])
            inputs[str(path)] = digest(path)
        for unit in ORDERS:
            path = HERE/'failure-composition-prerequisite-v1'/(unit+'.json')
            gate = sealed(path)
            assert gate['unit'] == unit and gate['maximum_score_error'] < 1e-6
            assert all(gate['proposal_checks'].values())
            verify_sources(gate['sources']); verify_sources(gate['inputs'])
            sources.update(gate['sources']); inputs.update(gate['inputs'])
            inputs[str(path)] = digest(path)
        for name in ('check_failure_composition.py', 'failure_composition_checks.py',
                     'test_failure_composition_checks.py', 'FAILURE_COMPOSITION_PLAN.md',
                     'run_seed_limit.py', 'run_one_start_blas.py', 'evaluate_variant.py', 'evaluate_pilot.py'):
            sources[str(HERE/name)] = digest(HERE/name)
        verify_sources(sources); verify_sources(inputs)
        directory = HERE/'failure-composition-cold-v1'/args.unit
        directory.mkdir(parents=True, exist_ok=False)
        save(directory/'plan.json', dict(unit=binding, order=ORDERS[args.unit], sources=sources, inputs=inputs))
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                   PYTHONPATH=str(HERE.parents[1]/'src'))
        outcomes, receipts = {}, {}
        for arm in ORDERS[args.unit]:
            folder = directory/arm
            folder.mkdir()
            freeze = folder/'sources.json'
            save(freeze, dict(source_sha256=sources, inputs=inputs, units=[binding]))
            output = folder/(args.unit+'.json')
            worker = 'run_seed_limit.py' if arm == 'original' else 'run_one_start_blas.py'
            launch = execute([sys.executable, str(HERE/worker), args.unit, '--seed-limit', '1',
                              '--output', str(output)], folder, args.unit, timeout_s=90, env=env)
            verify_sources(sources); verify_sources(inputs)
            launch.update(freeze_sha256=digest(freeze), receipt_sha256=digest(output) if output.exists() else None)
            save(output.with_suffix('.launch.json'), launch)
            audit = execute([sys.executable, str(HERE/'evaluate_variant.py'), str(folder)],
                            folder, 'audit', timeout_s=90, env=env)
            save(folder/'audit-launch.json', audit)
            evaluation = sealed(folder/'evaluation.json') if (folder/'evaluation.json').exists() else None
            receipts[arm] = sealed(output) if output.exists() else None
            outcomes[arm] = dict(launch=launch, audit_launch=audit, evaluation=evaluation)
        verify_sources(sources); verify_sources(inputs)
        checks = comparison_checks(receipts, parent, outcomes)
        result = dict(unit=args.unit, outcomes=outcomes, checks=checks,
                      failure_preserved=all(checks.values()),
                      qualification='Failure-selected cold computational comparison; matching rejection is not '
                      'numerical acceptance. No reference error is reported for unresolved fits.')
        save(directory/'comparison.json', result)
        print(json.dumps(dict(unit=args.unit, failure_preserved=result['failure_preserved'], checks=checks)), flush=True)


if __name__ == '__main__':
    main()
