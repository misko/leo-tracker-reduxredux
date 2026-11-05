"""Alternate complete phase-refreshed fits with frozen and owned geometry.

External benchmark only: temporarily substitute the geometry calculator inside
this single-process experiment, restoring it after every trial and failure.
"""

import argparse
import hashlib
import json
import os
import statistics
import time
from contextlib import contextmanager
from pathlib import Path

import algo07v3_preposition_geometry_oracle as oracle
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import marginal
from leo.analysis.localization_v3.position import refreshed
from leo.analysis.localization_v3.region import SearchRegion
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store


@contextmanager
def calculator(operation):
    original = marginal.JointMarginal.calculate
    try:
        marginal.JointMarginal.calculate = operation
        yield
    finally:
        marginal.JointMarginal.calculate = original


def trial(scan, node, arm, operation):
    with calculator(operation):
        start, cpu = time.perf_counter(), time.process_time()
        problem, fit, history = refreshed(scan, scan.radio_sigma_hz, node, arm)
        seconds, cpu_seconds = time.perf_counter() - start, time.process_time() - cpu
        x = fit['parameters']
        signature = fingerprint(dict(fit=fit, history=history, state=problem.state(x),
                                     reference=problem.reference, calculated=problem.calculate(x)))
    return dict(seconds=seconds, cpu_seconds=cpu_seconds, signature=signature)


def alternating_fits(run):
    results = []
    for arm in ('c0', 'fitted_c'):
        expected = None
        for pair in range(3):
            order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
            for side in order:
                result = run(arm, side)
                if expected is not None and result['signature'] != expected:
                    raise ValueError('Full phase-refreshed fit changed')
                expected = result['signature']
                results.append(dict(arm=arm, pair=pair, side=side, **result))
                print(json.dumps(results[-1]), flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Fresh output required')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        parser.error('Pin OPENBLAS_NUM_THREADS=1 before starting Python')
    if len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU for alternating fits')
    if not hasattr(marginal, '_phase_geometry'):
        parser.error('Run against the qualified prepared-geometry candidate')
    if hashlib.sha256(Path(oracle.__file__).read_bytes()).hexdigest() != (
            '38535668aa81bb2116250225c457721b91a77fbd81084e8675a109ad3aa21c3f'):
        raise ValueError('Frozen original calculator changed')
    files = [*Path('src').rglob('*.py'), args.request, Path(__file__), Path(oracle.__file__),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    request = json.loads(args.request.read_bytes())
    if runtime_versions() != request['runtime']:
        raise ValueError('Match the numerical runtime')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    prepared, initial = saved['evidence']['preparation'], saved['evidence']['audit']['initial']
    noise_bytes = (json.dumps(prepared['noise'], default=_json_value,
                             sort_keys=True, allow_nan=False) + '\n').encode()
    winner = next(row for row in initial['choices']
                  if row['hypothesis'] == initial['selected_hypothesis'])
    functions = dict(baseline=oracle.JointMarginal.calculate,
                     candidate=marginal.JointMarginal.calculate)

    def run(arm, side):
        scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                        hashlib.sha256(noise_bytes).hexdigest(), genuine=True)
        return trial(scan, winner['node'], arm, functions[side])

    results = alternating_fits(run)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    means = {arm: {side: {key: statistics.mean(r[key] for r in results
                                              if r['side'] == side and r['arm'] == arm)
                          for key in ('seconds', 'cpu_seconds')} for side in functions}
             for arm in ('c0', 'fitted_c')}
    result = dict(rows=results, means=means, exact=True, bindings=bindings,
                  affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
                  phase_rounds=5, optimizer_iterations_per_round=48, runtime=request['runtime'],
                  prepared_input_benchmark=True, full_pipeline_speedup=None,
                  scientific_receipt=saved['sha256'])
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(means), flush=True)


if __name__ == '__main__':
    main()
