"""Separate identity layout from inverse-workspace reuse on a bound hard call."""

import argparse
import hashlib
import inspect
import json
import os
import statistics
import time
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_lapack_workspace import candidate, reference


def layout_candidate():
    source = inspect.getsource(reference.hierarchical_bound)
    before = '    identity = np.eye(width)'
    if source.count(before) != 1:
        raise ValueError('Review changed identity construction')
    code = source.replace(before, "    identity = np.eye(width, order='F')")
    scope = dict(vars(reference))
    exec(compile(code, '<inverse-identity-layout>', 'exec'), scope)
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
    raw, meta = args.capture / 'hardest.npz', args.capture / 'hardest.json'
    metadata = json.loads(meta.read_bytes())
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == metadata['arrays_sha256']
    with np.load(raw, allow_pickle=False) as saved:
        positional = [saved[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): saved[k]
                         for k in saved.files if k.startswith('keyword_')})
    paths = [Path(__file__), Path(reference.__file__), raw, meta,
             Path('tools/probe_algo07v3_lapack_workspace.py'),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    layout, original, layout_source = layout_candidate()
    workspace, _, workspace_source = candidate('inverse')
    for name, code in (('baseline', original), ('fortran', layout_source),
                       ('workspace', workspace_source)):
        (root / f'{name}.py').write_text(code)
    variants = dict(baseline=reference.hierarchical_bound, fortran=layout, workspace=workspace)
    expected = fingerprint(variants['baseline'](*positional, **keywords))
    before = fingerprint((positional, keywords))
    orders = [('baseline', 'fortran', 'workspace'), ('workspace', 'fortran', 'baseline'),
              ('fortran', 'baseline', 'workspace')]
    rows = []
    for pair, order in enumerate(orders):
        for variant in order:
            began, used = time.perf_counter(), time.process_time()
            outputs = [variants[variant](*positional, **keywords) for _ in range(5)]
            elapsed, used = time.perf_counter()-began, time.process_time()-used
            exact = all(fingerprint(value) == expected for value in outputs)
            unchanged = fingerprint((positional, keywords)) == before
            row = dict(pair=pair, variant=variant, seconds=elapsed/5, cpu_seconds=used/5,
                       calls=5, exact=exact, unchanged_inputs=unchanged)
            rows.append(row)
            (root / f'{pair}-{variant}.json').write_text(json.dumps(row, indent=2)+'\n')
            assert exact and unchanged
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    means = {v: statistics.mean(r['seconds'] for r in rows if r['variant'] == v) for v in variants}
    result = dict(rows=rows, bindings=bindings, means=means, exact=True, kernel_only=True,
                  runtime_modified=False, full_pipeline_speedup=None)
    (root / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(means), flush=True)


if __name__ == '__main__':
    main()
