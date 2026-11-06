"""External native comparison: parallel gradients only in the owning worker.

Owned sources and scientific policies remain unchanged. The experimental
function substitution and its routing are explicit bound measurement inputs.
"""

import argparse
import hashlib
import json
import multiprocessing
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from compare_algo07v3_runs import compare
from probe_algo07v3_gradient_axes import transform
from profile_algo07v3 import cpu, resources

from leo.analysis.localization_v3 import position
from leo.application import localization_v3_engine as engine
from leo.cli.algo07v3 import supervise, worker, write
from leo.contracts.digests import canonical_digest


@contextmanager
def routing(enabled, rows):
    original = position.bounded_gauss_newton
    original_timing = engine._Timing.run
    candidate, _, _ = transform()
    owner = os.getpid()
    current_stage = None

    def stage(timer, name, operation, expected=None):
        nonlocal current_stage
        previous, current_stage = current_stage, name
        try:
            return original_timing(timer, name, operation, expected)
        finally:
            current_stage = previous

    def routed(residual, initial, lower, upper, **kwargs):
        # Child fits retain their existing serial gradients. Do not create
        # nested workers beneath the three-slot annotation/arm executors.
        if os.getpid() != owner:
            return original(residual, initial, lower, upper, **kwargs)
        eligible = len(initial) == 2 and not multiprocessing.active_children()
        operation = candidate if enabled and eligible else original
        problem = getattr(residual, '__self__', None)
        residual_seconds = []

        def observed(x):
            before = time.perf_counter()
            value = residual(x)
            residual_seconds.append(time.perf_counter() - before)
            return value

        began, before = time.perf_counter(), cpu()
        complete, result = False, None
        try:
            result = operation(observed, initial, lower, upper, **kwargs)
            complete = True
            return result
        finally:
            after = cpu()
            rows.append(dict(
                stage=current_stage, parallel=bool(enabled and eligible), complete=complete,
                seconds=time.perf_counter() - began, self_cpu_seconds=after[0] - before[0],
                children_cpu_seconds=after[1] - before[1],
                fitted_c=getattr(problem, 'fitted_c', None),
                observations=len(problem.values) if problem is not None else None,
                parent_residual_calls=len(residual_seconds),
                parent_residual_seconds=sum(residual_seconds),
                first_residual_seconds=residual_seconds[0] if residual_seconds else None,
                evaluations=result['evaluations'] if complete else None))

    engine._Timing.run = stage
    position.bounded_gauss_newton = routed
    try:
        yield
    finally:
        engine._Timing.run = original_timing
        position.bounded_gauss_newton = original


def measured_worker(root, variant):
    rows = []
    try:
        with routing(variant == 'candidate', rows):
            return worker(root / 'request.json', root / 'worker.json', False)
    finally:
        write(root / 'fits.json', rows)


def launch(root, variant, entry_path=None):
    write(root / 'resources-start.json', resources())
    with (root / 'worker.log').open('xb') as log:
        outcome = supervise([sys.executable, '-B', str((entry_path or Path(__file__)).resolve()),
                             '--worker', str(root), '--variant', variant],
                            log=log, timeout=1200, environment=dict(
                                os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
                                PYTHONDONTWRITEBYTECODE='1'))
    write(root / 'resources-end.json', resources())
    result_path = root / 'worker.json'
    result = json.loads(result_path.read_bytes()) if result_path.exists() else None
    outcome.update(worker=result, request_sha256=canonical_digest(
        json.loads((root / 'request.json').read_bytes())))
    write(root / 'supervisor.json', outcome)
    return 0 if outcome['returncode'] == 0 and result and result['status'] == 'complete' else 1


def main(worker_operation=measured_worker, entry_path=None, runner_path=None, extra_paths=(),
         counter_events=()):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--launch', type=Path)
    parser.add_argument('--variant', choices=('baseline', 'candidate'))
    parser.add_argument('--candidate-first', action='store_true')
    args = parser.parse_args()
    if args.worker:
        return worker_operation(args.worker, args.variant)
    if args.launch:
        return launch(args.launch, args.variant, entry_path)
    if not args.request or not args.output:
        parser.error('--request and --output required')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    bundle = Path(request['native_input']['path']).parent
    runner = (runner_path or Path(
        'reports/2026_11_05_algo07v3_native_gradients/isolate.sh')).resolve()
    entry = (entry_path or Path(__file__)).resolve()
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__), runner, entry, *extra_paths,
             Path('tools/probe_algo07v3_gradient_axes.py'), Path('tools/profile_algo07v3.py'),
             Path('tools/compare_algo07v3_runs.py'), bundle / 'input-bindings.json']
    commands = {}
    for side in ('baseline', 'candidate'):
        target = root / side
        target.mkdir()
        write(target / 'request.json', dict(request, output_root=str(target / 'publication')))
        paths.append(target / 'request.json')
        commands[side] = ['/usr/bin/time', '-v', '-o', str(target / 'process-time.txt'),
                          'sh', str(runner), str(bundle), str(target), sys.executable, side]
        if counter_events:
            commands[side] = ['taskset', '-c', '0,1,2', 'perf', 'stat', '--json-output',
                              '-o', str(target/'counters.jsonl'), '-e', ','.join(counter_events),
                              '--', *commands[side]]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    order = ['candidate', 'baseline'] if args.candidate_first else ['baseline', 'candidate']
    write(root / 'plan.json', dict(bindings=bindings, commands=commands, order=order,
                                  cpus=[0, 1, 2], blas_threads=1, production_modified=False,
                                  external_function_substitution=True, profiled=False,
                                  hardware_counter_events=list(counter_events)))
    for side in order:
        print('Starting ' + side, flush=True)
        with (root / side / 'launch.log').open('xb') as log:
            subprocess.run(commands[side], stdout=log, stderr=subprocess.STDOUT, check=True)
        print('Completed ' + side, flush=True)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    comparison = compare(SimpleNamespace(
        baseline_request=root / 'baseline/request.json',
        candidate_request=root / 'candidate/request.json',
        baseline_timing=root / 'baseline/supervisor.json',
        candidate_timing=root / 'candidate/supervisor.json', changed_module=[], added_module=[]))
    comparison.update(external_function_substitution=True,
                      probe_sha256=bindings[str(entry)])
    write(root / 'comparison.json', comparison)
    print(json.dumps({k: comparison[k] for k in ('exact_owned_science_and_artifacts',
                                                'observed_process_seconds')}), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
