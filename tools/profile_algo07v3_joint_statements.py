"""Attribute unchanged joint-phase kernel statements on bound native captures."""

import argparse
import ast
import hashlib
import inspect
import json
import os
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

from benchmark_algo07v3_direct_grids import load_capture
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_blas_threads import library_info

from leo.analysis.localization_v3 import joint_density, numpy_factor


def observer(source=None):
    """Time individual assignments, never loops or nested cumulative scopes."""
    source = source or inspect.getsource(joint_density.two_family_phase_evidence)
    tree = ast.parse(source)
    if (len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef)
            or tree.body[0].name != 'two_family_phase_evidence'):
        raise ValueError('Expected one owned joint-density function')
    records = defaultdict(lambda: dict(calls=0, wall_seconds=0., cpu_seconds=0.))

    @contextmanager
    def measure(label):
        start, used = time.perf_counter(), time.process_time()
        try:
            yield
        finally:
            row = records[label]
            row['wall_seconds'] += time.perf_counter() - start
            row['cpu_seconds'] += time.process_time() - used
            row['calls'] += 1

    class Instrument(ast.NodeTransformer):
        def visit_Assign(self, node):
            label = f'{node.lineno}: ' + ', '.join(ast.unparse(n) for n in node.targets)
            scope = ast.Call(func=ast.Name(id='_observe_statement', ctx=ast.Load()),
                             args=[ast.Constant(value=label)], keywords=[])
            return ast.copy_location(ast.With(
                items=[ast.withitem(context_expr=scope, optional_vars=None)], body=[node]), node)

    tree = ast.fix_missing_locations(Instrument().visit(tree))
    namespace = dict(vars(joint_density), _observe_statement=measure)
    exec(compile(tree, '<observed-owned-joint-density>', 'exec'), namespace)
    return namespace['two_family_phase_evidence'], records, ast.unparse(tree)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native, output = args.native.resolve(), args.output.resolve()
    if output.is_relative_to('/mnt/qnap01') or len(os.sched_getaffinity(0)) != 1:
        parser.error('One CPU and a fresh local output required')
    verification = json.loads((native / 'comparison.json').read_bytes())
    if not verification['exact_owned_science_and_artifacts']:
        raise ValueError('Native exact-science comparison required')
    captures = native / 'baseline'
    catalogue = json.loads((captures / 'captures.json').read_bytes())
    libraries = library_info()
    if not catalogue or any(row['threads'] != 1 for row in libraries):
        raise ValueError('Native captures and one-thread BLAS required')
    backend = numpy_factor._backend()
    if backend is None:
        raise ValueError('Current owned LU backend required')
    paths = [Path(__file__), Path(joint_density.__file__), Path(numpy_factor.__file__),
             Path('tools/benchmark_algo07v3_direct_grids.py'),
             Path('tools/probe_algo07v3_blas_threads.py'),
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('src/leo/analysis/_joint_lu.c'), native / 'comparison.json',
             captures / 'captures.json', *(Path(lib._name) for lib in backend[:2]),
             *(captures / 'captures' / f'{key}.npz' for key in catalogue)]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    output.mkdir(exist_ok=False)
    (output / 'plan.json').write_text(json.dumps(dict(
        bindings=bindings, libraries=libraries, cpus=sorted(os.sched_getaffinity(0)),
        scope='Instrumented statement attribution, not a speed benchmark',
        production_modified=False), indent=2) + '\n')
    rows = []
    for key in sorted(catalogue, key=int):
        inputs = load_capture(captures, key, catalogue[key])
        before = fingerprint(inputs)
        for optimized in (True, False):
            reference = joint_density.two_family_phase_evidence(
                *inputs, optimize_contractions=optimized)
            if not optimized and fingerprint(reference) != catalogue[key]['result']:
                raise ValueError('Current kernel changed original direct native result')
            function, records, transformed = observer()
            start, used = time.perf_counter(), time.process_time()
            actual = function(*inputs, optimize_contractions=optimized)
            wall, cpu = time.perf_counter() - start, time.process_time() - used
            if fingerprint(actual) != fingerprint(reference) or fingerprint(inputs) != before:
                raise ValueError('Observer changed result or input bytes')
            row = dict(phase_pairs=int(key), optimized=optimized, seconds=wall,
                       cpu_seconds=cpu, exact=True, statements=dict(records))
            rows.append(row)
            (output / 'rows.json').write_text(json.dumps(rows, indent=2) + '\n')
            print(json.dumps({k: v for k, v in row.items() if k != 'statements'}), flush=True)
    if library_info() != libraries or any(
            hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha for p, sha in bindings.items()):
        raise ValueError('Bound dependencies changed')
    (output / 'observer.py').write_text(transformed + '\n')
    (output / 'result.json').write_text(json.dumps(dict(
        rows=rows, bindings=bindings, full_pipeline_speedup=None), indent=2) + '\n')


if __name__ == '__main__':
    main()
