"""Observe exact repeated hierarchical inputs without skipping any calculation.

Every process has an independent observation table. Input keys include all
arguments/defaults, array contents and layouts. This is not a runtime cache.
"""

import argparse
import hashlib
import inspect
import json
import os
import sys
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3 import resources

from leo.analysis.localization_v3 import (
    discovery_likelihood,
    event_position,
    hierarchical,
    history_position,
    position,
    retained_position,
)
from leo.cli.algo07v3 import supervise, worker, write

MODULES = (discovery_likelihood, event_position, history_position, position, retained_position)


def input_signature(arguments):
    def layout(value):
        if isinstance(value, np.ndarray):
            return dict(value=fingerprint(value), strides=value.strides,
                        aligned=bool(value.flags.aligned), writeable=bool(value.flags.writeable))
        if isinstance(value, dict):
            return {k: layout(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [layout(v) for v in value]
        return fingerprint(value)
    return hashlib.sha256(json.dumps(layout(arguments), sort_keys=True).encode()).hexdigest()


class Observer:
    def __init__(self):
        self.signature = inspect.signature(hierarchical.hierarchical_bound)
        self.reset()

    def reset(self):
        self.pid, self.seen, self.rows = os.getpid(), {}, {}
        self.caches = {n: OrderedDict() for n in (1, 8, 64, 512)}

    def call(self, original, label, args, kwargs):
        if self.pid != os.getpid():
            self.reset()  # Forked processes must not count inherited parent observations.
        begin = time.perf_counter()
        bound = self.signature.bind(*args, **kwargs)
        bound.apply_defaults()
        key = input_signature(bound.arguments)
        key_seconds = time.perf_counter() - begin
        begin = time.perf_counter()
        result = original(*args, **kwargs)
        seconds = time.perf_counter() - begin
        begin = time.perf_counter()
        signature = fingerprint(result)
        row = self.rows.setdefault(label, dict(calls=0, seconds=0., repeat_calls=0,
                                              repeat_seconds=0., cross_label_calls=0,
                                              key_seconds=0., output_check_seconds=0.,
                                              hits={str(n): 0 for n in self.caches},
                                              hit_seconds={str(n): 0. for n in self.caches}))
        row['calls'] += 1
        row['seconds'] += seconds
        row['key_seconds'] += key_seconds
        if key in self.seen:
            expected, first_label = self.seen[key]
            if signature != expected:
                raise ValueError('Identical complete hierarchical input changed its result')
            row['repeat_calls'] += 1
            row['repeat_seconds'] += seconds
            row['cross_label_calls'] += int(label != first_label)
        else:
            self.seen[key] = signature, label
        for capacity, cache in self.caches.items():
            if key in cache:
                row['hits'][str(capacity)] += 1
                row['hit_seconds'][str(capacity)] += seconds
                cache.move_to_end(key)
            else:
                cache[key] = True
                if len(cache) > capacity:
                    cache.popitem(last=False)
        row['output_check_seconds'] += time.perf_counter() - begin
        return result

    def save(self, root):
        # Child reset may not have happened if the task used no hierarchical fit.
        if self.pid == os.getpid():
            write(root / f'calls-{self.pid}.json', dict(pid=self.pid, rows=self.rows,
                                                       unique_inputs=len(self.seen)))


@contextmanager
def observe(observer, label):
    originals = [(m, m.hierarchical_bound) for m in MODULES]
    try:
        for module, original in originals:
            def invoke(*args, original=original, module=module, **kwargs):
                return observer.call(original, f'{label()}:{module.__name__.rsplit(".", 1)[1]}',
                                     args, kwargs)
            module.hierarchical_bound = invoke
        yield
    finally:
        for module, original in originals:
            module.hierarchical_bound = original


def observed_worker(root):
    from leo.application import localization_v3_engine as engine
    from leo.operations import localization_v3_parallel as parallel

    observer, active = Observer(), 'outside'
    original_timing, original_invoke = engine._Timing.run, parallel._invoke

    def stage(timer, name, operation, expected=None):
        nonlocal active
        previous, active = active, name
        try:
            return original_timing(timer, name, operation, expected)
        finally:
            active = previous

    def child(*args):
        try:
            return original_invoke(*args)
        finally:
            observer.save(root)

    engine._Timing.run, parallel._invoke = stage, child
    try:
        with observe(observer, lambda: active):
            return worker(root / 'request.json', root / 'worker.json', False)
    finally:
        engine._Timing.run, parallel._invoke = original_timing, original_invoke
        observer.save(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    if args.worker:
        return observed_worker(args.worker)
    if not args.request or not args.output:
        parser.error('--request and --output required')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 3:
        parser.error('Pin three CPUs and one BLAS thread')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    write(root / 'request.json', dict(request, output_root=str(root / 'publication')))
    paths = [*Path('src').rglob('*.py'), Path(__file__), args.request, root / 'request.json',
             Path('tools/profile_algo07v3.py'), Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write(root / 'plan.json', dict(bindings=bindings, cpus=sorted(os.sched_getaffinity(0)),
                                   blas_threads=1, timeout_seconds=1200,
                                   calculations_skipped=False, production_modified=False))
    write(root / 'resources-start.json', resources())
    with (root / 'worker.log').open('xb') as log:
        outcome = supervise([sys.executable, '-B', str(Path(__file__).resolve()),
                             '--worker', str(root)], log=log, timeout=1200,
                            environment=dict(os.environ))
    changed = [p for p, sha in bindings.items()
               if hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha]
    result_path = root / 'worker.json'
    result = json.loads(result_path.read_bytes()) if result_path.exists() else None
    write(root / 'resources-end.json', resources())
    write(root / 'profile.json', dict(process=outcome, worker=result, changed_sources=changed,
                                     full_pipeline_speed_benchmark=False))
    return 0 if outcome['returncode'] == 0 and result and not changed else 1


if __name__ == '__main__':
    raise SystemExit(main())
