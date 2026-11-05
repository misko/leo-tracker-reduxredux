"""External experiment: schedule independent initial discovery seeds in batches.

The original per-seed body is extracted unchanged; full initial-search results
must match both each other and the saved owned initial search. No runtime source
is edited, no candidate or fit budget is reduced, and at most three children run.
"""

import argparse
import ast
import copy
import hashlib
import inspect
import json
import os
import resource
import statistics
import time
from contextlib import contextmanager
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import discovery, initial_search
from leo.analysis.localization_v3.region import SearchRegion
from leo.application.localization_v3 import _context
from leo.application.localization_v3_engine import _json_value
from leo.operations.localization_v3_job import runtime_versions
from leo.operations.localization_v3_parallel import map_initial_arms, map_predictive_folds
from leo.storage.localization_v3 import LocalizationV3Store


def batch_seeds(operation, proposals):
    items = list(proposals)
    results = []
    for start in range(0, len(items), 3):
        results.extend(map_predictive_folds(operation, items[start:start + 3]))
    return results


def transform(mapper=batch_seeds):
    source = inspect.getsource(discovery.fresh_discovery)
    tree = ast.parse(source)
    function = tree.body[0]
    tail = function.body[-3:]
    if (ast.unparse(tail[0]) != 'candidates = []' or not isinstance(tail[1], ast.For)
            or ast.unparse(tail[1].target) != '(number, beta)'
            or ast.unparse(tail[1].iter) != 'enumerate(proposals)'
            or tail[1].orelse or ast.unparse(tail[2]) != 'return candidates'):
        raise ValueError('Discovery seed loop changed; review the extraction')
    loop = tail[1]
    append = loop.body[-1]
    if (not isinstance(append, ast.Expr) or not isinstance(append.value, ast.Call)
            or ast.unparse(append.value.func) != 'candidates.append'
            or len(append.value.args) != 1 or append.value.keywords):
        raise ValueError('Discovery result construction changed')
    helper = ast.parse('def one_seed(item):\n    number, beta = item').body[0]
    helper.body += copy.deepcopy(loop.body[:-1]) + [ast.Return(copy.deepcopy(append.value.args[0]))]
    function.body[-3:] = [helper, ast.parse(
        'return list(_map_seeds(one_seed, enumerate(proposals)))').body[0]]
    tree = ast.fix_missing_locations(tree)
    scope = dict(vars(discovery), _map_seeds=mapper)
    exec(compile(tree, '<scheduled-discovery-seeds>', 'exec'), scope)
    return scope['fresh_discovery'], source, ast.unparse(tree)


@contextmanager
def selected_discovery(operation):
    original = initial_search.fresh_discovery
    try:
        initial_search.fresh_discovery = operation
        yield
    finally:
        initial_search.fresh_discovery = original


def cpu_seconds():
    return [r.ru_utime + r.ru_stime for r in (
        resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN))]


def host_resources():
    return dict(load=os.getloadavg(), cpu_pressure=Path('/proc/pressure/cpu').read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 3:
        parser.error('Pin three CPUs and one BLAS thread')
    files = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/check_algo07v3_scan_likelihood.py')]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    request = json.loads(args.request.read_bytes())
    if runtime_versions() != request['runtime']:
        raise ValueError('Match the numerical runtime')
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    prepared = saved['evidence']['preparation']
    expected = fingerprint(saved['evidence']['audit']['initial'])
    input_signature = fingerprint(prepared)
    noise_bytes = (json.dumps(prepared['noise'], default=_json_value,
                             sort_keys=True, allow_nan=False) + '\n').encode()
    candidate, source, compiled = transform()
    (args.output / 'original.py').write_text(source)
    (args.output / 'candidate.py').write_text(compiled + '\n')
    functions = dict(baseline=discovery.fresh_discovery, candidate=candidate)
    rows, host_before = [], host_resources()
    for pair in range(3):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            scan = _context(prepared, SearchRegion(tuple(request['search_center'])),
                            hashlib.sha256(noise_bytes).hexdigest(), genuine=False)
            discovery_times = []

            def recorded(*positional, _operation=functions[side], _times=discovery_times,
                         **keywords):
                started = time.perf_counter()
                result = _operation(*positional, **keywords)
                _times.append(time.perf_counter() - started)
                return result

            began, cpu = time.perf_counter(), cpu_seconds()
            with selected_discovery(recorded):
                value = initial_search.initial_search(scan, scan.radio_sigma_hz,
                                                       map_arms=map_initial_arms)
            seconds, cpu_after = time.perf_counter() - began, cpu_seconds()
            assert len(discovery_times) == 1
            actual = fingerprint(value)
            if actual != expected:
                (args.output / 'failed-actual.json').write_text(json.dumps(actual, indent=2) + '\n')
                (args.output / 'failed-expected.json').write_text(
                    json.dumps(expected, indent=2) + '\n')
                raise ValueError('Full initial-search result differs from owned reference')
            row = dict(pair=pair, side=side, seconds=seconds, exact=True,
                       discovery_seconds=discovery_times[0],
                       self_cpu_seconds=cpu_after[0] - cpu[0],
                       children_cpu_seconds=cpu_after[1] - cpu[1])
            rows.append(row)
            print(json.dumps(row), flush=True)
    assert fingerprint(prepared) == input_signature
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    means = {side: {key: statistics.mean(r[key] for r in rows if r['side'] == side)
                    for key in ('seconds', 'discovery_seconds',
                                'self_cpu_seconds', 'children_cpu_seconds')}
             for side in functions}
    data = dict(rows=rows, means=means, exact=True, bindings=bindings,
                runtime=request['runtime'], affinity=sorted(os.sched_getaffinity(0)),
                blas_threads=1, max_workers=3, scientific_receipt=saved['sha256'],
                source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                candidate_sha256=hashlib.sha256(compiled.encode()).hexdigest(),
                host_start=host_before, host_end=host_resources(),
                runtime_modified=False, full_pipeline_speedup=None)
    (args.output / 'result.json').write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps(means), flush=True)


if __name__ == '__main__':
    main()
