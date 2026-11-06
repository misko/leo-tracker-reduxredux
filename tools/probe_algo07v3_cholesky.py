"""Compare direct LAPACK Cholesky with NumPy inside the complete likelihood.

External experiment only. A mathematically equivalent factorization must still
pass byte-level complete-result comparison before any timing or integration.
"""

import argparse
import hashlib
import inspect
import json
import os
import time
from pathlib import Path

import algo07v3_precholesky_hierarchical_oracle as hierarchical
import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from scipy.linalg.lapack import dpotrf


def root(gram):
    if not len(gram):
        return np.linalg.cholesky(gram)
    factor, info = dpotrf(gram, lower=1, clean=1)
    if info != 0:
        raise np.linalg.LinAlgError('Matrix is not positive definite')
    return np.ascontiguousarray(factor)


def candidate():
    source = inspect.getsource(hierarchical.hierarchical_bound)
    before = 'root = np.linalg.cholesky(gram)'
    if source.count(before) != 1:
        raise ValueError('Review changed Cholesky boundary')
    changed = source.replace(before, 'root = _root(gram)')
    scope = dict(vars(hierarchical), _root=root)
    exec(compile(changed, '<direct-lapack-cholesky>', 'exec'), scope)
    return scope['hierarchical_bound'], source, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    metadata = json.loads((args.capture / 'hardest.json').read_bytes())
    capture = args.capture / 'hardest.npz'
    assert hashlib.sha256(capture.read_bytes()).hexdigest() == metadata['arrays_sha256']
    with np.load(capture) as data:
        arguments = [data[f'argument_{n}'].copy() for n in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): data[k].copy()
                         for k in data.files if k.startswith('keyword_')})
    operation, original, changed = candidate()
    (args.output / 'original.py').write_text(original)
    (args.output / 'candidate.py').write_text(changed)
    paths = [Path(__file__), Path(hierarchical.__file__), capture,
             args.capture / 'hardest.json', Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    before = fingerprint((arguments, keywords))
    expected = hierarchical.hierarchical_bound(*arguments, **keywords)
    actual = operation(*arguments, **keywords)
    differences = [k for k in expected if fingerprint(expected[k]) != fingerprint(actual[k])]
    rows = []
    if not differences:
        for pair in range(5):
            order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
            for side in order:
                function = hierarchical.hierarchical_bound if side == 'baseline' else operation
                began, cpu = time.perf_counter(), time.process_time()
                result = function(*arguments, **keywords)
                elapsed, used = time.perf_counter() - began, time.process_time() - cpu
                assert fingerprint(result) == fingerprint(expected)
                rows.append(dict(pair=pair, side=side, seconds=elapsed, cpu_seconds=used))
    assert before == fingerprint((arguments, keywords))
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    receipt = dict(exact=not differences, differing_fields=differences, rows=rows,
                    expected=fingerprint(expected), actual=fingerprint(actual),
                    bindings=bindings, production_modified=False,
                    captured_kernel_only=True, full_pipeline_speedup=None)
    (args.output / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(exact=not differences, differing_fields=differences, rows=rows)))


if __name__ == '__main__':
    main()
