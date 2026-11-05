"""Count exact repeated normal-position calculations in a complete initial search.

Observation only: every original calculation still executes. The one-CPU clock
includes fingerprint instrumentation and is not a production timing benchmark.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import weakref
from collections import Counter, OrderedDict
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


class RepeatProfile:
    def __init__(self):
        self.instances = weakref.WeakKeyDictionary()
        self.rows = []

    def calculate(self, original, problem, x, caller):
        if problem not in self.instances:
            row = dict(index=len(self.rows), arm='fitted_c' if problem.fitted_c else 'c0',
                       calls=0, unique=0, repeated=0, seconds=0., repeat_seconds=0.,
                       callers=Counter(), hits={str(n): 0 for n in (1, 2, 8)},
                       hit_seconds={str(n): 0. for n in (1, 2, 8)})
            self.rows.append(row)
            self.instances[problem] = row, {}, {n: OrderedDict() for n in (1, 2, 8)}
        row, seen, caches = self.instances[problem]
        a = np.asarray(x)
        key = a.dtype.str, a.shape, a.tobytes()
        began = time.perf_counter()
        result = original(problem, x)
        elapsed = time.perf_counter() - began
        signature = fingerprint(result)
        row['calls'] += 1
        row['seconds'] += elapsed
        row['callers'][caller] += 1
        if key in seen:
            if signature != seen[key]:
                raise ValueError('Same position changed within a normal problem')
            row['repeated'] += 1
            row['repeat_seconds'] += elapsed
        else:
            row['unique'] += 1
            seen[key] = signature
        for capacity, cache in caches.items():
            if key in cache:
                row['hits'][str(capacity)] += 1
                row['hit_seconds'][str(capacity)] += elapsed
                cache.move_to_end(key)
            else:
                cache[key] = True
                if len(cache) > capacity:
                    cache.popitem(last=False)
        return result


@contextmanager
def observe(profile):
    original = position.NormalPosition.calculate

    def calculate(problem, x):
        return profile.calculate(original, problem, x, sys._getframe(1).f_code.co_name)

    try:
        position.NormalPosition.calculate = calculate
        yield
    finally:
        position.NormalPosition.calculate = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    if runtime_versions() != request['runtime']:
        raise ValueError('Match the frozen numerical runtime')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    prepared = saved['evidence']['preparation']
    noise = (json.dumps(prepared['noise'], default=_json_value,
                       sort_keys=True, allow_nan=False) + '\n').encode()
    scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                    hashlib.sha256(noise).hexdigest(), genuine=False)
    plan = dict(bindings=bindings, scientific_receipt=saved['sha256'],
                affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
                original_calculations_skipped=False, production_timing=False)
    (args.output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    profile = RepeatProfile()
    began, complete = time.perf_counter(), False
    try:
        with observe(profile):
            result = initial_search.initial_search(scan, scan.radio_sigma_hz)
        if fingerprint(result) != fingerprint(saved['evidence']['audit']['initial']):
            raise ValueError('Complete initial search changed under observation')
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha
               for p, sha in bindings.items()):
            raise ValueError('Bound source changed during profile')
        complete = True
    finally:
        totals = {key: sum(r[key] for r in profile.rows)
                  for key in ('calls', 'unique', 'repeated', 'seconds', 'repeat_seconds')}
        totals['hits'] = {str(n): sum(r['hits'][str(n)] for r in profile.rows) for n in (1, 2, 8)}
        totals['hit_seconds'] = {str(n): sum(r['hit_seconds'][str(n)] for r in profile.rows)
                                 for n in (1, 2, 8)}
        receipt = dict(**plan, complete=complete, exact=complete, rows=profile.rows,
                       totals=totals, instrumented_seconds=time.perf_counter() - began)
        (args.output / 'profile.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(dict(complete=complete, totals=totals)), flush=True)


if __name__ == '__main__':
    main()
