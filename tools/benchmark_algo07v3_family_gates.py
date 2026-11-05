"""Alternate complete recovery audits inside a fresh native pipeline run.

The instrumented overall clock includes repeated work and is not pipeline speed.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from copy import deepcopy
from pathlib import Path

import algo07v3_prerecovery_arms_oracle as oracle
from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3 import resources, timed

from leo.cli.algo07v3 import supervise, worker, write


def trials(functions, expected, repeats):
    if not 1 <= repeats <= 3:
        raise ValueError('Use one to three alternating pairs')
    signature, rows = fingerprint(expected), []
    for pair in range(repeats):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            result = timed(functions[side], rows, side)
            if fingerprint(result) != signature:
                raise ValueError(f'Complete audit differs: pair {pair}, {side}')
            rows[-1].update(pair=pair, side=side, exact=True)
    return rows


def observed_worker(root, repeats):
    from leo.analysis.localization_v3 import recovery_controller as controller

    original = controller.audit_inclusion
    audits = []

    def audit(*args, **kwargs):
        expected = original(*args, **kwargs)
        policy = args[0].get('numerical_policy')
        receipt = fingerprint(policy.receipt) if policy is not None else None

        def run(function):
            # Numerical replay owns ordered problem/refresh receipts. Repeated
            # benchmark trials must not append to the live pipeline's receipt.
            trial_args = args
            if policy is not None:
                trial_args = (dict(args[0], numerical_policy=deepcopy(policy)), *args[1:])
            return function(*trial_args, **kwargs)

        affinity = os.sched_getaffinity(0)
        try:
            os.sched_setaffinity(0, {min(affinity)})
            before = resources()
            rows = trials(dict(baseline=lambda: run(oracle.audit_inclusion),
                               candidate=lambda: run(original)), expected, repeats)
            if policy is not None and fingerprint(policy.receipt) != receipt:
                raise ValueError('Benchmark changed the live numerical receipt')
            audits.append(dict(shared=kwargs['shared'], rows=rows, exact=True,
                               resources_start=before, resources_end=resources(),
                               affinity=sorted(os.sched_getaffinity(0))))
            write(root / 'audits.json', audits)
            print(json.dumps(dict(event='audit_benchmark', index=len(audits) - 1,
                                  exact=True, executions=len(rows))), flush=True)
        finally:
            os.sched_setaffinity(0, affinity)
        return expected

    controller.audit_inclusion = audit
    try:
        return worker(root / 'request.json', root / 'worker.json', False)
    finally:
        controller.audit_inclusion = original


def launch(args):
    from leo.operations.localization_v3_job import runtime_versions, validate_request

    if not 1 <= args.repeats <= 3:
        raise ValueError('Use one to three alternating pairs')
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
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/profile_algo07v3.py'), root / 'request.json']
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if bindings[str(Path(oracle.__file__).resolve())] != (
            '93b7f6871b5884f5f09c994fe883799ed9d3192de9ef6e4677d640d02851e5bc'):
        raise ValueError('Frozen recovery oracle differs')
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
        scope='Fresh native run with warmed alternating complete recovery audits',
    ))
    return 0 if (outcome['returncode'] == 0 and result and
                 result['status'] == 'complete' and not changed) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timeout', type=float, default=900)
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
