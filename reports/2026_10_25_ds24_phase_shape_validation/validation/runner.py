"""Bounded fresh-recording reference and frozen RX1 comparison; no geography."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
PYTHON = REPO / '.venv/bin/python'
OLD = Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')
ENGINE = Path('/srv/bulk/leo/research/ds25-20261024/engine/ds24_engine.py')
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OPENBLAS_NUM_THREADS='1',
           OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
           PYTHONPATH=f'/tmp/algo03-feasible-deps:{OLD}/evaluation:src:tools')
ARMS = ('c0', 'fitted_c')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write_new(path, value):
    def encode(x):
        import numpy as np
        if isinstance(x, np.ndarray): return x.tolist()
        if isinstance(x, np.generic): return x.item()
        raise TypeError(type(x).__name__)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, default=encode, allow_nan=False)
        handle.write('\n')


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def protocol():
    p = read(ROOT / 'protocol.json')
    for binding in p['bindings']:
        if digest(binding['path']) != binding['sha256']:
            raise ValueError('frozen input/source changed: ' + binding['path'])
    if p['cases'] != [r['dataset_label'] for r in read(ROOT / 'sample.json')['selected']]:
        raise ValueError('panel membership changed')
    qualification = read(OLD / 'receiver/selection.json')
    if not qualification['selection_uses_no_GPS'] or not qualification['methods']['fast_rx1_rf50']['qualified']:
        raise ValueError('original frozen RF qualification is absent')
    return p


def run_command(command, log_path, seconds):
    if seconds <= 0:
        raise TimeoutError('study or case budget exhausted before stage')
    with Path(log_path).open('x') as log:
        child = subprocess.Popen(command, cwd=REPO, env=ENV, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return child.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            # Only this newly created process group; elevated preparation may
            # have descendants inaccessible to the unprivileged supervisor.
            subprocess.run(['sudo', '-n', 'kill', '-KILL', '--', '-' + str(child.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=False, timeout=10)
            child.wait(timeout=10)
            raise


def baseline_context(case):
    import numpy as np
    import algo02_scan as algo
    saved_path = ROOT / 'family_cavity/position' / (case + '.json')
    saved = read(saved_path)
    if saved['status'] != 'complete':
        raise ValueError('baseline incomplete')
    chosen = saved['selected'] if saved['accepted'] else None
    algo.bind_run_directory(ROOT)
    return dict(case=case, scan=algo.load_scan(ROOT, case),
        node=copy.deepcopy(chosen['node'] if chosen else saved['baseline_node']),
        keep=np.asarray(saved['original_mask'], bool), powers=np.asarray(saved['powers']),
        model=copy.deepcopy(saved['model']),
        means=np.asarray(chosen['means'] if chosen else saved['baseline_means']),
        entries=copy.deepcopy(chosen['entries'] if chosen else saved['baseline_entries']),
        observations=read(ROOT / case / 'observations.json'),
        arms=saved['policy_arms'], baseline_path=str(saved_path),
        baseline_sha256=digest(saved_path))


def trial(case):
    import numpy as np
    from matched_controls import (measurement_binding, factor_contract,
                                  cold_refit, phase_pair_valid)
    from probe_ds23_graph_seeded_paths import build, coverage
    p = protocol()
    if case not in p['cases']:
        raise ValueError('case outside fixed panel')
    began = time.monotonic()
    d = baseline_context(case)
    binding = measurement_binding(d)
    adapter = module(OLD / 'receiver/adapter.py', 'frozen_rx1_expansion')
    # The old build_method is intentionally cohort-bound. Reuse its exact
    # immutable expansion, while the new frozen panel supplies membership.
    changed = adapter.expand(d, 'fast_rx1_rf50')
    expected = {}
    replay = {}
    likelihood = None
    for arm in ARMS:
        s = d['arms'][arm]
        original = build(d, 'default', arm, s['phase_reference'])
        expected[arm] = factor_contract(original, d['entries'])
        curved = [native_id
            for i, sl in zip(original.members, original.slices, strict=True)
            for native_id, keep in zip(d['scan'].tracks[i]['observation_ids'], original.keep[sl], strict=True)
            if keep]
        predictive = [native_id for e in d['entries']
            for native_id in e.get('observation_ids', d['scan'].tracks[e['track_index']]['observation_ids'])]
        if len(curved) != len(set(curved)) or len(predictive) != len(set(predictive)) or set(curved) & set(predictive):
            raise ValueError('duplicate likelihood observation ownership')
        available = {o['observation_id'] for o in read(ROOT / case / 'observations.json')}
        if not (set(curved) | set(predictive)) <= available:
            raise ValueError('likelihood contains non-native observations')
        counts = dict(curved_unique=len(curved), predictive_unique=len(predictive),
                      union_unique=len(curved) + len(predictive), total_GLRT=len(available),
                      union_ids_sha256=hashlib.sha256(json.dumps(sorted(set(curved) | set(predictive))).encode()).hexdigest())
        if likelihood is not None and counts != likelihood:
            raise ValueError('c arms have different likelihood membership')
        likelihood = counts
        replay[arm] = float(original.calculate(s['endpoint_east_north_km'])[
            'negative_twice_elbo'] - s['negative_twice_elbo'])
        if abs(replay[arm]) > min(1e-3, 1e-8 * max(abs(s['negative_twice_elbo']), 1)):
            raise ValueError('original objective does not replay')
    results = {}
    for name, data in [('matched_cold_baseline', d), ('rx1_rf50', changed)]:
        arms = {}
        for arm in ARMS:
            arms[arm] = cold_refit(
                lambda a, ref: build(data, 'default', a, ref), arm,
                len(d['means']), d['entries'], expected[arm])
            write_new(ROOT / case / (name + '_' + arm + '.json'), arms[arm])
        results[name] = dict(arms=arms, paired_valid=bool(phase_pair_valid(arms)))
    if measurement_binding(d) != binding:
        raise ValueError('receiver expansion mutated the baseline inputs')
    adopted = results['rx1_rf50']['paired_valid']
    cov = {}
    for name, data, arms in [('baseline', d, d['arms']),
                             ('matched_cold_baseline', d, results['matched_cold_baseline']['arms']),
                             ('rx1_rf50', changed, results['rx1_rf50']['arms'])]:
        cov[name] = {a: coverage(data, 'default', a, arms[a]) for a in ARMS}
    losses = {a: sorted(set(cov['baseline'][a]['accepted_observation_ids']) -
                       set(cov['rx1_rf50'][a]['accepted_observation_ids'])) for a in ARMS}
    protocol()
    write_new(ROOT / case / 'comparison.json', dict(
        case=case, status='complete', baseline=d['arms'], results=results,
        adopted=adopted, policy_source='rx1_rf50' if adopted else 'baseline',
        coverage=cov, lost_baseline_postfit_IDs=losses,
        likelihood_membership=likelihood,
        lost_postfit_IDs_are_reported_not_a_new_policy_gate=True,
        original_policy='paired_original_RF_and_phase_gates_else_exact_baseline',
        original_objective_replay=replay, measurement_binding=binding,
        baseline_sha256=d['baseline_sha256'], physical_factors_preserved=True,
        GPS_or_error_used=False, seconds=time.monotonic() - began,
        protocol_sha256=digest(ROOT / 'protocol.json')))


def one(case, global_deadline):
    p = protocol()
    folder = ROOT / case
    folder.mkdir(exist_ok=True)
    began = time.monotonic()
    deadline = min(global_deadline, began + p['per_case_seconds'])
    env_arguments = [f'{k}={ENV[k]}' for k in
                     ('PYTHONPATH', 'PYTHONDONTWRITEBYTECODE',
                      'OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')]
    prep = [str(PYTHON), 'tools/prepare_algo02_ds23.py', '--run-dir', str(ROOT),
            '--case', case]
    stages = [
        ('export', ['sudo', '-n', 'env', *env_arguments, *prep, '--stage', 'export'], 180),
        ('prepare', ['sudo', '-n', 'env', *env_arguments, *prep, '--stage', 'prepare'], 600),
        ('algo02', [str(PYTHON), 'tools/algo02_scan.py', '--run-dir', str(ROOT),
                    '--case', case, '--stage', 'all'], 900),
        ('cavity', [str(PYTHON), str(ENGINE), '--root', str(ROOT), '--case', case], 960),
        ('comparison', [str(PYTHON), str(Path(__file__).resolve()), '--stage', 'trial',
                         '--case', case], 180)]
    result = dict(case=case, status='running', stages=[], GPS_or_error_used=False)
    try:
        for stage, command, cap in stages:
            mark = time.monotonic()
            try:
                code = run_command(command, folder / (stage + '.log'),
                                   min(cap, deadline - mark))
                result['stages'].append(dict(stage=stage, returncode=code,
                                              seconds=time.monotonic() - mark))
            except Exception as error:
                result['stages'].append(dict(stage=stage, error=repr(error),
                                              seconds=time.monotonic() - mark))
                raise
            if code:
                raise RuntimeError(stage + ' exited ' + str(code))
            if stage == 'prepare' and read(folder / 'prepared.json')['status'] != 'prepared':
                result.update(status='input_unqualified', reason=read(folder / 'prepared.json')['status'])
                break
            if stage == 'algo02' and read(folder / 'algo02_result.json')['status'] != 'accepted':
                result.update(status='reference_unqualified', reason=read(folder / 'algo02_result.json').get('reason'))
                break
            if stage == 'cavity' and read(ROOT / 'family_cavity/position' / (case + '.json'))['status'] != 'complete':
                result.update(status='reference_failed')
                break
        else:
            result.update(status='complete')
    except Exception as error:
        result.update(status='execution_failed', error=repr(error))
    result['seconds'] = time.monotonic() - began
    write_new(folder / 'execution.json', result)
    print(json.dumps(result), flush=True)
    return result


def run():
    p = protocol()
    preflight = read(ROOT / 'independent_preflight.json')
    if not preflight['all_passed'] or preflight['protocol_sha256'] != digest(ROOT / 'protocol.json'):
        raise ValueError('independent preflight did not pass')
    write_new(ROOT / 'scientific_start.json', dict(protocol_sha256=digest(ROOT / 'protocol.json'),
                                                  started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())))
    began = time.monotonic()
    with ThreadPoolExecutor(max_workers=p['workers']) as pool:
        jobs = [pool.submit(one, c, began + p['total_seconds']) for c in p['cases']]
        rows = [f.result() for f in as_completed(jobs)]
    write_new(ROOT / 'execution.json', dict(rows=sorted(rows, key=lambda r: r['case']),
        all_terminal=True, workers=p['workers'], seconds=time.monotonic() - began,
        GPS_or_error_used=False, protocol_sha256=digest(ROOT / 'protocol.json')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('run', 'trial'), required=True)
    parser.add_argument('--case')
    args = parser.parse_args()
    trial(args.case) if args.stage == 'trial' else run()
