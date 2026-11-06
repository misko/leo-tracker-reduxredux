"""Fresh native pair for direct-only ordered chunks, with actual-grid captures."""

import argparse
import hashlib
import json
import os
import resource
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from compare_algo07v3_runs import compare
from probe_algo07v3_blas_threads import library_info
from probe_algo07v3_joint_chunks import candidate

from leo.analysis.localization_v3 import joint_density, joint_recovery
from leo.cli.algo07v3 import supervise, worker, write


def choose(original, parallel, *, enabled, owner_pid, owner_thread, optimized):
    """The external caller grants three slots only to its serial main owner."""
    return (parallel if enabled and not optimized and os.getpid() == owner_pid
            and threading.get_ident() == owner_thread else original)


def native_worker(root, side):
    if sorted(os.sched_getaffinity(0)) != [0, 1, 2]:
        raise ValueError('Explicit ownership of three CPU slots required')
    libraries = library_info()
    if any(row['threads'] != 1 for row in libraries):
        raise ValueError('Actual BLAS providers must retain one thread')
    original = joint_density.two_family_phase_evidence
    parallel, transformed = candidate(workers=3)
    (root / 'candidate.py').write_text(transformed + '\n')
    owner_pid, owner_thread = os.getpid(), threading.get_ident()
    calls, captures = [], {}
    (root / 'captures').mkdir()
    write(root / 'backend.json', dict(
        libraries=libraries, owner_pid=owner_pid, owner_thread=owner_thread,
        affinity=sorted(os.sched_getaffinity(0)), side=side, direct_only=True,
        code_sha256=hashlib.sha256(transformed.encode()).hexdigest()))

    def observed(*args, **kwargs):
        optimized = kwargs.get('optimize_contractions', True)
        fn = choose(original, parallel, enabled=side == 'candidate', owner_pid=owner_pid,
                    owner_thread=owner_thread, optimized=optimized)
        began, used = time.perf_counter(), time.process_time()
        result = fn(*args, **kwargs)
        calls.append(dict(seconds=time.perf_counter() - began,
                          cpu_seconds=time.process_time() - used, optimized=optimized,
                          phase_pairs=result['phase_pair_count'], parallel=fn is parallel))
        # Symmetric capture on both sides, outside the kernel clock. Arrays are
        # real inputs from this native scan, not a resampled large-grid fixture.
        pairs = result['phase_pair_count']
        if not optimized and pairs > 1 and str(pairs) not in captures:
            if len(args) != 6:
                raise ValueError('Review changed joint input boundary')
            started = time.perf_counter()
            arrays = {'base_covariance': args[2]}
            for name, values in zip(('observed', 'means', 'modes', 'log_priors', 'visible'),
                                    (args[0], args[1], args[3], args[4], args[5]), strict=True):
                arrays.update({f'{name}_{i}': v for i, v in enumerate(values)})
            path = root / 'captures' / f'{pairs}.npz'
            np.savez(path, **arrays)
            captures[str(pairs)] = dict(input=fingerprint(args), result=fingerprint(result),
                                       sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                       seconds=time.perf_counter() - started)
        return result

    try:
        with patch.object(joint_density, 'two_family_phase_evidence', observed), \
                patch.object(joint_recovery, 'two_family_phase_evidence', observed):
            return worker(root / 'request.json', root / 'worker.json', False)
    finally:
        write(root / 'kernel-calls.json', calls)
        write(root / 'captures.json', captures)
        if library_info() != libraries:
            raise ValueError('Actual BLAS provider/thread settings changed')


def signature(calls):
    return [(r['optimized'], r['phase_pairs']) for r in calls]


def cpu():
    used = resource.getrusage(resource.RUSAGE_CHILDREN)
    return dict(user_seconds=used.ru_utime, system_seconds=used.ru_stime)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--side', choices=['baseline', 'candidate'])
    args = parser.parse_args()
    if args.worker:
        if args.side is None:
            parser.error('Explicit worker side required')
        raise SystemExit(native_worker(args.worker, args.side))
    if args.request is None or args.output is None:
        parser.error('Request and fresh output required')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01') or sorted(os.sched_getaffinity(0)) != [0, 1, 2]:
        parser.error('Local output and exactly CPU slots 0,1,2 required')
    root.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/probe_algo07v3_joint_chunks.py'),
             Path('tools/probe_algo07v3_shared_lu.py'),
             Path('tools/probe_algo07v3_blas_threads.py'),
             Path('tools/compare_algo07v3_runs.py'),
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/check_algo07v3_publication.py')]
    pins = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write(root / 'plan.json', dict(bindings=pins, sequence=['baseline', 'candidate'],
                                  timeout_per_side_seconds=1200, runtime_modified=False,
                                  external_prototype=True, capture_on_both_sides=True))
    for side in ('baseline', 'candidate'):
        folder = root / side
        folder.mkdir()
        request = json.loads(args.request.read_bytes())
        request['output_root'] = str(folder / 'publication')
        write(folder / 'request.json', request)
        before = cpu()
        with (folder / 'worker.log').open('xb') as log:
            process = supervise([sys.executable, '-B', str(Path(__file__).resolve()),
                                 '--worker', str(folder), '--side', side], log=log, timeout=1200,
                                environment=dict(os.environ, OPENBLAS_NUM_THREADS='1',
                                                 OMP_NUM_THREADS='1'))
        after = cpu()
        process['reaped_child_cpu'] = {k: after[k] - before[k] for k in before}
        if process['returncode'] != 0:
            write(folder / 'supervisor.json', process)
            raise SystemExit(process['returncode'])
        outcome = json.loads((folder / 'worker.json').read_bytes())
        write(folder / 'supervisor.json', dict(process, worker=outcome,
                                              request_sha256=outcome['request_sha256']))
        print(json.dumps(dict(side=side, process=process)), flush=True)
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in pins.items()):
        raise ValueError('Bound sources changed during native pair')
    calls = [json.loads((root / side / 'kernel-calls.json').read_bytes())
             for side in ('baseline', 'candidate')]
    if not calls[0] or signature(calls[0]) != signature(calls[1]):
        raise ValueError('Joint-kernel call sequence differs or is empty')
    if (any(r['parallel'] for r in calls[0]) or not any(r['parallel'] for r in calls[1])
            or any(r['parallel'] and r['optimized'] for r in calls[1])):
        raise ValueError('Direct-only candidate dispatch was not exercised correctly')
    captures = [json.loads((root / side / 'captures.json').read_bytes())
                for side in ('baseline', 'candidate')]
    if (not captures[0] or {k: (v['input'], v['result']) for k, v in captures[0].items()}
            != {k: (v['input'], v['result']) for k, v in captures[1].items()}):
        raise ValueError('Captured native inputs or complete kernel results differ')
    result = compare(SimpleNamespace(
        baseline_request=root / 'baseline/request.json',
        candidate_request=root / 'candidate/request.json',
        baseline_timing=root / 'baseline/supervisor.json',
        candidate_timing=root / 'candidate/supervisor.json', changed_module=[], added_module=[]))
    result.update(external_prototype=True, production_modified=False, direct_only=True)
    write(root / 'comparison.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
