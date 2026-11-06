"""External ordered phase-chunk concurrency probe; never changes BLAS threads."""

import argparse
import ast
import hashlib
import inspect
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_blas_threads import library_info
from probe_algo07v3_shared_lu import cpu

from leo.analysis.localization_v3 import joint_density


def ordered_chunks(function, starts, *, workers):
    if workers not in (1, 2, 3):
        raise ValueError('One to three CPU slots required')
    starts = list(starts)
    if len(starts) <= 1 or workers == 1:
        yield from map(function, starts)
        return
    with ThreadPoolExecutor(max_workers=min(workers, len(starts))) as executor:
        # map yields in input order, preserving equal-score MAP tie breaking.
        yield from executor.map(function, starts)


def candidate(*, workers, source=None):
    if workers not in (1, 2, 3):
        raise ValueError('One to three CPU slots required')
    source = source or inspect.getsource(joint_density.two_family_phase_evidence)
    tree = ast.parse(source)
    fn, = tree.body
    loops = [n for n in fn.body if isinstance(n, ast.For)
             and ast.unparse(n.iter) == 'range(0, counts[0], rows_per_chunk)']
    if len(loops) != 1:
        raise ValueError('Review changed chunk boundary')
    loop = loops[0]
    writes = [n for n in loop.body if isinstance(n, ast.Assign)
              and ast.unparse(n.targets[0]) == 'log_joint[start:end]']
    expected = ('if score > best:\n    best = score\n'
                '    best_coeff = coefficient.reshape(-1, d1 + d2)[flat].copy()')
    if len(writes) != 1 or ast.unparse(loop.body[-1]) != expected:
        raise ValueError('Review changed result/reduction boundary')
    body = [n for n in loop.body[:-1] if n is not writes[0]]
    body += ast.parse('return start, end, joint, score, '
                      'coefficient.reshape(-1, d1 + d2)[flat].copy()').body
    chunk = ast.parse('def evaluate_chunk(start): pass').body[0]
    chunk.body = body
    collect = ast.parse('''
for start, end, joint, score, coefficient in _map_chunks(
        evaluate_chunk, range(0, counts[0], rows_per_chunk)):
    log_joint[start:end] = joint
    if score > best:
        best = score
        best_coeff = coefficient
''').body[0]
    index = fn.body.index(loop)
    fn.body[index:index + 1] = [chunk, collect]
    tree = ast.fix_missing_locations(tree)

    def mapper(function, starts):
        return ordered_chunks(function, starts, workers=workers)

    scope = dict(vars(joint_density), _map_chunks=mapper)
    exec(compile(tree, '<ordered-phase-chunks-probe>', 'exec'), scope)
    return scope['two_family_phase_evidence'], ast.unparse(tree)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, choices=[2, 3], required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01') or sorted(os.sched_getaffinity(0)) != [0, 1, 2]:
        parser.error('Local output and exactly CPU slots 0,1,2 required')
    pools = library_info()
    if any(p['threads'] != 1 for p in pools):
        raise ValueError('All loaded BLAS providers must retain one thread')
    root.mkdir(exist_ok=False)
    fn, source = candidate(workers=args.workers)
    (root / 'candidate.py').write_text(source + '\n')
    paths = [Path(__file__), Path(joint_density.__file__), args.fixture,
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/probe_algo07v3_shared_lu.py'), root / 'candidate.py',
             Path('tools/probe_algo07v3_blas_threads.py'),
             *[Path(p['path']) for p in pools]]
    pins = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (root / 'plan.json').write_text(json.dumps(dict(
        bindings=pins, workers=args.workers, pools=pools, affinity=sorted(os.sched_getaffinity(0)),
        scope='captured complete kernel; no full-worker qualification'), indent=2))
    with np.load(args.fixture, allow_pickle=False) as data:
        inputs = [[data[f'{name}_{i}'] for i in range(2)]
                  for name in ('observed', 'means', 'modes', 'log_priors', 'visible')]
        inputs.insert(2, data['base_covariance'])
    before, rows = fingerprint(inputs), []
    for mode in (True, False):
        reference = None
        for repeat in range(6):
            order = ('baseline', 'candidate') if repeat % 2 == 0 else ('candidate', 'baseline')
            for side in order:
                function = joint_density.two_family_phase_evidence if side == 'baseline' else fn
                start, used = time.perf_counter(), cpu()
                result = function(*inputs, optimize_contractions=mode)
                wall, used = time.perf_counter() - start, cpu() - used
                signature = fingerprint(result)
                if reference is None:
                    reference = signature
                rows.append(dict(optimized=mode, repeat=repeat, side=side, seconds=wall,
                                 cpu_seconds=used, exact=signature == reference))
                (root / 'rows.json').write_text(json.dumps(rows, indent=2))
                print(json.dumps(rows[-1]), flush=True)
                if signature != reference or fingerprint(inputs) != before:
                    raise ValueError('Complete kernel or input bytes changed')
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in pins.items()):
        raise ValueError('Source or fixture binding changed')
    if library_info() != pools:
        raise ValueError('BLAS provider or thread setting changed')
    (root / 'result.json').write_text(json.dumps(dict(
        rows=rows, exact=True, input_fingerprint=before, bindings=pins,
        native_qualified=False, production_modified=False), indent=2))


if __name__ == '__main__':
    main()
