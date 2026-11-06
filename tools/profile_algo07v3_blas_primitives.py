"""Shadow-test BLAS primitives while returning the unchanged one-thread trajectory."""

import argparse
import ast
import ctypes
import inspect
import json
import os
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_blas_threads import digest, library_info

from leo.analysis.localization_v3 import hierarchical


def clone(value):
    if isinstance(value, np.ndarray):
        return value.copy(order='K')
    if isinstance(value, tuple):
        return tuple(clone(v) for v in value)
    if isinstance(value, dict):
        return {k: clone(v) for k, v in value.items()}
    return value


class Shadow:
    def __init__(self, configure, threads):
        self.configure, self.threads, self.rows = configure, threads, {}

    def call(self, label, owner, operation, *args, **kwargs):
        row = self.rows.setdefault(label, dict(calls=0, tested=0, first_difference=None))
        row['calls'] += 1
        if row['first_difference'] is not None:
            return operation(*args, **kwargs)
        # LAPACK may overwrite its RHS. Own both shadows before the original call.
        # NumPy products are read-only here. Preserve operand aliasing: A.T @ A
        # can dispatch differently from two independent, numerically equal copies.
        copied = clone((args, kwargs)) if owner == 'scipy' else (args, kwargs)
        candidate = clone((args, kwargs)) if owner == 'scipy' else (args, kwargs)
        result = operation(*args, **kwargs)
        reference = operation(*copied[0], **copied[1])
        if fingerprint(result) != fingerprint(reference):
            raise ValueError('Copy/layout control differs at ' + label)
        try:
            self.configure(owner, self.threads)
            alternative = operation(*candidate[0], **candidate[1])
        finally:
            self.configure(owner, 1)
        row['tested'] += 1
        if fingerprint(reference) != fingerprint(alternative):
            row['first_difference'] = dict(
                call=row['calls'], baseline=fingerprint(reference),
                candidate=fingerprint(alternative),
                argument_shapes=[list(v.shape) if isinstance(v, np.ndarray) else None
                                 for v in args])
        return result


def instrument(shadow):
    names = ('_solve_factor', '_cholesky', 'hierarchical_bound')
    source = '\n\n'.join(inspect.getsource(getattr(hierarchical, name)) for name in names)
    tree = ast.parse(source)

    class Products(ast.NodeTransformer):
        def visit_BinOp(self, node):
            label = ast.unparse(node)
            node = self.generic_visit(node)
            if isinstance(node.op, ast.MatMult):
                return ast.copy_location(ast.Call(
                    func=ast.Name(id='_product', ctx=ast.Load()),
                    args=[ast.Constant(label), node.left, node.right], keywords=[]), node)
            return node

    scope = dict(vars(hierarchical))
    scope['_product'] = lambda label, a, b: shadow.call(label, 'numpy', np.matmul, a, b)
    for name in ('dgetrf', 'dgetrs', 'dpotrf'):
        original = getattr(hierarchical, name)

        def wrapper(*args, _name=name, _operation=original, **kwargs):
            label = _name
            if _name == 'dgetrs':
                label += '-matrix' if args[2].ndim == 2 else '-vector'
            return shadow.call(label, 'scipy', _operation, *args, **kwargs)

        scope[name] = wrapper
    changed = ast.fix_missing_locations(Products().visit(tree))
    exec(compile(changed, '<shadow-blas-primitives>', 'exec'), scope)
    return scope['hierarchical_bound'], source, ast.unparse(changed)


def configuration(libraries):
    functions = {}
    for row in libraries:
        suffix = '64_' if row['owner'] == 'numpy' else ''
        handle = ctypes.CDLL(row['path'])
        setter = getattr(handle, 'scipy_openblas_set_num_threads' + suffix)
        setter.argtypes, setter.restype = [ctypes.c_int], None
        getter = getattr(handle, 'scipy_openblas_get_num_threads' + suffix)
        getter.argtypes, getter.restype = [], ctypes.c_int
        functions[row['owner']] = setter, getter

    def configure(owner, threads):
        setter, getter = functions[owner]
        setter(threads)
        if getter() != threads:
            raise ValueError('Actual BLAS thread setting differs')

    return configure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threads', type=int, choices=(2, 3), required=True)
    args = parser.parse_args()
    if sorted(os.sched_getaffinity(0)) != [0, 1, 2]:
        parser.error('Requires CPU affinity 0,1,2')
    if args.output.resolve().is_relative_to('/mnt/qnap01'):
        parser.error('QNAP is read-only')
    libs = library_info()
    if any(row['threads'] != 1 for row in libs):
        parser.error('Both BLAS libraries must start at one thread')
    args.output.mkdir(exist_ok=False)
    meta, arrays = args.capture / 'hardest.json', args.capture / 'hardest.npz'
    metadata = json.loads(meta.read_bytes())
    assert digest(arrays) == metadata['arrays_sha256']
    with np.load(arrays, allow_pickle=False) as data:
        positional = [data[f'argument_{i}'] for i in range(4)]
        keywords = dict(metadata['scalar_keywords'])
        keywords.update({k.removeprefix('keyword_'): data[k] for k in data.files
                         if k.startswith('keyword_')})
    paths = [Path(__file__), Path(hierarchical.__file__), meta, arrays,
             Path('tools/check_algo07v3_scan_likelihood.py'),
             Path('tools/probe_algo07v3_blas_threads.py')]
    bindings = {str(path.resolve()): digest(path) for path in paths}
    before = fingerprint((positional, keywords))
    expected = fingerprint(hierarchical.hierarchical_bound(*positional, **keywords))
    shadow = Shadow(configuration(libs), args.threads)
    function, original, changed = instrument(shadow)
    actual = function(*positional, **keywords)
    assert fingerprint(actual) == expected
    assert fingerprint((positional, keywords)) == before
    assert library_info() == libs
    assert all(digest(Path(p)) == sha for p, sha in bindings.items())
    (args.output / 'original.py').write_text(original)
    (args.output / 'instrumented.py').write_text(changed)
    result = dict(bindings=bindings, libraries=libs, threads=args.threads,
                  rows=shadow.rows, unchanged_trajectory_exact=True,
                  expected=expected, production_modified=False, full_pipeline_speedup=None)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: dict(calls=v['calls'], tested=v['tested'],
                              first_difference_call=(v['first_difference'] or {}).get('call'))
                      for k, v in shadow.rows.items()}, indent=2))


if __name__ == '__main__':
    main()
