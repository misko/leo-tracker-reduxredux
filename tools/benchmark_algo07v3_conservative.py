"""Alternate serial/concurrent conservative recovery over saved native preparation.

This is an exact prepared-stage benchmark, not a fresh inference/publication run.
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import algo07v3_preconservative_arms_oracle as oracle
from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3 import resources, timed

from leo.analysis.localization_v3 import conservative_recovery as candidate
from leo.analysis.localization_v3.region import SearchRegion
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.operations.localization_v3_job import runtime_versions
from leo.operations.localization_v3_parallel import map_initial_arms
from leo.storage.localization_v3 import LocalizationV3Store


def trials(functions, expected, repeats):
    if not 1 <= repeats <= 3:
        raise ValueError('Use one to three bounded alternating pairs')
    signature, rows = fingerprint(expected), []
    for pair in range(repeats):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            result = timed(functions[side], rows, side)
            if fingerprint(result) != signature:
                raise ValueError(f'Conservative science differs: pair {pair}, {side}')
            rows[-1].update(pair=pair, side=side, exact=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Fresh output required')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        parser.error('Pin OPENBLAS_NUM_THREADS=1 before starting Python')
    files = [*Path('src').rglob('*.py'), args.request, Path(__file__), Path(oracle.__file__),
             Path('tools/profile_algo07v3.py'), Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if bindings[str(Path(oracle.__file__).resolve())] != (
            '1980c199bb2a195e06e11d5bd4ebc56cf00ea30ee7c65bcaa21d17bc16544d5b'):
        raise ValueError('Frozen serial oracle differs')
    request = json.loads(args.request.read_bytes())
    if request['runtime'] != runtime_versions():
        raise ValueError('Match the frozen numerical runtime')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    evidence = saved['evidence']
    prepared, initial = evidence['preparation'], evidence['audit']['initial']
    expected = evidence['audit']['recovery']
    noise_bytes = (json.dumps(prepared['noise'], default=_json_value,
                             sort_keys=True, allow_nan=False) + '\n').encode()
    noise_sha = hashlib.sha256(noise_bytes).hexdigest()
    region = SearchRegion(tuple(request['search_center']))
    before = fingerprint((prepared, initial))

    def run(side):
        # Each trial gets fresh per-scan caches and exactly the same preparation.
        scan = _context(prepared, region, noise_sha, genuine=True)
        function = oracle.conservative_recovery if side == 'baseline' else (
            candidate.conservative_recovery)
        extra = {} if side == 'baseline' else dict(map_arms=map_initial_arms)
        return function(scan, initial, prepared['tracks']['observations'], **extra)

    began, host = time.perf_counter(), resources()
    rows = trials({side: lambda side=side: run(side) for side in ('baseline', 'candidate')},
                  expected, args.repeats)
    assert fingerprint((prepared, initial)) == before
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    result = dict(rows=rows, exact=True, scientific_receipt=saved['sha256'],
                  bindings=bindings, affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
                  overall_seconds=time.perf_counter() - began,
                  resources_start=host, resources_end=resources(),
                  full_pipeline_benchmark=False, production_modified=False)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'bindings'}, indent=2))


if __name__ == '__main__':
    main()
