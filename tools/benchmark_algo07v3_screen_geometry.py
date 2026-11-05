"""Alternate complete residual screens over a public owned evidence export.

This component benchmark reuses prepared inputs; it is not a fresh pipeline run.
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import algo07v3_prescreen_geometry_oracle as oracle
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import residual_screen, screen_geometry
from leo.analysis.localization_v3.region import SearchRegion
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store


def trials(functions, args, expected, repeats):
    if not 1 <= repeats <= 5:
        raise ValueError('Use one to five bounded alternating pairs')
    signature = fingerprint(expected)
    rows = []
    for repeat in range(repeats):
        order = ['baseline', 'candidate'] if repeat % 2 == 0 else ['candidate', 'baseline']
        for side in order:
            began, cpu = time.perf_counter(), time.process_time()
            result = functions[side](*args)
            seconds, cpu_seconds = time.perf_counter() - began, time.process_time() - cpu
            if fingerprint(result) != signature:
                raise ValueError(f'Complete screen differs: pair {repeat}, {side}')
            rows.append(dict(pair=repeat, side=side, seconds=seconds, cpu_seconds=cpu_seconds,
                             exact=True))
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
    files = [args.request, Path(__file__), Path(oracle.__file__),
             Path(residual_screen.__file__), Path(screen_geometry.__file__)]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    assert bindings[str(Path(oracle.__file__).resolve())] == (
        'c605070f6fc7433c727c6e4df746f9766570bfa9b161c18c5dc6f7a6cbc5a9b4')
    request = json.loads(args.request.read_bytes())
    if runtime_versions() != request['runtime']:
        raise ValueError('Match the frozen numerical runtime before benchmarking')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    evidence = saved['evidence']
    packet = evidence['audit']['additional_recovery']['preflight']
    catalogue = evidence['catalogue']
    expected = evidence['audit']['residual_screen']['screen']
    before = fingerprint((packet, catalogue))
    started = time.perf_counter()
    functions = dict(baseline=oracle.screen_candidates,
                     candidate=residual_screen.screen_candidates)
    rows = trials(functions,
                  (packet, catalogue, SearchRegion(tuple(request['search_center']))),
                  expected, args.repeats)
    assert fingerprint((packet, catalogue)) == before
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    input_digest = hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()
    result = dict(rows=rows, input_fingerprint_sha256=input_digest,
                  scientific_receipt=saved['sha256'],
                  bindings=bindings, affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
                  overall_seconds=time.perf_counter() - started,
                  target_count=len(packet['targets']), catalogue_count=len(catalogue['elements']),
                  full_pipeline_benchmark=False, exact=True, production_modified=False)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
