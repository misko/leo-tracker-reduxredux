"""External exact-factor reuse probe for the owned v3 joint-density kernel."""

import argparse
import ast
import ctypes as ct
import hashlib
import inspect
import json
import resource
import subprocess
import time
from pathlib import Path

import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import joint_density


def candidate(factor, source=None):
    source = source or inspect.getsource(joint_density.two_family_phase_evidence)
    tree = ast.parse(source)
    solve = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
             and ast.unparse(n.value) == 'np.linalg.solve(gram, rhs[..., None])[..., 0]']
    determinant = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                   and ast.unparse(n.value) == 'np.linalg.slogdet(gram)']
    if len(solve) != 1 or len(determinant) != 1:
        raise ValueError('Review changed solve/determinant boundaries')
    solve[0].targets = ast.parse('coefficient, sign, logdet = None').body[0].targets
    solve[0].value = ast.parse('_factor(gram, rhs)', mode='eval').body

    class Remove(ast.NodeTransformer):
        def visit_Assign(self, node):
            return None if node is determinant[0] else node

    tree = ast.fix_missing_locations(Remove().visit(tree))
    scope = dict(vars(joint_density), _factor=factor)
    exec(compile(tree, '<v3-shared-lu-probe>', 'exec'), scope)
    return scope['two_family_phase_evidence'], ast.unparse(tree)


def bind(source, root):
    libraries = list((Path(np.__file__).parent.parent / 'numpy.libs').glob(
        'libscipy_openblas64_*.so'))
    if len(libraries) != 1:
        raise ValueError('Exactly one installed NumPy ILP64 OpenBLAS required')
    binary = root / 'batch-lu.so'
    command = ['cc', '-O3', '-fPIC', '-shared', '-std=c11', '-ffp-contract=off',
               '-Wall', '-Wextra', str(source), '-o', str(binary), '-lm']
    subprocess.run(command, check=True, capture_output=True)
    library, lapack = ct.CDLL(str(binary)), ct.CDLL(str(libraries[0]))
    native = library.batch_lu
    native.argtypes, native.restype = [ct.c_void_p] * 6 + [ct.c_size_t, ct.c_int], ct.c_int
    address = ct.cast(lapack.scipy_dgesv_64_, ct.c_void_p)

    def factor(a, b):
        a, b = np.asarray(a), np.asarray(b)
        if (a.dtype != np.float64 or b.dtype != np.float64 or a.ndim < 2
                or not 1 <= a.shape[-1] <= 32 or a.shape[-1] != a.shape[-2]
                or b.shape != a.shape[:-1] or not np.isfinite(a).all()
                or not np.isfinite(b).all()):
            raise ValueError('Finite matching float64 matrices with dimension 1..32 required')
        a, b = np.ascontiguousarray(a), np.ascontiguousarray(b)
        coef = np.empty_like(b)
        sign, logdet = (np.empty(b.shape[:-1]) for _ in range(2))
        status = native(address, *(v.ctypes.data_as(ct.c_void_p)
                                  for v in (a, b, coef, sign, logdet)), sign.size, a.shape[-1])
        if status:
            raise np.linalg.LinAlgError(f'Explicit native factor status {status}')
        return coef, sign, logdet

    return factor, [source, binary, libraries[0]], command


def cpu():
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        p.error('QNAP is read-only')
    root.mkdir(exist_ok=False)
    factor, paths, command = bind(Path(__file__).with_name('native_batch_lu.c'), root)
    replacement, source = candidate(factor)
    (root / 'candidate.py').write_text(source + '\n')
    paths += [args.fixture, Path(__file__), Path(joint_density.__file__),
              Path('tools/check_algo07v3_scan_likelihood.py'), root / 'candidate.py']
    pins = {str(q.resolve()): hashlib.sha256(q.read_bytes()).hexdigest() for q in paths}
    (root / 'plan.json').write_text(json.dumps(dict(bindings=pins, command=command), indent=2))
    with np.load(args.fixture, allow_pickle=False) as data:
        inputs = [[data[f'{name}_{i}'] for i in range(2)]
                  for name in ('observed', 'means', 'modes', 'log_priors', 'visible')]
        inputs.insert(2, data['base_covariance'])
    before, rows = fingerprint(inputs), []
    for mode in (True, False):
        reference = None
        for repeat in range(6):
            for side in (('baseline', 'candidate') if repeat % 2 == 0
                         else ('candidate', 'baseline')):
                fn = joint_density.two_family_phase_evidence if side == 'baseline' else replacement
                start, used = time.perf_counter(), cpu()
                result = fn(*inputs, optimize_contractions=mode)
                wall, used = time.perf_counter() - start, cpu() - used
                sig = fingerprint(result)
                if reference is None:
                    reference = sig
                row = dict(optimized_contractions=mode, repeat=repeat, side=side,
                           seconds=wall, cpu_seconds=used, exact=sig == reference)
                rows.append(row)
                print(json.dumps(row), flush=True)
                (root / 'rows.json').write_text(json.dumps(rows, indent=2))
                if sig != reference or before != fingerprint(inputs):
                    raise ValueError('Complete kernel or input bytes changed')
    assert all(hashlib.sha256(Path(q).read_bytes()).hexdigest() == sha
               for q, sha in pins.items())
    (root / 'result.json').write_text(json.dumps(dict(
        rows=rows, bindings=pins, exact=True, native_qualified=False,
        production_modified=False, input_fingerprint=before), indent=2))


if __name__ == '__main__':
    main()
