"""External compiled ordered-scatter experiment; no runtime imports this module."""

import argparse
import ctypes
import hashlib
import inspect
import json
import os
import subprocess
import time
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import hierarchical as reference


def build(root):
    source = Path(__file__).with_name('algo07v3_ordered_scatter.c')
    library = root / 'ordered_scatter.so'
    command = ['cc', '-O3', '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra',
               '-Werror', '-shared', '-fPIC', str(source), '-o', str(library)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    version = subprocess.check_output(['cc', '--version'], text=True)
    metadata = dict(command=command, compiler=version,
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    binary_sha256=hashlib.sha256(library.read_bytes()).hexdigest())
    (root / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n')
    loaded = ctypes.CDLL(str(library.resolve()))
    operation = loaded.ordered_scatter
    real = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags=('C_CONTIGUOUS', 'ALIGNED'))
    integer = np.ctypeslib.ndpointer(dtype=np.intp, ndim=1, flags=('C_CONTIGUOUS', 'ALIGNED'))
    operation.argtypes = [real, ctypes.c_size_t, integer, integer, real, ctypes.c_size_t,
                          real, ctypes.c_size_t]
    operation.restype = ctypes.c_int

    def scatter(output, indices, groups, weights, values):
        if not output.flags.writeable:
            raise ValueError('Output must be writable')
        if len(indices) != len(groups) or len(indices) != len(values):
            raise ValueError('Index, group and value lengths must match')
        if any(np.shares_memory(output, a) for a in (indices, groups, weights, values)):
            raise ValueError('Output must not alias inputs')
        if operation(output, len(output), indices, groups, weights, len(weights),
                     values, len(values)):
            raise ValueError('Index or group outside bounds')

    return scatter


def candidate(scatter):
    original = inspect.getsource(reference.hierarchical_bound)
    changed = original
    for expression in (
        'np.add.at(gram.ravel(), matrix_indices, block_weight[matrix_groups] * matrices)',
        'np.add.at(rhs, rhs_indices, block_weight[rhs_groups] * right_sides)',
    ):
        assert changed.count(expression) == 1
    changed = changed.replace(
        'np.add.at(gram.ravel(), matrix_indices, block_weight[matrix_groups] * matrices)',
        '_scatter(gram.ravel(), matrix_indices, matrix_groups, block_weight, matrices)')
    changed = changed.replace(
        'np.add.at(rhs, rhs_indices, block_weight[rhs_groups] * right_sides)',
        '_scatter(rhs, rhs_indices, rhs_groups, block_weight, right_sides)')
    scope = dict(vars(reference), _scatter=scatter)
    exec(compile(changed, '<external-ordered-assembly>', 'exec'), scope)
    return scope['hierarchical_bound'], original, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    metadata = json.loads((args.capture / 'hardest.json').read_bytes())
    raw = args.capture / 'hardest.npz'
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == metadata['arrays_sha256']
    with np.load(raw, allow_pickle=False) as saved:
        positional = [saved[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): saved[k]
                         for k in saved.files if k.startswith('keyword_')})
    function, original, changed = candidate(build(args.output))
    paths = [Path(__file__), Path(__file__).with_name('algo07v3_ordered_scatter.c'),
             Path(reference.__file__), raw, args.capture / 'hardest.json',
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (args.output / 'original.py').write_text(original)
    (args.output / 'candidate.py').write_text(changed)
    expected = fingerprint(reference.hierarchical_bound(*positional, **keywords))
    before = fingerprint((positional, keywords))
    rows = []
    for pair in range(6):
        for side in (('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')):
            operation = reference.hierarchical_bound if side == 'baseline' else function
            began, used = time.perf_counter(), time.process_time()
            values = [operation(*positional, **keywords) for _ in range(5)]
            elapsed, used = time.perf_counter() - began, time.process_time() - used
            exact = all(fingerprint(v) == expected for v in values)
            row = dict(pair=pair, side=side, seconds=elapsed / 5, cpu_seconds=used / 5,
                       calls=5, exact=exact, unchanged_inputs=before == fingerprint(
                           (positional, keywords)))
            rows.append(row)
            (args.output / f'{pair}-{side}.json').write_text(json.dumps(row, indent=2) + '\n')
            print(json.dumps(row), flush=True)
            assert row['exact'] and row['unchanged_inputs']
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    result = dict(rows=rows, bindings=bindings, runtime_modified=False,
                  full_pipeline_speedup=None, exact=True)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
