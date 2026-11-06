"""External Cholesky-layout experiment against the current complete likelihood."""

import argparse
import hashlib
import inspect
import json
import os
import time
import types
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import hierarchical


def candidate():
    original = inspect.getsource(hierarchical._cholesky)
    needle = 'return np.ascontiguousarray(factor)'
    if original.count(needle) != 1:
        raise ValueError('Review changed Cholesky layout boundary')
    changed = original.replace(needle, 'return factor')
    scope = dict(vars(hierarchical))
    exec(compile(changed, '<native-cholesky-layout>', 'exec'), scope)
    baseline = hierarchical.hierarchical_bound
    function = types.FunctionType(baseline.__code__, scope, baseline.__name__,
                                  baseline.__defaults__, baseline.__closure__)
    function.__kwdefaults__ = baseline.__kwdefaults__.copy()
    return function, original, changed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        p.error('One CPU and one BLAS thread required')
    if args.output.resolve().is_relative_to('/mnt/qnap01'):
        p.error('QNAP is read-only')
    args.output.mkdir(exist_ok=False)
    meta, arrays = args.capture/'hardest.json', args.capture/'hardest.npz'
    metadata = json.loads(meta.read_bytes())
    assert hashlib.sha256(arrays.read_bytes()).hexdigest() == metadata['arrays_sha256']
    with np.load(arrays, allow_pickle=False) as data:
        positional = [data[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): data[k] for k in data.files
                         if k.startswith('keyword_')})
    operation, original, changed = candidate()
    paths = [Path(__file__), Path(hierarchical.__file__), meta, arrays,
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(q.resolve()): hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    (args.output/'original.py').write_text(original.rstrip()+'\n')
    (args.output/'candidate.py').write_text(changed.rstrip()+'\n')
    before = fingerprint((positional, keywords))
    expected = hierarchical.hierarchical_bound(*positional, **keywords)
    actual = operation(*positional, **keywords)
    differences = [k for k in expected if fingerprint(actual[k]) != fingerprint(expected[k])]
    rows = []
    if not differences:
        for pair in range(6):
            order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
            for side in order:
                function = operation if side == 'candidate' else hierarchical.hierarchical_bound
                began, used = time.perf_counter(), time.process_time()
                values = [function(*positional, **keywords) for _ in range(3)]
                elapsed, cpu = time.perf_counter()-began, time.process_time()-used
                row = dict(pair=pair, side=side, seconds=elapsed/3, cpu_seconds=cpu/3,
                           calls=3, exact=all(fingerprint(v) == fingerprint(expected) for v in values))
                rows.append(row)
                assert row['exact']
    assert before == fingerprint((positional, keywords))
    assert all(hashlib.sha256(Path(q).read_bytes()).hexdigest() == h for q, h in bindings.items())
    result = dict(exact=not differences, differing_fields=differences, rows=rows,
                  expected=fingerprint(expected), actual=fingerprint(actual), bindings=bindings,
                  captured_kernel_only=True, production_modified=False, full_pipeline_speedup=None)
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('exact', 'differing_fields', 'rows')}), flush=True)


if __name__ == '__main__':
    main()
