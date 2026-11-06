"""Profile the owned native worker and its forked fits in a fresh private store.

Research-only instrumentation. Profiled latency is not a speed benchmark.
"""

import argparse
import cProfile
import dataclasses
import hashlib
import inspect
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


def frequencies(root=Path('/sys/devices/system/cpu'), cores=None):
    """Point samples, not averages or a correction factor for measured timings."""
    result = {}
    for core in sorted(os.sched_getaffinity(0) if cores is None else cores):
        path = root / f'cpu{core}/cpufreq/scaling_cur_freq'
        try:
            result[str(core)] = int(path.read_text().strip())
        except FileNotFoundError:
            result[str(core)] = None
    return result


def profile_item(item):
    if isinstance(item, (str, int, bool)):
        return item
    if (isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], int)
            and isinstance(item[1], str)
            and item[1] in ('c0', 'fitted_c')):
        return list(item)
    return repr(type(item))


def timed(operation, rows, name, *args, parent_stage=None):
    frequency_before = frequencies()
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
                         children_cpu_seconds=after[1] - before[1], completed=complete,
                         cpu_frequency_start_khz=frequency_before,
                         cpu_frequency_end_khz=frequencies(), parent_stage=parent_stage))


def fit_metadata(operation):
    name = getattr(operation, '__qualname__', type(operation).__name__)
    metadata = dict(operation=name)
    if 'fit_new.<locals>.fit_arm' in name:
        include = inspect.signature(operation).parameters['include'].default
        metadata['variant'] = 'new_family' if include else 'control'
    if 'fit_shared.<locals>.fit_arm' in name:
        extras = inspect.signature(operation).parameters['extras'].default
        metadata['extra_count'] = len(extras)
    return metadata


def profile_worker(root, only_stage=None, timers_only=False):
    from leo.application import localization_v3 as policy
    from leo.application import localization_v3_engine as engine
    from leo.operations import localization_v3_parallel as parallel

    original_run, original_invoke = engine.run_native, parallel._invoke
    original_timing = engine._Timing.run
    original_predictive = policy.recover_predictive_checkpoint
    rows, top_rows, worker_rows = [], [], []
    active = only_stage is None
    stage_name, top_stage = None, None

    def top_timing(timer, name, operation, expected=None):
        nonlocal top_stage
        previous, top_stage = top_stage, name
        try:
            return timed(original_timing, top_rows, name, timer, name, operation, expected)
        finally:
            top_stage = previous

    def recovery_stage(operation, name, *args):
        nonlocal stage_name
        previous, stage_name = stage_name, name
        try:
            return timed(operation, rows, name, name, *args, parent_stage=top_stage)
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
        child_profile = None
        if not timers_only:
            profile.disable()
            child_profile = cProfile.Profile()
            child_profile.enable()
        began, before = time.perf_counter(), cpu()
        try:
            return original_invoke(*args)
        finally:
            after, ended = cpu(), time.perf_counter()
            if child_profile is not None:
                child_profile.disable()
                child_profile.dump_stats(str(root / f'profile-{os.getpid()}.pstats'))
            operation, item = args[:2]
            metadata = dict(stage=stage_name, top_stage=top_stage,
                            **fit_metadata(operation), item=profile_item(item),
                            start=began, end=ended, seconds=ended-began,
                            self_cpu_seconds=after[0]-before[0],
                            children_cpu_seconds=after[1]-before[1],
                            task_window_includes_pipe_send=True,
                            timers_only=timers_only)
            write(root / f'profile-{os.getpid()}.json', metadata)

    def predictive(*args, **kwargs):
        nonlocal active
        active = True
        if not timers_only:
            profile.enable()
        try:
            return original_predictive(*args, **kwargs)
        finally:
            profile.disable()
            active = False

    engine.run_native, parallel._invoke = observed, invoke
    engine._Timing.run = top_timing
    profile = cProfile.Profile()
    if only_stage is None and not timers_only:
        profile.enable()
    elif only_stage is not None:
        policy.recover_predictive_checkpoint = predictive
    try:
        return timed(worker, worker_rows, 'worker',
                     root / 'request.json', root / 'worker.json', False)
    finally:
        profile.disable()
        if not timers_only:
            profile.dump_stats(str(root / f'profile-{os.getpid()}.pstats'))
        engine.run_native, parallel._invoke = original_run, original_invoke
        engine._Timing.run = original_timing
        policy.recover_predictive_checkpoint = original_predictive
        write(root / 'recovery-substages.json', rows)
        write(root / 'stage-resources.json', top_rows)
        write(root / 'worker-resources.json', worker_rows)


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
                                  timers_only=getattr(args, 'timers_only', False),
                                  production_modified=False))
    write(root / 'resources-start.json', resources())
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--worker', str(root)]
    if getattr(args, 'only_stage', None):
        command += ['--only-stage', args.only_stage]
    if getattr(args, 'timers_only', False):
        command += ['--timers-only']
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
    parser.add_argument('--timers-only', action='store_true',
                        help='Full stage/child wall and CPU accounting without cProfile tracing')
    args = parser.parse_args()
    if args.worker:
        return profile_worker(args.worker, args.only_stage, args.timers_only)
    if not args.request or not args.output:
        parser.error('--request and --output required')
    return launch(args)


if __name__ == '__main__':
    raise SystemExit(main())
