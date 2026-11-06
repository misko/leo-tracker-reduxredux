"""External experiment: queue unchanged initial branch/arm fits on three workers.

No runtime source changes. Full cold search, all hypotheses and both zero-phase
controls must match the saved owned initial result in every alternating trial.
"""
import argparse
import ast
import copy
import hashlib
import inspect
import json
import os
import time
from pathlib import Path

import algo07v3_preinitialqueue_oracle as initial_search
import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_discovery_schedule import cpu_seconds, host_resources

from leo.analysis.localization_v3.region import SearchRegion
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.operations.localization_v3_job import runtime_versions
from leo.operations.localization_v3_parallel import map_annotation_training, map_initial_arms
from leo.storage.localization_v3 import LocalizationV3Store


def cpu_policy():
    """Endpoint observations, not continuous or attributable clock-frequency evidence."""
    result = {}
    for cpu in sorted(os.sched_getaffinity(0)):
        root = Path(f'/sys/devices/system/cpu/cpu{cpu}')
        fields = {}
        for name in ('cpufreq/scaling_cur_freq', 'cpufreq/scaling_governor',
                     'topology/thread_siblings_list'):
            path = root / name
            fields[name] = path.read_text().strip() if path.exists() else None
        result[str(cpu)] = fields
    return result


def transform(mapper=map_annotation_training):
    source = inspect.getsource(initial_search.initial_search)
    tree = ast.parse(source)
    body = tree.body[0].body
    loops = [n for n in body if isinstance(n, ast.For)
             and ast.unparse(n.target) == '(index, (score, node))']
    if len(loops) != 1:
        raise ValueError('Initial branch loop changed; review extraction')
    loop = loops[0]
    assignment = loop.body[1]
    if (ast.unparse(loop.iter) != 'enumerate(selected)'
            or not isinstance(assignment, ast.Assign)
            or ast.unparse(assignment.targets[0]) != 'mapped'
            or not isinstance(assignment.value, ast.Call)
            or len(assignment.value.args) != 2
            or not isinstance(assignment.value.args[0], ast.Lambda)
            or ast.unparse(assignment.value.args[1]) != 'arms'):
        raise ValueError('Independent arm dispatch changed')
    helper = ast.parse('def fit_task(task):\n    index, arm = task\n'
                       '    score, node = selected[index]').body[0]
    helper.body.append(ast.Return(copy.deepcopy(assignment.value.args[0].body)))
    setup = ast.parse(
        "tasks = [(i, a) for i in range(len(selected)) for a in ('c0', 'fitted_c')]\n"
        'trained = dict(zip(tasks, _map_pairs(fit_task, tasks), strict=True))').body
    at = body.index(loop)
    body[at:at] = [helper, *setup]
    assignment.value = ast.parse('[trained[index, a] for a in arms]', mode='eval').body
    body[1:1] = ast.parse(
        'if on_branch is not None or branch_budget > 3:\n'
        "    raise ValueError('External queue probe requires no callback and <=3 branches')"
    ).body
    tree = ast.fix_missing_locations(tree)
    scope = dict(vars(initial_search), _map_pairs=mapper)
    exec(compile(tree, '<queued-initial-branches>', 'exec'), scope)
    return scope['initial_search'], source, ast.unparse(tree)


def trials(functions, expected, repeats, *, on_failure=None):
    if not 1 <= repeats <= 3:
        raise ValueError('Use one to three alternating pairs')
    reference, rows = fingerprint(expected), []
    for pair in range(repeats):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            # The callback builds a fresh context before returning the timed operation.
            operation = functions[side]()
            clocks = cpu_policy()
            before, began = cpu_seconds(), time.perf_counter()
            value = operation()
            elapsed = time.perf_counter() - began
            cpu = np.subtract(cpu_seconds(), before).tolist()
            actual = fingerprint(value)
            if actual != reference:
                if on_failure is not None:
                    on_failure(reference, actual, side, pair)
                raise ValueError(f'Full initial search changed: {side}, pair {pair}')
            row = dict(side=side, pair=pair, seconds=elapsed, cpu_seconds=cpu, exact=True,
                       fully_fitted_hypotheses=value['fully_fitted_hypotheses'],
                       cpu_policy_before=clocks, cpu_policy_after=cpu_policy())
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if not k.startswith('cpu_policy')}),
                  flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, choices=range(1, 4), default=3)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 3:
        parser.error('Pin three CPUs and one BLAS thread')
    files = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path(initial_search.__file__),
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/probe_algo07v3_discovery_schedule.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    request = json.loads(args.request.read_bytes())
    if request['runtime'] != runtime_versions():
        raise ValueError('Match the frozen numerical runtime')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    prepared, expected = saved['evidence']['preparation'], saved['evidence']['audit']['initial']
    input_signature = fingerprint(prepared)
    noise = (json.dumps(prepared['noise'], default=_json_value,
                       sort_keys=True, allow_nan=False) + '\n').encode()
    noise_sha = hashlib.sha256(noise).hexdigest()
    candidate, original, changed = transform()
    (args.output / 'original.txt').write_text(original)
    (args.output / 'candidate.txt').write_text(changed)
    (args.output / 'plan.json').write_text(json.dumps(dict(
        bindings=bindings, request=str(args.request), repeats=args.repeats,
        affinity=sorted(os.sched_getaffinity(0)), blas_threads=1, max_workers=3,
        production_modified=False), indent=2) + '\n')

    def fresh(side):
        scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                        noise_sha, genuine=False)
        function = initial_search.initial_search if side == 'baseline' else candidate
        return lambda: function(scan, scan.radio_sigma_hz, map_arms=map_initial_arms)

    host = host_resources()

    def failed(expected, actual, side, pair):
        for name, value in [('expected', expected), ('actual', actual)]:
            (args.output / f'failed-{pair}-{side}-{name}.json').write_text(
                json.dumps(value, indent=2) + '\n')

    rows = trials({side: lambda side=side: fresh(side) for side in ('baseline', 'candidate')},
                  expected, args.repeats, on_failure=failed)
    assert fingerprint(prepared) == input_signature
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    result = dict(rows=rows, bindings=bindings, scientific_receipt=saved['sha256'], exact=True,
                  resources_start=host, resources_end=host_resources(),
                  affinity=sorted(os.sched_getaffinity(0)), blas_threads=1,
                  max_workers=3, full_pipeline_benchmark=False, runtime_modified=False)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
