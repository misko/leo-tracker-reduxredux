"""External exact LAPACK workspace experiments on a bound hard likelihood call."""

import argparse
import hashlib
import inspect
import json
import os
import statistics
import time
from pathlib import Path

import algo07v3_preworkspace_hierarchical_oracle as reference
import numpy as np
from check_algo07v3_scan_likelihood import fingerprint


def candidate(variant):
    if variant not in ('lu', 'inverse', 'both'):
        raise ValueError('Unknown workspace experiment')
    source = inspect.getsource(reference.hierarchical_bound)
    code = source

    def replace(before, after):
        nonlocal code
        if code.count(before) != 1:
            raise ValueError('Review changed posterior boundary')
        code = code.replace(before, after)

    buffers = ''
    if variant in ('lu', 'both'):
        buffers += "    lu_work = np.empty((width, width), order='F')\n"
        replace('        lu, pivots, info = dgetrf(root) if width else (root, None, 0)',
                '''        if width:
            lu_work[...] = root
            lu, pivots, info = dgetrf(lu_work, overwrite_a=1)
        else:
            lu, pivots, info = root, None, 0''')
    if variant in ('inverse', 'both'):
        replace('    identity = np.eye(width)', "    identity = np.eye(width, order='F')")
        buffers += "    inverse_work = np.empty((width, width), order='F')\n"
        replace('            inv_root = _solve_factor(lu, pivots, identity)'
                ' if width else identity.copy()',
                '''            if width:
                inverse_work[...] = identity
                inv_root, info = dgetrs(lu, pivots, inverse_work, overwrite_b=1)
                if info:
                    raise np.linalg.LinAlgError(f"DGETRS failed: {info}")
            else:
                inv_root = identity.copy()''')
    replace('    def posterior(weight, precision, covariance):',
            buffers + '\n    def posterior(weight, precision, covariance):')
    scope = dict(vars(reference))
    exec(compile(code, f'<lapack-workspace-{variant}>', 'exec'), scope)
    return scope['hierarchical_bound'], source, code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    metadata = json.loads((args.capture / 'hardest.json').read_bytes())
    raw = args.capture / 'hardest.npz'
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == metadata['arrays_sha256']
    with np.load(raw, allow_pickle=False) as saved:
        positional = [saved[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): saved[k]
                         for k in saved.files if k.startswith('keyword_')})
    paths = [Path(__file__), Path(reference.__file__), raw, args.capture / 'hardest.json',
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    before = fingerprint((positional, keywords))
    expected = fingerprint(reference.hierarchical_bound(*positional, **keywords))
    rows = []
    for variant in ('lu', 'inverse', 'both'):
        operation, original, changed = candidate(variant)
        (root / 'original.py').write_text(original)
        (root / f'{variant}.py').write_text(changed)
        exact = fingerprint(operation(*positional, **keywords)) == expected
        (root / f'{variant}-exact.json').write_text(json.dumps(dict(exact=exact))+'\n')
        if not exact:
            raise ValueError(f'{variant} changed the complete likelihood')
        for pair in range(3):
            for side in (('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')):
                function = reference.hierarchical_bound if side == 'baseline' else operation
                began, used = time.perf_counter(), time.process_time()
                outputs = [function(*positional, **keywords) for _ in range(3)]
                elapsed, used = time.perf_counter()-began, time.process_time()-used
                exact = all(fingerprint(value) == expected for value in outputs)
                unchanged = before == fingerprint((positional, keywords))
                row = dict(variant=variant, pair=pair, side=side, seconds=elapsed/3,
                    cpu_seconds=used/3, calls=3, exact=exact, unchanged_inputs=unchanged)
                rows.append(row)
                (root / f'{variant}-{pair}-{side}.json').write_text(json.dumps(row, indent=2)+'\n')
                assert exact and unchanged
        means = {side: statistics.mean(r['seconds'] for r in rows
                                       if r['variant'] == variant and r['side'] == side)
                 for side in ('baseline', 'candidate')}
        print(json.dumps(dict(variant=variant, means=means, exact=True)), flush=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    result = dict(rows=rows, bindings=bindings, exact=True, runtime_modified=False,
                  shape=positional[1].shape, kernel_only=True, full_pipeline_speedup=None)
    (root / 'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
