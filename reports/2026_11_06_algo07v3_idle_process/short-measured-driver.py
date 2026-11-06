"""External exact initial-search experiment: lend idle capacity to derivative axes.

Only the last live fit, after the outer queue drains and peers are reaped, may
use one helper thread. Runtime sources and production configuration are untouched.
"""

import argparse
import copy
import hashlib
import inspect
import json
import multiprocessing
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_gradient_axes import transform
from profile_algo07v3 import cpu, resources

from leo.analysis.localization_v3 import initial_search, position
from leo.analysis.localization_v3.region import SearchRegion
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.operations import localization_v3_parallel as parallel
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store


class IdleDerivatives:
    """One map invocation; only its sole surviving outer child can borrow."""

    def __init__(self):
        self.spare = multiprocessing.get_context('fork').Value('b', 0, lock=False)
        self.executor = None
        self.problem = self.clone = None
        self.records = []
        self.counts = dict(serial_gradients=0, borrowed_gradients=0, cloned_problems=0)
        self.gradient, self.original_gradient, self.generated_gradient = transform()
        self.gradient.__globals__['_columns'] = self.columns
        original = inspect.getsource(parallel._execute)
        needle = '                    del pending[index]'
        if original.count(needle) != 1:
            raise ValueError('Review changed outer-queue completion boundary')
        replacement = needle + '''
                    process.join()
                    if process.exitcode != 0:
                        raise ParallelFitFailure("Initial child failed during teardown")
                    _spare.value = int(next_item == len(items) and len(pending) == 1)'''
        self.original_executor = original
        self.generated_executor = original.replace(needle, replacement)
        scope = dict(vars(parallel), _spare=self.spare)
        exec(compile(self.generated_executor, '<idle-derivative-queue>', 'exec'), scope)
        self.execute = scope['_execute']

    def columns(self, residual, x, lo, hi, step):
        pairs = []
        for k in range(len(x)):
            a, b = x.copy(), x.copy()
            a[k], b[k] = max(lo[k], x[k]-step), min(hi[k], x[k]+step)
            pairs.append((b, a))
        owner = getattr(residual, '__self__', None)
        safe = (type(owner) is position.NormalPosition and
                getattr(residual, '__func__', None) is position.NormalPosition.residual and
                not any(callable(v) for v in vars(owner).values()))
        if not self.spare.value or len(pairs) != 2 or not safe:
            self.counts['serial_gradients'] += 1
            values = [(residual(b), residual(a)) for b, a in pairs]
        else:
            if self.problem is not owner:
                self.problem, self.clone = owner, copy.copy(owner)
                # Model arrays are read-only inputs throughout this fixed-phase
                # fit. Give the helper its own mutable geometry-cache attribute.
                self.clone._fixed_phase_geometry_cache = None
                self.counts['cloned_problems'] += 1
            if self.executor is None:
                self.executor = ThreadPoolExecutor(max_workers=1,
                                                   thread_name_prefix='idle-derivative')
            self.counts['borrowed_gradients'] += 1
            right = self.clone.residual
            b, a = pairs[1]
            future = self.executor.submit(lambda: (right(b), right(a)))
            left = (residual(pairs[0][0]), residual(pairs[0][1]))
            values = [left, future.result()]
        return [(v[0]-v[1])/(pair[0][k]-pair[1][k])
                for k, (v, pair) in enumerate(zip(values, pairs, strict=True))]

    def task(self, operation, item):
        old = position.bounded_gauss_newton
        position.bounded_gauss_newton = self.gradient
        try:
            began, used = time.perf_counter(), time.process_time()
            value = operation(item)
            elapsed, used = time.perf_counter()-began, time.process_time()-used
            return value, dict(item=item, seconds=elapsed, cpu_seconds=used, **self.counts)
        finally:
            position.bounded_gauss_newton = old
            if self.executor is not None:
                self.executor.shutdown(wait=True, cancel_futures=True)
            self.problem = self.clone = None

    def map(self, operation, items):
        if self.records or self.spare.value:
            raise ValueError('Use a fresh coordinator for each outer queue')
        # Delegate the existing public port's input validation, changing only
        # its narrow executor binding in this external function copy.
        def ordered(op, values, *, workers=None):
            try:
                rows = self.execute(lambda item: self.task(op, item), values, workers=workers)
            except Exception as error:
                raise parallel.ParallelFitFailure(str(error)) from error
            self.records = [row[1] for row in rows]
            return [row[0] for row in rows]
        scope = dict(vars(parallel), _ordered=ordered)
        exec(compile(inspect.getsource(parallel.map_initial_branches),
                     '<idle-initial-port>', 'exec'), scope)
        return scope['map_initial_branches'](operation, items)


