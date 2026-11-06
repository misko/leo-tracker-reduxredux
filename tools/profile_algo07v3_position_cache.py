"""Observe per-problem cache evictions without skipping any additional calculation.

Shadow capacities count potentially reusable work, not proven speed gains.
The real cache and returned result objects remain unchanged.
"""

import argparse
import hashlib
import json
import os
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

from benchmark_algo07v3_training_kernel import trial
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_posterior_buffers import training_inputs

from leo.analysis.localization_v3 import event_position, hierarchical, prediction
from leo.operations.localization_v3_job import runtime_versions


class Census:
    def __init__(self, capacities=(8, 16, 32, 64)):
        if 8 not in capacities or any(type(n) is not int or n < 8 for n in capacities):
            raise ValueError('Include the existing size 8 and positive larger integer sizes')
        self.rows = []
        self.capacities = tuple(dict.fromkeys(capacities))

    def attach(self, problem, original_cached):
        original = problem.calculate
        row = dict(calls=0, actual_misses=0, actual_calculation_seconds=0.0,
                   shadows={str(n): dict(misses=0, avoidable_calls=0,
                                         avoidable_calculation_seconds=0.0)
                            for n in self.capacities})
        shadows = {n: OrderedDict() for n in self.capacities}
        self.rows.append(row)

        def measured(x):
            began = time.perf_counter()
            value = original(x)
            row['actual_calculation_seconds'] += time.perf_counter() - began
            row['actual_misses'] += 1
            return value

        problem.calculate = measured
        original_cached(problem)
        actual = problem.calculate

        def observed(x):
            key = tuple(x)
            count, seconds = row['actual_misses'], row['actual_calculation_seconds']
            hits = {n: key in cache for n, cache in shadows.items()}
            value = actual(x)
            miss = row['actual_misses'] - count
            assert miss == int(not hits[8]), 'Shadow differs from actual existing cache'
            row['calls'] += 1
            for n, cache in shadows.items():
                stats = row['shadows'][str(n)]
                stats['misses'] += int(not hits[n])
                if miss and hits[n]:
                    stats['avoidable_calls'] += 1
                    stats['avoidable_calculation_seconds'] += (
                        row['actual_calculation_seconds'] - seconds)
                cache[key] = None
                cache.move_to_end(key)
                if len(cache) > n:
                    cache.popitem(last=False)
            return value

        problem.calculate = observed
        return problem


@contextmanager
def observe(census):
    originals = [(module, module.cached) for module in (prediction, event_position)]
    try:
        for module, operation in originals:
            module.cached = lambda p, operation=operation: census.attach(p, operation)
        yield
    finally:
        for module, operation in originals:
            module.cached = operation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('request', 'expected-root', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    expected = {arm: args.expected_root / f'{arm}-0-candidate.json'
                for arm in ('c0', 'fitted_c')}
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__), *expected.values(),
             Path('tools/benchmark_algo07v3_training_kernel.py'),
             Path('tools/probe_algo07v3_posterior_buffers.py'),
             Path('tools/probe_algo07v3_annotation_arms.py'),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    assert runtime_versions() == request['runtime']
    plan = dict(bindings=bindings, runtime_modified=False, observation_only=True,
                capacities=[8, 16, 32, 64], phase_rounds=5, optimizer_iterations=48,
                target=1, fold=1, cpus=sorted(os.sched_getaffinity(0)), blas_threads=1)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    results = {}
    for arm in ('c0', 'fitted_c'):
        d, keep, receipt, seed, split = training_inputs(request)
        before = fingerprint((d['node'], keep))
        census = Census()
        with observe(census):
            fit = trial(d, keep, arm, hierarchical.hierarchical_bound)
        row = dict(fit=fit, problems=census.rows, seed=seed, split=split,
                   scientific_receipt=receipt,
                   exact=fit['signature'] == json.loads(expected[arm].read_bytes())['signature'])
        results[arm] = row
        (args.output / f'{arm}.json').write_text(json.dumps(row, indent=2) + '\n')
        assert row['exact'] and before == fingerprint((d['node'], keep))
        assert len(census.rows) == 5
        summary = {str(n): {k: sum(p['shadows'][str(n)][k] for p in census.rows)
                            for k in ('misses', 'avoidable_calls', 'avoidable_calculation_seconds')}
                   for n in census.capacities}
        row['summary'] = summary
        print(json.dumps(dict(arm=arm, exact=True, summary=summary)), flush=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    (args.output / 'result.json').write_text(json.dumps(dict(
        plan=plan, results=results, measured_speedup=None, production_modified=False),
        indent=2) + '\n')


if __name__ == '__main__':
    main()
