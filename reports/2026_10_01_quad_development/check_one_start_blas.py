"""Paired one-start acquisition composition, with separate bounded audits."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys

import numpy as np
from run_window import prepare_window
from regression_batch import digest, execute, verify_sources
from screen_seed_prefix import sealed

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORDERS = {'DS9-B01-S1': ('original','blas'), 'DS10-B01-S1': ('blas','original'),
          'DS11-B01-S1': ('original','blas')}


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit', choices=ORDERS)
    args = parser.parse_args()
    with (HERE.parent/'2026_10_01_localization_goal/.regression-fit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        binding, scans, _, _, _ = prepare_window(args.unit)
        baseline_path = HERE/'independent-v2'/args.unit.rsplit('-',1)[0]/(args.unit+'.json')
        baseline = sealed(baseline_path)
        verify_sources(baseline['source_sha256'])
        verify_sources(baseline['inputs'])
        inputs = dict(baseline['inputs'])
        for _, height, _ in scans:
            inputs[height.input_bindings['grid_path']] = height.input_bindings['grid_sha256']
        inputs[str(baseline_path)] = digest(baseline_path)
        sources = dict(baseline['source_sha256'])
        for unit in ORDERS:
            gate_path = HERE/'one-start-blas-prerequisite-v1'/(unit+'.json')
            gate = sealed(gate_path)
            assert all(gate['proposal_checks'].values()) and gate['maximum_score_error'] < 1e-6
            verify_sources(gate['sources']); verify_sources(gate['inputs'])
            sources.update(gate['sources']); inputs.update(gate['inputs'])
            inputs[str(gate_path)] = digest(gate_path)
        for name in ('check_one_start_blas.py', 'run_seed_limit.py', 'run_one_start_blas.py',
                     'ONE_START_BLAS_PLAN.md', 'test_one_start_blas_wrapper.py', 'screen_seed_prefix.py',
                     'evaluate_variant.py', 'evaluate_pilot.py', 'SEED_PREFIX_SCREEN.md'):
            path = HERE/name
            sources[str(path)] = digest(path)
        directory = HERE/'one-start-blas-cold-v1'/args.unit
        directory.mkdir(parents=True, exist_ok=False)
        save(directory/'plan.json', dict(unit=binding, order=ORDERS[args.unit], sources=sources, inputs=inputs))
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', PYTHONPATH=str(ROOT/'src'))
        results = {}
        for limit in ORDERS[args.unit]:
            arm = directory/str(limit)
            arm.mkdir()
            freeze = arm/'sources.json'
            save(freeze, dict(source_sha256=sources, inputs=inputs, units=[binding]))
            output = arm/(args.unit+'.json')
            launch = execute([sys.executable, str(HERE/('run_seed_limit.py' if limit == 'original' else 'run_one_start_blas.py')), args.unit,
                              '--seed-limit', '1', '--output', str(output)],
                             arm, args.unit, timeout_s=90*binding['size'], env=env)
            verify_sources(sources)
            verify_sources(inputs)
            launch.update(freeze_sha256=digest(freeze), receipt_sha256=digest(output) if output.exists() else None)
            save(output.with_suffix('.launch.json'), launch)
            audit_launch = execute([sys.executable, str(HERE/'evaluate_variant.py'), str(arm)],
                                   arm, 'audit', timeout_s=90*binding['size'], env=env)
            save(arm/'audit-launch.json', audit_launch)
            evaluation = sealed(arm/'evaluation.json') if (arm/'evaluation.json').exists() else None
            results[str(limit)] = dict(launch=launch, audit_launch=audit_launch, evaluation=evaluation)
        paths = [directory/str(i)/(args.unit+'.json') for i in ('original', 'blas')]
        checks = {}
        if all(p.exists() for p in paths):
            one, three = [sealed(p) for p in paths]
            checks['configured_limits'] = one['config']['seed_limit'] == three['config']['seed_limit'] == 1
            for key in ('seeds','requested','unique_points','spacing'):
                checks['proposal_'+key] = one.get('proposal',{}).get(key) == three.get('proposal',{}).get(key) == baseline['proposal'][key]
            checks['proposal_scores'] = all('proposal' in r and np.allclose(r['proposal']['scores'],baseline['proposal']['scores'],rtol=0,atol=1e-6) for r in (one,three))
            checks['one_fit'] = len(one['fits']) == 1
            if one['fits'] and three['fits']:
                a, b = one['fits'][0], three['fits'][0]
                checks['first_state'] = bool(np.allclose(a['mean'], b['mean'], rtol=0, atol=1e-5))
                checks['first_labels'] = a['associations'] == b['associations']
                checks['first_objective'] = abs(a['objectives'][-1]-b['objectives'][-1]) < 1e-6
            checks['blas_fit_count'] = len(three['fits']) == 1
            for label, receipt in (('original',one),('blas',three)):
                fit = receipt.get('best'); saved = baseline['fits'][0]
                checks[label+'_saved_state'] = bool(fit and np.allclose(fit['mean'],saved['mean'],rtol=0,atol=1e-5))
                checks[label+'_saved_labels'] = bool(fit and fit['associations']==saved['associations'])
                checks[label+'_saved_objective'] = bool(fit and abs(fit['objectives'][-1]-saved['objectives'][-1])<1e-6)
        result = dict(unit=args.unit, results=results, equivalence_checks=checks,
                      qualification='Cold inference from prepared inputs; sequential alternating order, not randomized. No inherited fitted state. Numerical audit before reference scoring.')
        save(directory/'comparison.json', result)
        print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
