"""Observe posterior subexpressions on a captured call without changing its result."""

import argparse
import ast
import hashlib
import inspect
import json
import os
import time
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import hierarchical


def instrument(rows):
    source = inspect.getsource(hierarchical.hierarchical_bound)
    tree = ast.parse(source)
    posterior = next(n for n in tree.body[0].body
                     if isinstance(n, ast.FunctionDef) and n.name == 'posterior')
    labels = {'gram, rhs': 'initialize', 'root': 'cholesky', 'lu, pivots, info': 'lower_LU',
              'mean': 'two_mean_solves', 'inv_root': 'inverse_solve',
              'cov': 'covariance_product'}
    found = []
    for node in ast.walk(posterior):
        label = None
        if isinstance(node, ast.Assign):
            left = node.targets[0]
            target = (', '.join(ast.unparse(n) for n in left.elts)
                      if isinstance(left, ast.Tuple) else ast.unparse(left))
            if target in labels and not (target == 'cov' and isinstance(node.value, ast.Constant)):
                label = labels[target]
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and ast.unparse(node.value.func) == 'np.add.at'):
            label = 'ordered_assembly'
        if label:
            found.append(label)
            wrapper = ast.parse(f'_observe({label!r}, lambda: None)', mode='eval').body
            wrapper.args[1].body = node.value
            node.value = wrapper
    if sorted(found) != sorted([*labels.values(), 'ordered_assembly', 'ordered_assembly']):
        raise ValueError('Review posterior boundaries before profiling')

    def observe(name, operation):
        before = time.perf_counter()
        result = operation()
        elapsed = time.perf_counter() - before
        row = rows.setdefault(name, dict(calls=0, seconds=0.))
        row['calls'] += 1
        row['seconds'] += elapsed
        return result

    tree = ast.fix_missing_locations(tree)
    scope = dict(vars(hierarchical), _observe=observe)
    exec(compile(tree, '<profile-posterior-parts>', 'exec'), scope)
    return scope['hierarchical_bound'], source, ast.unparse(tree)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    args.output.mkdir(exist_ok=False)
    metadata = json.loads((args.capture / 'hardest.json').read_bytes())
    raw = args.capture / 'hardest.npz'
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == metadata['arrays_sha256']
    with np.load(raw, allow_pickle=False) as saved:
        positional = [saved[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): saved[k]
                         for k in saved.files if k.startswith('keyword_')})
    paths = [Path(__file__), Path(hierarchical.__file__), raw, args.capture / 'hardest.json']
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    expected = fingerprint(hierarchical.hierarchical_bound(*positional, **keywords))
    before = fingerprint((positional, keywords))
    rows, trials = {}, []
    operation, original, changed = instrument(rows)
    for _ in range(3):
        begin = time.perf_counter()
        result = operation(*positional, **keywords)
        trials.append(dict(seconds=time.perf_counter() - begin,
                           exact=fingerprint(result) == expected))
    assert all(r['exact'] for r in trials) and before == fingerprint((positional, keywords))
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    (args.output / 'original.py').write_text(original)
    (args.output / 'instrumented.py').write_text(changed)
    output = dict(bindings=bindings, parts=rows, trials=trials, exact=True,
                  precision_iterations=result['precision_iterations'],
                  profiled=True, full_pipeline_speedup=None)
    (args.output / 'result.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output['parts'], indent=2))


if __name__ == '__main__':
    main()
