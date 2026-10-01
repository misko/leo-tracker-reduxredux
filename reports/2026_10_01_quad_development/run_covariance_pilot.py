"""Bounded fixed-evidence covariance refits; original work charged to both arms."""
import time
START = time.monotonic()
import argparse
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import resource
import sys
import numpy as np
from covariance_track_ports import prepare_covariance_window
from run_window import fit_localization_fast
from regression_batch import execute, verify_sources
from screen_seed_prefix import sealed, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PILOT = ('DS9-B01-S1', 'DS10-B01-S1', 'DS11-B01-S1')


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')


def remaining_budget(original_seconds):
    if not np.isfinite(original_seconds) or original_seconds < 0:
        raise ValueError('Invalid original work accounting')
    remaining = 90-original_seconds
    if remaining < 10:
        raise ValueError('Insufficient remaining inference budget')
    return remaining


def worker(unit, limit, directory, seconds):
    freeze = sealed(directory/'sources.json')
    verify_sources(freeze['source_sha256'])
    verify_sources(freeze['inputs'])
    parent = Path(freeze['parent_receipt'])
    original = sealed(parent)
    prepared, selection = prepare_covariance_window(unit, limit)
    binding, scans, columns, precision, ports = prepared
    assert binding == original['binding']
    assert precision.tolist() == original['precision']
    assert [c.tolist() for c in columns] == original['columns']
    state = np.asarray(original['best']['mean'])
    fit = fit_localization_fast(state, ports, precision, lambda x: np.linalg.norm(x[:2]) <= 250,
        max_iterations=64, deadline=START+seconds-5, degrees_of_freedom=4.)
    fitted = dict(seed_index=original['best']['seed_index'], mean=fit.mean.tolist(),
        objectives=list(fit.objectives), converged=fit.converged, reason=fit.reason,
        iterations=fit.iterations, associations=list(fit.associations), seconds=time.monotonic()-START)
    result = deepcopy(original)
    result.update(best=fitted, fits=[fitted], status='converged_local_mode' if fit.converged else 'unresolved',
        observations=[list(p.observation_ids) for p in ports], source_sha256=freeze['source_sha256'],
        qualification='Warm local model diagnostic from same original state for each arm. Original inference work charged. No new acquisition, no geographic start selection.',
        covariance_pilot=dict(covariance_arm=limit, parent_sha256=digest(parent), initial_state=state.tolist(),
            max_iterations=64, selection=selection, original_seconds=freeze['original_seconds'], extra_limit_s=seconds))
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update(wall_seconds=freeze['original_seconds']+time.monotonic()-START,
                  cpu_seconds=original['cpu_seconds']+usage.ru_utime+usage.ru_stime)
    verify_sources(freeze['source_sha256'])
    verify_sources(freeze['inputs'])
    save(directory/(unit+'.json'), result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit', choices=PILOT)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--limit', choices=('tau10', 'matched_white'))
    parser.add_argument('--seconds', type=float)
    args = parser.parse_args()
    directory = HERE/'covariance-pilot-v1'/args.unit
    if args.worker:
        worker(args.unit, args.limit, directory/str(args.limit), args.seconds)
        return
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory.mkdir(parents=True, exist_ok=False)
        gates = [HERE/n for n in ('covariance-port-check-v1.json',)]
        sources, inputs = {}, {}
        for path in gates:
            gate = sealed(path)
            verify_sources(gate['sources'])
            verify_sources(gate['inputs'])
            sources.update(gate['sources'])
            inputs.update(gate['inputs'])
            inputs[str(path)] = digest(path)
        for name in ('run_covariance_pilot.py', 'evaluate_covariance_pilot.py', 'covariance_track_ports.py',
                     'evaluate_pilot.py', 'evaluate_variant.py', 'DENSER_TRACK_EVIDENCE_PLAN.md',
                     'COVARIANCE_FIT_PILOT_PLAN.md', 'test_covariance_pilot_policy.py'):
            sources[str(HERE/name)] = digest(HERE/name)
        parent = HERE/'independent-v2'/args.unit.rsplit('-', 1)[0]/(args.unit+'.json')
        original = sealed(parent)
        original_launch_path = parent.with_suffix('.launch.json')
        original_launch = json.loads(original_launch_path.read_text())
        assert original_launch['receipt_sha256'] == digest(parent)
        assert original_launch['returncode'] == 0 and original_launch['within_budget'] and not original_launch['timed_out']
        original_evaluation = parent.parent/'evaluation.json'
        audited = next(r for r in sealed(original_evaluation)['rows'] if r['unit'] == args.unit)
        assert audited['accepted'] and audited['receipt_sha256'] == digest(parent)
        original_seconds = original_launch['elapsed_seconds']
        seconds = remaining_budget(original_seconds)
        inputs.update({str(p): digest(p) for p in (parent, original_launch_path, original_evaluation)})
        verify_sources(sources)
        verify_sources(inputs)
        save(directory/'plan.json', dict(unit=args.unit, order=['tau10', 'matched_white'], sources=sources, inputs=inputs,
            original_seconds=original_seconds, extra_limit_s=seconds))
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONPATH=str(ROOT/'src'))
        for limit in ('tau10', 'matched_white'):
            arm = directory/str(limit)
            arm.mkdir()
            freeze = arm/'sources.json'
            save(freeze, dict(source_sha256=sources, inputs=inputs, units=[original['binding']],
                covariance_arm=limit, parent_receipt=str(parent), original_seconds=original_seconds))
            launch = execute([sys.executable, str(Path(__file__).resolve()), args.unit, '--worker',
                '--limit', str(limit), '--seconds', str(seconds)], arm, args.unit, timeout_s=seconds, env=env)
            output = arm/(args.unit+'.json')
            extra = launch['elapsed_seconds']
            launch.update(incremental_seconds=extra, original_seconds=original_seconds,
                elapsed_seconds=original_seconds+extra,
                within_budget=launch['within_budget'] and original_seconds+extra <= 90,
                freeze_sha256=digest(freeze), receipt_sha256=digest(output) if output.exists() else None)
            save(output.with_suffix('.launch.json'), launch)
            audit_launch = execute([sys.executable, str(HERE/'evaluate_covariance_pilot.py'), str(arm)],
                arm, 'audit', timeout_s=90, env=env)
            save(arm/'audit-launch.json', audit_launch)
            verify_sources(sources)
            verify_sources(inputs)
            evaluation = sealed(arm/'evaluation.json') if (arm/'evaluation.json').exists() else None
            save(arm/'outcome.json', dict(launch=launch, audit_launch=audit_launch, evaluation=evaluation))
            print(json.dumps(dict(unit=args.unit, limit=limit, audit_returncode=audit_launch['returncode'],
                evaluation=evaluation)), flush=True)


if __name__ == '__main__':
    main()