def main(coordinator_type=IdleDerivatives, extra_paths=()):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--repeats', type=int, choices=(1, 2, 3), default=1)
    p.add_argument('--candidate-first', action='store_true')
    args = p.parse_args()
    if len(os.sched_getaffinity(0)) != 3 or os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        p.error('Three CPUs and one BLAS thread required')
    if args.output.resolve().is_relative_to('/mnt/qnap01'):
        p.error('QNAP is read-only')
    args.output.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    assert runtime_versions() == request['runtime']
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/probe_algo07v3_gradient_axes.py'), Path('tools/profile_algo07v3.py'),
             *extra_paths]
    bindings = {str(q.resolve()): hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    prepared, expected = saved['evidence']['preparation'], saved['evidence']['audit']['initial']
    before = fingerprint(prepared)
    noise = (json.dumps(prepared['noise'], default=_json_value,
                        sort_keys=True, allow_nan=False)+'\n').encode()
    prototype = coordinator_type()
    for name in ('original_executor', 'generated_executor', 'original_gradient',
                 'generated_gradient'):
        (args.output/f'{name}.py').write_text(getattr(prototype, name)+'\n')
    plan = dict(bindings=bindings, scientific_receipt=saved['sha256'],
                cpus=sorted(os.sched_getaffinity(0)), blas_threads=1, max_execution_units=3,
                candidate_first=args.candidate_first, repeats=args.repeats,
                production_modified=False, external_function_substitution=True,
                coordinator_type=coordinator_type.__name__)
    (args.output/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    rows = []
    for pair in range(args.repeats):
        order = ['baseline', 'candidate']
        if bool(pair % 2) != args.candidate_first:
            order.reverse()
        for side in order:
            scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                            hashlib.sha256(noise).hexdigest(), genuine=False)
            coordinator = coordinator_type()
            mapper = (coordinator.map if side == 'candidate' else parallel.map_initial_branches)
            host = resources()
            began, used = time.perf_counter(), cpu()
            value = initial_search.initial_search(scan, scan.radio_sigma_hz, map_branches=mapper)
            elapsed, after = time.perf_counter()-began, cpu()
            row = dict(pair=pair, side=side, seconds=elapsed,
                       cpu_seconds=sum(b-a for a, b in zip(used, after, strict=True)),
                       exact=fingerprint(value) == fingerprint(expected),
                       tasks=coordinator.records, resources_before=host,
                       resources_after=resources())
            rows.append(row)
            (args.output/f'{pair}-{side}.json').write_text(json.dumps(row, indent=2)+'\n')
            assert row['exact'] and before == fingerprint(prepared)
            print(json.dumps({k:v for k,v in row.items() if k not in (
                'tasks', 'resources_before', 'resources_after')}), flush=True)
    assert all(hashlib.sha256(Path(q).read_bytes()).hexdigest() == sha
               for q, sha in bindings.items())
    (args.output/'result.json').write_text(json.dumps(dict(
        plan=plan, rows=rows, exact=True, full_pipeline_speedup=None), indent=2)+'\n')


if __name__ == '__main__':
    main()
