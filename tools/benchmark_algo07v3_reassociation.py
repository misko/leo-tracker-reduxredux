"""Observe exact alternating reassociation screens inside a fresh native run.

The full run is instrumented and is not a complete-path speed benchmark.
"""

import argparse
import cProfile
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import algo07v3_prereassociation_geometry_oracle as oracle
from benchmark_algo07v3_screen_geometry import trials
from profile_algo07v3 import resources, timed

from leo.cli.algo07v3 import supervise, worker, write


def observed_worker(root, repeats):
    from leo.analysis.localization_v3 import reassociation_admission as admission
    from leo.application import localization_v3 as policy

    original_screen, original_conservative = admission.screen, policy.refit_initial_position
    screens, conservative = [], []

    def screen(*args):
        # The untimed original invocation warms the live context and supplies
        # the same candidate result the uninstrumented worker would consume.
        expected = original_screen(*args)
        affinity = os.sched_getaffinity(0)
        try:
            os.sched_setaffinity(0, {min(affinity)})
            before = resources()
            rows = trials(dict(baseline=oracle.screen, candidate=original_screen),
                          args, expected, repeats)
            screens.append(dict(norad=int(args[1]), rows=rows, exact=True,
                                catalogue_count=len(args[2]),
                                resources_start=before, resources_end=resources(),
                                affinity=sorted(os.sched_getaffinity(0))))
            write(root / 'screens.json', screens)
            print(json.dumps(dict(event='screen_benchmark', norad=int(args[1]),
                                  exact=True, executions=len(rows))), flush=True)
        finally:
            os.sched_setaffinity(0, affinity)
        return expected

    def refit(*args, **kwargs):
        profile = cProfile.Profile()
        try:
            return timed(lambda: profile.runcall(original_conservative, *args, **kwargs),
                         conservative, 'conservative')
        finally:
            profile.dump_stats(str(root / 'conservative.pstats'))
            write(root / 'conservative.json', conservative)

    admission.screen, policy.refit_initial_position = screen, refit
    try:
        return worker(root / 'request.json', root / 'worker.json', False)
    finally:
        admission.screen, policy.refit_initial_position = original_screen, original_conservative


def launch(args):
    from leo.operations.localization_v3_job import runtime_versions, validate_request

    if not 1 <= args.repeats <= 5:
        raise ValueError('Use one to five alternating pairs')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        raise ValueError('Pin OPENBLAS_NUM_THREADS=1 before starting Python')
    request = validate_request(json.loads(args.request.read_bytes()))
    if request['runtime'] != runtime_versions():
        raise ValueError('Match the bound numerical runtime')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(parents=True, exist_ok=False)
    write(root / 'request.json', dict(request, output_root=str(root / 'publication')))
    files = [*Path('src').rglob('*.py'), Path(__file__), Path(oracle.__file__),
             Path('tools/benchmark_algo07v3_screen_geometry.py'),
             Path('tools/profile_algo07v3.py'), root / 'request.json']
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if bindings[str(Path(oracle.__file__).resolve())] != (
            '1a4bdceb73c75a3638c63f0fff74ea34cf1a5b4932c54f9fd29f1cca102b8750'):
        raise ValueError('Frozen screen oracle differs')
    write(root / 'plan.json', dict(bindings=bindings, timeout_seconds=args.timeout,
                                   repeats=args.repeats, affinity=sorted(os.sched_getaffinity(0)),
                                   blas_threads=1, production_modified=False))
    write(root / 'resources-start.json', resources())
    began = time.perf_counter()
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker', str(root),
               '--repeats', str(args.repeats)]
    environment = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
                       MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    with (root / 'worker.log').open('xb') as log:
        outcome = supervise(command, log=log, timeout=args.timeout, environment=environment)
    changed = [p for p, sha in bindings.items()
               if hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha]
    result_path = root / 'worker.json'
    result = json.loads(result_path.read_bytes()) if result_path.exists() else None
    write(root / 'resources-end.json', resources())
    write(root / 'benchmark.json', dict(
        process=outcome, worker=result, changed_sources=changed,
        overall_instrumented_seconds=time.perf_counter() - began,
        full_pipeline_speed_benchmark=False, production_modified=False,
        scope='Fresh native run with warmed alternating screens and conservative cProfile',
    ))
    return 0 if (outcome['returncode'] == 0 and result and
                 result['status'] == 'complete' and not changed) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timeout', type=float, default=1200)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return observed_worker(args.worker, args.repeats)
    if not args.request or not args.output:
        parser.error('--request and --output required')
    return launch(args)


if __name__ == '__main__':
    raise SystemExit(main())
