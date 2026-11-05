"""External bounded-scope, one-entry calculation cache for initial search."""

import argparse
import ast
import copy
import hashlib
import inspect
import json
import os
import statistics
import time
from contextlib import contextmanager
from pathlib import Path

import algo07v3_preinitial_cache_position_oracle as reference_position
import algo07v3_preinitial_cache_search_oracle as reference_search
import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_discovery_schedule import cpu_seconds, host_resources

from leo.analysis.localization_v3.region import SearchRegion
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.operations.localization_v3_job import runtime_versions
from leo.operations.localization_v3_parallel import map_initial_arms
from leo.storage.localization_v3 import LocalizationV3Store


@contextmanager
def fixed_calculations(problem):
    """Reuse only the last calculation while the caller keeps its model fixed.

    Copies isolate caller-owned results; no cache or replacement method escapes
    the scope. Position bytes distinguish signed zero and numerical dtypes.
    """
    original = problem.calculate
    had_instance_method = 'calculate' in vars(problem)
    key, saved = None, None

    def calculate(x):
        nonlocal key, saved
        a = np.asarray(x)
        current = a.dtype.str, a.shape, a.tobytes()
        if current == key:
            return copy.deepcopy(saved)
        result = original(x)
        saved = copy.deepcopy(result)
        key = current
        return result

    try:
        problem.calculate = calculate
        yield
    finally:
        if had_instance_method:
            problem.calculate = original
        else:
            del problem.calculate


def transformed(function, transform, scope):
    source = inspect.getsource(function)
    tree = ast.parse(source)
    transform(tree.body[0])
    tree = ast.fix_missing_locations(tree)
    namespace = dict(scope, fixed_calculations=fixed_calculations)
    exec(compile(tree, '<scoped-initial-calculations>', 'exec'), namespace)
    return namespace[function.__name__], source, ast.unparse(tree)


def wrap(body, first, last, problem):
    matches = [i for i, n in enumerate(body) if ast.unparse(n).startswith(first)]
    stops = [i for i, n in enumerate(body) if ast.unparse(n).startswith(last)]
    if len(matches) != 1 or len(stops) != 1 or stops[0] < matches[0]:
        raise ValueError('Fixed-model calculation scope changed; review extraction')
    a, b = matches[0], stops[0] + 1
    context = ast.parse(f'with fixed_calculations({problem}):\n    pass').body[0]
    context.body = body[a:b]
    body[a:b] = [context]


def functions():
    # Freeze old/new comparisons even after runtime integration.
    reference_search.refreshed = reference_position.refreshed
    reference_search.fit = reference_position.fit
    reference_search.NormalPosition = reference_position.NormalPosition

    def refreshed_body(function):
        loop = next(n for n in function.body if isinstance(n, ast.For))
        wrap(loop.body, 'result = fit(', 'phase = problem.state(', 'problem')

    refreshed, a, b = transformed(reference_position.refreshed, refreshed_body,
                                 vars(reference_position))

    def arm_body(function):
        wrap(function.body, "x = result['parameters']", 'return dict(', 'p')

    arm, c, d = transformed(reference_search.fit_initial_arm, arm_body,
                            dict(vars(reference_search), refreshed=refreshed))

    def search_body(function):
        loop = next(n for n in function.body if isinstance(n, ast.For)
                    and ast.unparse(n.target) == 'arm')
        wrap(loop.body, 'zero[arm] = fit(', 'zero[arm] = fit(', 'p')

    search, e, f = transformed(reference_search.initial_search, search_body,
                               dict(vars(reference_search), fit_initial_arm=arm))
    return reference_search.initial_search, search, dict(
        refreshed=dict(original=a, candidate=b), fit_initial_arm=dict(original=c, candidate=d),
        initial_search=dict(original=e, candidate=f))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, choices=range(1, 4), default=3)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 3:
        parser.error('Pin three CPUs and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path(reference_position.__file__), Path(reference_search.__file__),
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/probe_algo07v3_discovery_schedule.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    if runtime_versions() != request['runtime']:
        raise ValueError('Match the frozen numerical runtime')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    prepared, expected = saved['evidence']['preparation'], saved['evidence']['audit']['initial']
    noise = (json.dumps(prepared['noise'], default=_json_value,
                       sort_keys=True, allow_nan=False) + '\n').encode()
    baseline, candidate, sources = functions()
    (args.output / 'sources.json').write_text(json.dumps(sources, indent=2) + '\n')
    (args.output / 'plan.json').write_text(json.dumps(dict(
        bindings=bindings, scientific_receipt=saved['sha256'],
        affinity=sorted(os.sched_getaffinity(0)), blas_threads=1, cache_entries=1,
        repeats=args.repeats, runtime_modified=False), indent=2) + '\n')
    rows, host = [], host_resources()
    for pair in range(args.repeats):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                            hashlib.sha256(noise).hexdigest(), genuine=False)
            operation = baseline if side == 'baseline' else candidate
            before, began = cpu_seconds(), time.perf_counter()
            value = operation(scan, scan.radio_sigma_hz, map_arms=map_initial_arms)
            seconds = time.perf_counter() - began
            cpu = np.subtract(cpu_seconds(), before).tolist()
            actual, required = fingerprint(value), fingerprint(expected)
            row = dict(pair=pair, side=side, seconds=seconds, cpu_seconds=cpu,
                       exact=actual == required,
                       fully_fitted_hypotheses=value['fully_fitted_hypotheses'])
            rows.append(row)
            (args.output / f'{pair}-{side}.json').write_text(json.dumps(row, indent=2) + '\n')
            print(json.dumps(row), flush=True)
            if not row['exact']:
                for name, signature in [('actual', actual), ('expected', required)]:
                    (args.output / f'failed-{name}.json').write_text(
                        json.dumps(signature, indent=2) + '\n')
                raise ValueError('Complete initial search changed')
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    means = {side: dict(seconds=statistics.mean(r['seconds'] for r in rows if r['side'] == side),
                       cpu_seconds=statistics.mean(sum(r['cpu_seconds']) for r in rows
                                                   if r['side'] == side))
             for side in ('baseline', 'candidate')}
    result = dict(rows=rows, means=means, exact=True, bindings=bindings,
                  resources_start=host, resources_end=host_resources(),
                  full_pipeline_speedup=None, runtime_modified=False)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(means), flush=True)


if __name__ == '__main__':
    main()
