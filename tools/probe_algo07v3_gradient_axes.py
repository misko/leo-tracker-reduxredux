"""External two-axis finite-difference experiment; no nested production workers.

Measure complete training fits before considering a runtime execution port.
"""

import argparse
import ast
import hashlib
import inspect
import json
import os
import statistics
import time
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_annotation_arms import fold_inputs, load_context
from profile_algo07v3 import cpu, resources

from leo.analysis.localization_v3 import position, prediction
from leo.analysis.localization_v3.recovery_partitions import planned_split
from leo.analysis.research import continuous_curve_fit
from leo.operations.localization_v3_job import runtime_versions
from leo.operations.localization_v3_parallel import _ordered


def columns(residual, x, lo, hi, step):
    pairs = []
    for k in range(len(x)):
        a, b = x.copy(), x.copy()
        a[k], b[k] = max(lo[k], x[k] - step), min(hi[k], x[k] + step)
        pairs.append((b, a))
    if len(pairs) != 2:
        raise ValueError('The external prototype is restricted to two position axes')
    values = _ordered(lambda pair: (residual(pair[0]), residual(pair[1])), pairs)
    return [(value[0] - value[1]) / (pair[0][k] - pair[1][k])
            for k, (value, pair) in enumerate(zip(values, pairs, strict=True))]


def transform():
    source = inspect.getsource(continuous_curve_fit.bounded_gauss_newton)
    tree = ast.parse(source)
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.For)
             and ast.unparse(n.target) == 'k' and ast.unparse(n.iter) == 'range(len(x))']
    if len(loops) != 1:
        raise ValueError('Review original finite-difference boundaries')
    loop = loops[0]
    expected = ('columns.append((residual(b) - residual(a)) / (b[k] - a[k]))',
                'evaluations += 2')
    if tuple(ast.unparse(n) for n in loop.body[-2:]) != expected:
        raise ValueError('Original gradient arithmetic changed')
    parent = next(n for n in ast.walk(tree) if hasattr(n, 'body') and loop in n.body)
    index = parent.body.index(loop)
    parent.body[index:index + 1] = ast.parse(
        'columns = _columns(residual, x, lo, hi, step)\nevaluations += 2 * len(x)').body
    tree = ast.fix_missing_locations(tree)
    scope = dict(vars(continuous_curve_fit), _columns=columns)
    exec(compile(tree, '<parallel-gradient-axes>', 'exec'), scope)
    return scope['bounded_gauss_newton'], source, ast.unparse(tree)


def trial(context, keep, arm, operation):
    original = position.bounded_gauss_newton
    position.bounded_gauss_newton = operation
    before, began = cpu(), time.perf_counter()
    try:
        problem, x, meta = prediction.fit_training(
            context, context['node'], keep, arm, record_optimizer=True)
        elapsed, after = time.perf_counter() - began, cpu()
        signature = fingerprint(dict(x=x, meta=meta, reference=problem.reference,
                                     state=problem.state(x), calculate=problem.calculate(x)))
        return dict(seconds=elapsed, self_cpu_seconds=after[0] - before[0],
                    children_cpu_seconds=after[1] - before[1], signature=signature)
    finally:
        position.bounded_gauss_newton = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, choices=(1, 2, 3), default=1)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 3:
        parser.error('Pin three CPUs and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    request = json.loads(args.request.read_bytes())
    assert request['runtime'] == runtime_versions()
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/probe_algo07v3_annotation_arms.py'), Path('tools/profile_algo07v3.py'),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    candidate, original, changed = transform()
    (args.output / 'original.py').write_text(original)
    (args.output / 'candidate.py').write_text(changed)
    (args.output / 'plan.json').write_text(json.dumps(dict(
        bindings=bindings, affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
        repeats=args.repeats, rounds=5, iterations=48, target=1, fold=1,
        production_modified=False, runtime_modified=False), indent=2) + '\n')
    rows = []
    for arm_index, arm in enumerate(('c0', 'fitted_c')):
        expected = None
        for pair in range(args.repeats):
            order = ('baseline', 'candidate') if (pair + arm_index) % 2 == 0 else (
                'candidate', 'baseline')
            for side in order:
                context, inventory, receipt = load_context(request)
                context, i, full, n, seed, plan = fold_inputs(context, inventory, 1, 1)
                train, _, split = planned_split(
                    full, context['scan'].tracks[i]['times'], seed, plan)
                keep = context['keep'] & train[:n]
                before = fingerprint((context['node'], keep))
                host_before = resources()
                result = trial(context, keep, arm, candidate if side == 'candidate' else
                               continuous_curve_fit.bounded_gauss_newton)
                assert before == fingerprint((context['node'], keep))
                if expected is None:
                    expected = result['signature']
                row = dict(arm=arm, side=side, pair=pair, **result,
                           exact=result['signature'] == expected, seed=int(seed), split=split,
                           training_points=int(keep.sum()), scientific_receipt=receipt,
                           resources_before=host_before, resources_after=resources())
                rows.append(row)
                (args.output / f'{arm}-{pair}-{side}.json').write_text(
                    json.dumps(row, indent=2) + '\n')
                print(json.dumps({k: row[k] for k in ('arm', 'side', 'pair', 'seconds',
                                                     'self_cpu_seconds', 'children_cpu_seconds',
                                                     'exact')}), flush=True)
                if not row['exact']:
                    raise ValueError('Complete training fit differs; retain failed trial')
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    means = {arm: {side: statistics.mean(r['seconds'] for r in rows
                                        if r['arm'] == arm and r['side'] == side)
                   for side in ('baseline', 'candidate')} for arm in ('c0', 'fitted_c')}
    (args.output / 'result.json').write_text(json.dumps(dict(
        means=means, exact=True, trials=len(rows), bindings=bindings,
        full_pipeline_speedup=None, runtime_modified=False), indent=2) + '\n')
    print(json.dumps(means), flush=True)


if __name__ == '__main__':
    main()
