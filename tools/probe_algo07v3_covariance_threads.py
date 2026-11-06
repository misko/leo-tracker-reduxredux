"""External covariance-only threading trial; all other BLAS work stays serial."""

import argparse
import inspect
import json
import os
import time
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_blas_threads import digest, library_info
from profile_algo07v3_blas_primitives import configuration

from leo.analysis.localization_v3 import hierarchical


def candidate(configure, threads):
    source = inspect.getsource(hierarchical.hierarchical_bound)
    needle = 'cov = inv_root.T @ inv_root'
    if source.count(needle) != 1:
        raise ValueError('Review covariance multiplication boundary')
    changed = source.replace(needle, 'cov = _covariance(inv_root)')

    def covariance(root):
        try:
            configure('numpy', threads)
            return root.T @ root
        finally:
            configure('numpy', 1)

    scope = dict(vars(hierarchical), _covariance=covariance)
    exec(compile(changed, '<covariance-only-threads>', 'exec'), scope)
    return scope['hierarchical_bound'], changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threads', type=int, choices=(2, 3), required=True)
    args = parser.parse_args()
    if sorted(os.sched_getaffinity(0)) != [0, 1, 2]:
        parser.error('Requires CPU affinity 0,1,2')
    if args.output.resolve().is_relative_to('/mnt/qnap01'):
        parser.error('QNAP is read-only')
    libraries = library_info()
    if any(row['threads'] != 1 for row in libraries):
        parser.error('Start both BLAS libraries at one thread')
    args.output.mkdir(exist_ok=False)
    arrays, meta = args.capture / 'hardest.npz', args.capture / 'hardest.json'
    metadata = json.loads(meta.read_bytes())
    assert digest(arrays) == metadata['arrays_sha256']
    with np.load(arrays, allow_pickle=False) as data:
        positional = [data[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): data[k] for k in data.files
                         if k.startswith('keyword_')})
    paths = [Path(__file__), Path(hierarchical.__file__), arrays, meta,
             Path('tools/profile_algo07v3_blas_primitives.py'),
             Path('tools/probe_algo07v3_blas_threads.py'),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(path.resolve()): digest(path) for path in paths}
    operation, changed = candidate(configuration(libraries), args.threads)
    (args.output / 'candidate.py').write_text(changed)
    before = fingerprint((positional, keywords))
    expected = fingerprint(hierarchical.hierarchical_bound(*positional, **keywords))
    actual = fingerprint(operation(*positional, **keywords))
    differences = [key for key in expected if expected[key] != actual[key]]
    rows = []
    if not differences:
        for pair in range(6):
            order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
            for side in order:
                function = operation if side == 'candidate' else hierarchical.hierarchical_bound
                began, used = time.perf_counter(), time.process_time()
                values = [function(*positional, **keywords) for _ in range(3)]
                elapsed, cpu = time.perf_counter() - began, time.process_time() - used
                row = dict(pair=pair, side=side, seconds=elapsed / 3, cpu_seconds=cpu / 3,
                           calls=3, exact=all(fingerprint(v) == expected for v in values))
                rows.append(row)
                assert row['exact']
    assert library_info() == libraries
    assert fingerprint((positional, keywords)) == before
    assert all(digest(Path(p)) == sha for p, sha in bindings.items())
    result = dict(bindings=bindings, libraries=libraries, threads=args.threads,
                  expected=expected, actual=actual, differing_fields=differences,
                  exact=not differences, rows=rows, production_modified=False,
                  captured_kernel_only=True, full_pipeline_speedup=None)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(exact=not differences, differing_fields=differences, rows=rows)))


if __name__ == '__main__':
    main()
