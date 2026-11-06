"""Bounded external covariance experiments; never imported by runtime code."""

import argparse
import hashlib
import inspect
import json
import os
import time
from pathlib import Path

import numpy as np
from scipy.linalg.blas import dsyrk

from check_algo07v3_scan_likelihood import fingerprint
from leo.analysis.localization_v3 import hierarchical
from leo.operations.localization_v3_job import runtime_versions


def symmetric_product(value):
    # Return the same C layout as the original NumPy matrix product.
    result = np.array(dsyrk(1.0, value, trans=1, lower=0), order='C')
    lower = np.tril_indices(len(value), -1)
    result[lower] = result.T[lower]
    return result


def candidate(kind):
    source = inspect.getsource(hierarchical.hierarchical_bound)
    expression = 'cov = inv_root.T @ inv_root'
    if source.count(expression) != 1:
        raise ValueError('Covariance boundary changed')
    if kind == 'workspace':
        declaration = "inverse_work = np.empty((width, width), order='F')"
        if source.count(declaration) != 1:
            raise ValueError('Workspace boundary changed')
        changed = source.replace(declaration, declaration +
                                 '\n    covariance_work = np.empty((width, width))')
        changed = changed.replace(expression,
                                  'cov = np.matmul(inv_root.T, inv_root, out=covariance_work)')
    elif kind == 'symmetric':
        changed = source.replace(expression, 'cov = _symmetric_product(inv_root)')
    else:
        raise ValueError(kind)
    scope = dict(vars(hierarchical), _symmetric_product=symmetric_product)
    exec(compile(changed, '<external-covariance-probe>', 'exec'), scope)
    return scope['hierarchical_bound'], source, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    meta_path = args.capture / 'hardest.json'
    raw_path = args.capture / 'hardest.npz'
    metadata = json.loads(meta_path.read_bytes())
    if hashlib.sha256(raw_path.read_bytes()).hexdigest() != metadata['arrays_sha256']:
        raise ValueError('Capture changed')
    with np.load(raw_path, allow_pickle=False) as saved:
        positional = [saved[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): saved[k]
                         for k in saved.files if k.startswith('keyword_')})
    paths = [Path(__file__), Path(hierarchical.__file__), meta_path, raw_path,
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    expected = fingerprint(hierarchical.hierarchical_bound(*positional, **keywords))
    before = fingerprint((positional, keywords))
    results = []
    for kind in ('workspace', 'symmetric'):
        operation, original, changed = candidate(kind)
        (args.output / f'{kind}.py').write_text(changed)
        (args.output / 'baseline.py').write_text(original)
        actual = operation(*positional, **keywords)
        exact = fingerprint(actual) == expected
        result = dict(kind=kind, exact=exact, rows=[])
        # A failed exactness check is a result, not permission for timing claims.
        if exact:
            for pair in range(6):
                order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
                for side in order:
                    function = hierarchical.hierarchical_bound if side == 'baseline' else operation
                    began, cpu = time.perf_counter(), time.process_time()
                    values = [function(*positional, **keywords) for _ in range(3)]
                    elapsed, used = time.perf_counter() - began, time.process_time() - cpu
                    row = dict(pair=pair, side=side, seconds=elapsed / 3,
                               cpu_seconds=used / 3, calls=3,
                               exact=all(fingerprint(v) == expected for v in values))
                    result['rows'].append(row)
                    if not row['exact']:
                        raise ValueError('Timed call changed output')
        result['unchanged_inputs'] = fingerprint((positional, keywords)) == before
        if not result['unchanged_inputs']:
            raise ValueError('Input mutated')
        results.append(result)
        (args.output / f'{kind}.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result), flush=True)
    if not all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items()):
        raise ValueError('Sources changed during experiment')
    (args.output / 'result.json').write_text(json.dumps(dict(
        cases=results, bindings=bindings, runtime=runtime_versions(),
        runtime_modified=False, full_pipeline_speedup=None), indent=2) + '\n')


if __name__ == '__main__':
    main()
