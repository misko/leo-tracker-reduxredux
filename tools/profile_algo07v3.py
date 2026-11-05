"""Profile the owned native worker and its forked fits in a fresh private store.

Research-only instrumentation. Profiled latency is not a speed benchmark.
"""

import argparse
import cProfile
import dataclasses
import hashlib
import json
import os
import resource
import sys
import time
from pathlib import Path

from leo.cli.algo07v3 import supervise, worker, write


def resources():
    return dict(load=os.getloadavg(), cpu_pressure=Path('/proc/pressure/cpu').read_text(),
                memory_pressure=Path('/proc/pressure/memory').read_text())


def cpu():
    return tuple(sum((r.ru_utime, r.ru_stime)) for r in
                 (resource.getrusage(resource.RUSAGE_SELF),
                  resource.getrusage(resource.RUSAGE_CHILDREN)))


def profile_item(item):
    if isinstance(item, (str, int, bool)):
        return item
    if (isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], int)
            and isinstance(item[1], str)
            and item[1] in ('c0', 'fitted_c')):
        return list(item)
    return repr(type(item))


def timed(operation, rows, name, *args):
    began, before = time.perf_counter(), cpu()
    complete = False
    try:
        result = operation(*args)
        complete = True
        return result
    finally:
        after = cpu()
        rows.append(dict(name=name, seconds=time.perf_counter() - began,
                         self_cpu_seconds=after[0] - before[0],
                         children_cpu_seconds=after[1] - before[1], completed=complete))


def profile_worker(root, only_stage=None):
    from leo.application import localization_v3 as policy
    from leo.application import localization_v3_engine as engine
    from leo.operations import localization_v3_parallel as parallel

    original_run, original_invoke = engine.run_native, parallel._invoke
    original_predictive = policy.recover_predictive_checkpoint
    rows = []
    active = only_stage is None
    stage_name = None

    def recovery_stage(operation, name, *args):
        nonlocal stage_name
        previous, stage_name = stage_name, name
        try:
            return timed(operation, rows, name, name, *args)
        finally:
            stage_name = previous

    def observed(*args, **kwargs):
        ports = kwargs['execution']
        kwargs['execution'] = dataclasses.replace(
            ports,
            run_stage=lambda name, op: recovery_stage(ports.run_stage, name, op),
            run_gap_stage=lambda name, op, cap: recovery_stage(
                ports.run_gap_stage, name, op, cap),
        )
        return original_run(*args, **kwargs)

    def invoke(*args):
        if not active:
            return original_invoke(*args)
        # Replace the inherited parent's profiler, retaining separate child files.
        profile.disable()
        child_profile = cProfile.Profile()
        child_profile.enable()
        try:
            return original_invoke(*args)
        finally:
            child_profile.disable()
            child_profile.dump_stats(str(root / f'profile-{os.getpid()}.pstats'))
            operation, item = args[:2]
            name = getattr(operation, '__qualname__', type(operation).__name__)
            defaults = getattr(operation, '__defaults__', None)
            metadata = dict(stage=stage_name, operation=name,
                            item=profile_item(item))
            if 'fit_new.<locals>.fit_arm' in name and defaults:
                metadata['variant'] = 'new_family' if defaults[0] else 'control'
            if 'fit_shared.<locals>.fit_arm' in name and defaults:
                metadata['extra_count'] = len(defaults[-1])
            write(root / f'profile-{os.getpid()}.json', metadata)

    def predictive(*args, **kwargs):
        nonlocal active
        active = True
        profile.enable()
        try:
            return original_predictive(*args, **kwargs)
        finally:
            profile.disable()
            active = False

    engine.run_native, parallel._invoke = observed, invoke
    profile = cProfile.Profile()
    if only_stage is None:
        profile.enable()
    else:
        policy.recover_predictive_checkpoint = predictive
    try:
        return worker(root / 'request.json', root / 'worker.json', False)
    finally:
        profile.disable()
        profile.dump_stats(str(root / f'profile-{os.getpid()}.pstats'))
        engine.run_native, parallel._invoke = original_run, original_invoke
        policy.recover_predictive_checkpoint = original_predictive
        write(root / 'recovery-substages.json', rows)


def launch(args):
    from leo.operations.localization_v3_job import validate_request

    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    request = validate_request(json.loads(args.request.read_bytes()))
    root.mkdir(parents=True, exist_ok=False)
    request = dict(request, output_root=str(root / 'publication'))
    write(root / 'request.json', request)
    files = [*Path('src').rglob('*.py'), Path(__file__), root / 'request.json']
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    write(root / 'plan.json', dict(bindings=bindings, affinity=sorted(os.sched_getaffinity(0)),
                                  timeout_seconds=args.timeout, profiled=True,
                                  only_stage=getattr(args, 'only_stage', None),
                                  production_modified=False))
    write(root / 'resources-start.json', resources())
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker', str(root)]
    if getattr(args, 'only_stage', None):
        command += ['--only-stage', args.only_stage]
    environment = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
                       MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    with (root / 'worker.log').open('xb') as log:
        outcome = supervise(command, log=log, timeout=args.timeout, environment=environment)
    write(root / 'resources-end.json', resources())
    outcome_path = root / 'worker.json'
    result = json.loads(outcome_path.read_bytes()) if outcome_path.exists() else None
    changed = [p for p, sha in bindings.items()
               if hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha]
    stages = [json.loads(line) for line in (root / 'worker.log').read_text().splitlines()
              if line.startswith('{') and json.loads(line).get('event') == 'stage']
    write(root / 'profile.json', dict(
        process=outcome, worker=result, stages=stages, changed_sources=changed,
        timing_scope='Profiled native GLRT input through owned publication; excludes capture, '
                     'GLRT extraction and queue; substages overlap top-level stages',
        qualified_speedup=None,
    ))
    return 0 if (outcome['returncode'] == 0 and result and
                 result['status'] == 'complete' and not result['resumed'] and not changed) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timeout', type=float, default=1200)
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--only-stage', choices=['predictive'])
    args = parser.parse_args()
    if args.worker:
        return profile_worker(args.worker, args.only_stage)
    if not args.request or not args.output:
        parser.error('--request and --output required')
    return launch(args)


if __name__ == '__main__':
    raise SystemExit(main())
