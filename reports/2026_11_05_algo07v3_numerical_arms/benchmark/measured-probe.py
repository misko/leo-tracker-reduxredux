"""External complete-fit trials with ordered numerical-policy receipt merging.

Repeated trials run inside one fresh native execution. Its total clock includes
benchmark work and is not a complete-pipeline speed measurement.
"""

import argparse
import hashlib
import inspect
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

from benchmark_algo07v3_family_gates import trials
from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3 import resources

from leo.analysis.localization_v3 import recovery_controller as controller
from leo.analysis.localization_v3 import recovery_inclusion as inclusion
from leo.analysis.localization_v3.numerical_policy import NumericalPolicy
from leo.cli.algo07v3 import supervise, worker, write
from leo.operations.localization_v3_parallel import map_initial_arms


def receipt_map(context, operation, arms, mapper):
    policy = context.get('numerical_policy')
    if mapper is None or type(policy) is not NumericalPolicy:
        return list(map(operation, arms))
    before = deepcopy(policy.receipt)

    def execute(arm):
        local = deepcopy(policy)
        context['numerical_policy'] = local
        try:
            value = operation(arm)
            return value, local.receipt
        finally:
            context['numerical_policy'] = policy

    completed = list(mapper(execute, arms))
    if fingerprint(policy.receipt) != fingerprint(before):
        raise ValueError('Mapper mutated the owning numerical receipt')
    merged = deepcopy(before)
    lists = ('reference_updates', 'optimizer_calls')
    constant = set(before) - {*lists, 'problem_count'}
    for _, receipt in completed:
        if set(receipt) != set(before) or any(
                fingerprint(receipt[k]) != fingerprint(before[k]) for k in constant):
            raise ValueError('Numerical policy configuration changed in child')
        for key in lists:
            n = len(before[key])
            if fingerprint(receipt[key][:n]) != fingerprint(before[key]):
                raise ValueError('Child rewrote existing numerical receipt')
            merged[key].extend(deepcopy(receipt[key][n:]))
        count = receipt['problem_count']
        if type(count) is not int or count < before['problem_count']:
            raise ValueError('Child problem count is invalid')
        merged['problem_count'] += count - before['problem_count']
    policy.receipt.clear()
    policy.receipt.update(merged)
    return [value for value, _ in completed]


def transform(name):
    original = inspect.getsource(getattr(inclusion, name))
    old = 'mapper = map if d.get("numerical_policy") is not None else (map_arms or map)'
    if original.count(old) != 1:
        raise ValueError('Review numerical replay mapper before transforming')
    changed = original.replace(old, 'mapper = lambda operation, arms: '
                               '_receipt_map(d, operation, arms, map_arms)')
    scope = dict(vars(inclusion), _receipt_map=receipt_map)
    exec(compile(changed, '<numerical-receipt-arms>', 'exec'), scope)
    return scope[name], original, changed


def observed_worker(root, repeats):
    originals = {name: getattr(controller, name) for name in ('fit_new', 'fit_shared')}
    candidates = {name: transform(name)[0] for name in originals}
    records = []

    def wrapper(name):
        original, candidate = originals[name], candidates[name]

        def measured(context, *args, **kwargs):
            policy = context.get('numerical_policy')
            if policy is None:
                return original(context, *args, **kwargs)
            before = deepcopy(policy)
            expected = original(context, *args, **kwargs)
            after = deepcopy(policy.receipt)

            def run(function, mapper):
                local = deepcopy(before)
                value = function(dict(context, numerical_policy=local), *args,
                                 **dict(kwargs, map_arms=mapper))
                return dict(value=value, receipt=local.receipt)

            rows = trials(dict(baseline=lambda: run(original, None),
                               candidate=lambda: run(candidate, map_initial_arms)),
                          dict(value=expected, receipt=after), repeats)
            if fingerprint(policy.receipt) != fingerprint(after):
                raise ValueError('Repeated trials changed live policy')
            records.append(dict(kind=name, rows=rows, complete_result_and_receipt_exact=True))
            write(root / 'trials.json', records)
            print(json.dumps(dict(event='numerical_arm_trials', index=len(records) - 1,
                                  kind=name, executions=len(rows), exact=True)), flush=True)
            return expected
        return measured

    for name in originals:
        setattr(controller, name, wrapper(name))
    try:
        return worker(root / 'request.json', root / 'worker.json', False)
    finally:
        for name, function in originals.items():
            setattr(controller, name, function)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    parser.add_argument('--repeats', type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args()
    if args.worker:
        return observed_worker(args.worker, args.repeats)
    if not args.request or not args.output:
        parser.error('--request and --output required')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 3:
        parser.error('Pin three CPUs and one BLAS thread')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    write(root / 'request.json', dict(request, output_root=str(root / 'publication')))
    paths = [*Path('src').rglob('*.py'), Path(__file__), args.request, root / 'request.json',
             Path('tools/benchmark_algo07v3_family_gates.py'),
             Path('tools/check_algo07v3_scan_likelihood.py'), Path('tools/profile_algo07v3.py')]
    for name in ('fit_new', 'fit_shared'):
        _, original, changed = transform(name)
        (root / (name + '-original.py')).write_text(original)
        (root / (name + '-candidate.py')).write_text(changed)
        paths.extend([root / (name + '-original.py'), root / (name + '-candidate.py')])
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    write(root / 'plan.json', dict(bindings=bindings, cpus=sorted(os.sched_getaffinity(0)),
                                   blas_threads=1, repeats=args.repeats, timeout_seconds=1200,
                                   runtime_integrated=False, production_modified=False))
    write(root / 'resources-start.json', resources())
    with (root / 'worker.log').open('xb') as log:
        outcome = supervise([sys.executable, '-B', str(Path(__file__).resolve()),
                             '--worker', str(root), '--repeats', str(args.repeats)],
                            log=log, timeout=1200, environment=dict(os.environ))
    changed = [p for p, sha in bindings.items()
               if hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha]
    result = json.loads((root / 'worker.json').read_bytes()) if (root / 'worker.json').exists() else None
    write(root / 'resources-end.json', resources())
    write(root / 'benchmark.json', dict(process=outcome, worker=result, changed_sources=changed,
                                       full_pipeline_speed_benchmark=False))
    return 0 if outcome['returncode'] == 0 and result and not changed else 1


if __name__ == '__main__':
    raise SystemExit(main())
