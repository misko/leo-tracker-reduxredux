"""Sequential full-worker trials of an external, explicitly bound LU prototype."""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from compare_algo07v3_runs import compare
from probe_algo07v3_shared_lu import bind, candidate

from leo.analysis.localization_v3 import joint_density, joint_recovery
from leo.cli.algo07v3 import supervise, worker, write


def native_worker(root, side):
    factor, paths, command = bind(Path(__file__).with_name('native_batch_lu.c'), root)
    replacement, _ = candidate(factor)
    original = joint_density.two_family_phase_evidence
    implementation = original if side == 'baseline' else replacement
    calls = []

    def observed(*args, **kwargs):
        start = time.perf_counter()
        result = implementation(*args, **kwargs)
        calls.append(dict(seconds=time.perf_counter() - start,
                          optimized=kwargs.get('optimize_contractions', True),
                          phase_pairs=result['phase_pair_count']))
        return result

    pins = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write(root / 'backend.json', dict(bindings=pins, command=command, side=side))
    try:
        with patch.object(joint_density, 'two_family_phase_evidence', observed), \
                patch.object(joint_recovery, 'two_family_phase_evidence', observed):
            return worker(root / 'request.json', root / 'worker.json', False)
    finally:
        write(root / 'kernel-calls.json', calls)
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha
               for p, sha in pins.items()):
            raise ValueError('Native backend changed during execution')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--request', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--worker', type=Path)
    p.add_argument('--side', choices=['baseline', 'candidate'])
    args = p.parse_args()
    if args.worker:
        if args.side is None:
            p.error('Worker side required')
        raise SystemExit(native_worker(args.worker, args.side))
    if args.request is None or args.output is None:
        p.error('Request and fresh output required')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01') or sorted(os.sched_getaffinity(0)) != [0, 1, 2]:
        p.error('Local output and exactly CPU slots 0,1,2 required')
    root.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/probe_algo07v3_shared_lu.py'), Path('tools/native_batch_lu.c'),
             Path('tools/compare_algo07v3_runs.py'),
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/check_algo07v3_publication.py')]
    pins = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write(root / 'plan.json', dict(bindings=pins, sequence=['baseline', 'candidate'],
                                  timeout_per_side_seconds=1200, runtime_modified=False,
                                  external_backend=True, private_namespaces=False))
    for side in ('baseline', 'candidate'):
        folder = root / side
        folder.mkdir()
        request = json.loads(args.request.read_bytes())
        request['output_root'] = str(folder / 'publication')
        write(folder / 'request.json', request)
        with (folder / 'worker.log').open('xb') as log:
            process = supervise([sys.executable, '-B', str(Path(__file__).resolve()),
                                 '--worker', str(folder), '--side', side], log=log, timeout=1200,
                                environment=dict(os.environ, OPENBLAS_NUM_THREADS='1',
                                                 OMP_NUM_THREADS='1'))
        if process['returncode'] != 0:
            write(folder / 'supervisor.json', process)
            raise SystemExit(process['returncode'])
        outcome = json.loads((folder / 'worker.json').read_bytes())
        write(folder / 'supervisor.json', dict(process, worker=outcome,
                                              request_sha256=outcome['request_sha256']))
        if not json.loads((folder / 'kernel-calls.json').read_bytes()):
            raise ValueError('No joint density calls executed; candidate not exercised')
        print(json.dumps(dict(side=side, seconds=process['process_seconds'])), flush=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in pins.items())
    calls = [json.loads((root / side / 'kernel-calls.json').read_bytes())
             for side in ('baseline', 'candidate')]
    if ([{k: v for k, v in r.items() if k != 'seconds'} for r in calls[0]] !=
            [{k: v for k, v in r.items() if k != 'seconds'} for r in calls[1]]):
        raise ValueError('Joint-kernel call sequence differs')
    result = compare(SimpleNamespace(
        baseline_request=root / 'baseline/request.json',
        candidate_request=root / 'candidate/request.json',
        baseline_timing=root / 'baseline/supervisor.json',
        candidate_timing=root / 'candidate/supervisor.json',
        changed_module=[], added_module=[]))
    result.update(external_backend=True, production_modified=False)
    write(root / 'comparison.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
