"""Observe a saved initial branch's complete fit without changing its numerics."""

import argparse
import hashlib
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import initial_search, position
from leo.analysis.localization_v3.region import SearchRegion
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store


class FirstCappedCapture:
    """Own a copy of the first capped fit call; selection never uses elapsed time."""

    def __init__(self):
        self.value = None

    def record(self, row, args, kwargs):
        if self.value is None and row['in_fit'] and row['iterations'] == 256:
            self.value = (dict(row), [np.array(v, copy=True) for v in args],
                          {k: np.array(v, copy=True) if isinstance(v, np.ndarray) else v
                           for k, v in kwargs.items()})

    def save(self, output):
        if self.value is None:
            return False
        row, args, kwargs = self.value
        output.mkdir(exist_ok=False)
        arrays = {f'argument_{i}': v for i, v in enumerate(args)}
        scalars = {}
        for key, value in kwargs.items():
            if isinstance(value, np.ndarray):
                arrays[f'keyword_{key}'] = value
            else:
                scalars[key] = value
        np.savez(output/'hardest.npz', **arrays)
        metadata = dict(row, scalar_keywords=scalars, selection='first capped in-fit call',
                        arrays_sha256=hashlib.sha256((output/'hardest.npz').read_bytes()).hexdigest())
        (output/'hardest.json').write_text(json.dumps(metadata, indent=2)+'\n')
        return True


@contextmanager
def observe(rows, capture=None):
    original_fit, original_bound = position.fit, position.hierarchical_bound
    original_calculate = position.NormalPosition.calculate
    phase, coordinates, in_fit = [-1], [None], [False]

    def fit(*args, **kwargs):
        phase[0] += 1
        in_fit[0] = True
        try:
            return original_fit(*args, **kwargs)
        finally:
            in_fit[0] = False

    def calculate(problem, x):
        previous, coordinates[0] = coordinates[0], [float(v).hex() for v in x]
        try:
            return original_calculate(problem, x)
        finally:
            coordinates[0] = previous

    def bound(*args, **kwargs):
        # Fingerprinting is outside the measured likelihood call. It observes
        # complete numerical inputs, not just a potentially misleading x key.
        signature = hashlib.sha256(json.dumps(fingerprint((args, kwargs)),
                                             sort_keys=True).encode()).hexdigest()
        began, used = time.perf_counter(), time.process_time()
        result = original_bound(*args, **kwargs)
        elapsed, cpu = time.perf_counter()-began, time.process_time()-used
        result_signature = hashlib.sha256(json.dumps(fingerprint(result),
                                                    sort_keys=True).encode()).hexdigest()
        rows.append(dict(phase=phase[0], in_fit=in_fit[0], position=coordinates[0],
                         seconds=elapsed, cpu_seconds=cpu,
                         points=len(args[0]), width=args[1].shape[1],
                         input_signature=signature, result_signature=result_signature,
                         iterations=result['precision_iterations'],
                         final_change=result['final_log_precision_change']))
        if capture is not None:
            capture.record(rows[-1], args, kwargs)
        return result

    try:
        position.fit, position.hierarchical_bound = fit, bound
        position.NormalPosition.calculate = calculate
        yield
    finally:
        position.fit, position.hierarchical_bound = original_fit, original_bound
        position.NormalPosition.calculate = original_calculate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('request', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--branch', type=int, default=1)
    parser.add_argument('--capture-capped', action='store_true')
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('One CPU and one BLAS thread required')
    if args.output.resolve().is_relative_to('/mnt/qnap01'):
        parser.error('QNAP is read-only')
    args.output.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    assert runtime_versions() == request['runtime']
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    prepared = saved['evidence']['preparation']
    choices = saved['evidence']['audit']['initial']['choices']
    assert 0 <= args.branch < len(choices)
    choice = choices[args.branch]
    before = fingerprint((prepared, choice))
    noise = (json.dumps(prepared['noise'], default=_json_value,
                        sort_keys=True, allow_nan=False)+'\n').encode()
    plan = dict(bindings=bindings, branch=args.branch, arms=['c0', 'fitted_c'],
                scientific_receipt=saved['sha256'], rounds=5, iterations=48,
                profiler_only=True, production_modified=False, capture_capped=args.capture_capped)
    (args.output/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    results = []
    for arm in plan['arms']:
        scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                        hashlib.sha256(noise).hexdigest(), genuine=False)
        rows = []
        capture = FirstCappedCapture() if args.capture_capped else None
        began, used = time.perf_counter(), time.process_time()
        with observe(rows, capture):
            value = initial_search.fit_initial_arm(scan, scan.radio_sigma_hz, choice['node'],
                                                   arm, rounds=5, iterations=48)
        elapsed, cpu = time.perf_counter()-began, time.process_time()-used
        exact = fingerprint(value) == fingerprint(choice['arms'][arm])
        row = dict(arm=arm, seconds=elapsed, cpu_seconds=cpu, exact=exact, calls=rows)
        results.append(row)
        (args.output/f'{arm}.json').write_text(json.dumps(row, indent=2)+'\n')
        assert exact and before == fingerprint((prepared, choice))
        if capture is not None:
            capture.save(args.output/f'{arm}-capture')
        print(json.dumps({k:v for k,v in row.items() if k != 'calls'}), flush=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    (args.output/'result.json').write_text(json.dumps(dict(
        plan=plan, results=results, exact=True, full_pipeline_speedup=None), indent=2)+'\n')


if __name__ == '__main__':
    main()
