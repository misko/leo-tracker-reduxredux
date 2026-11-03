"""Measure compiled small-matrix solves on a captured real phase-pair batch."""

import argparse
import ctypes as ct
import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np

from leo.analysis.research.joint_predictive_families import two_family_phase_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name('batch_factor.c')
    library = args.output/'factor.so'
    cmd = ['cc', '-O3', '-fPIC', '-shared', '-std=c11', '-ffp-contract=off',
           str(source), '-o', str(library), '-lm']
    subprocess.run(cmd, check=True)
    native = ct.CDLL(str(library)).batch_factor
    native.argtypes = [ct.c_void_p]*4 + [ct.c_size_t, ct.c_int]
    native.restype = ct.c_int
    original = np.linalg.solve
    batch = []

    def capture(a, b):
        if a.ndim == 4 and not batch:
            batch.extend([a.copy(), np.ascontiguousarray(b[..., 0])])
        return original(a, b)

    with np.load(args.fixture) as z:
        values = [[z[f'{s}_{i}'] for i in range(2)]
                  for s in ['observed', 'means', 'modes', 'log_priors', 'visible']]
        values.insert(2, z['base_covariance'])
        np.linalg.solve = capture
        try:
            two_family_phase_evidence(*values)
        finally:
            np.linalg.solve = original
    gram, rhs = batch
    rows = []
    for repeat in range(7):
        results = {}
        for variant in (['numpy', 'compiled'] if repeat % 2 == 0 else ['compiled', 'numpy']):
            began = time.perf_counter()
            if variant == 'numpy':
                coefficient = original(gram, rhs[..., None])[..., 0]
                sign, determinant = np.linalg.slogdet(gram)
                assert (sign > 0).all()
            else:
                coefficient = np.empty_like(rhs)
                determinant = np.empty(rhs.shape[:-1])
                code = native(*(a.ctypes.data_as(ct.c_void_p) for a in
                                (gram, rhs, coefficient, determinant)),
                              determinant.size, rhs.shape[-1])
                assert code == 0, code
            elapsed = time.perf_counter()-began
            rows.append(dict(repeat=repeat, variant=variant, seconds=elapsed))
            results[variant] = (coefficient, determinant)
        a, b = results['numpy'], results['compiled']
        delta = dict(coefficient=float(np.max(abs(a[0]-b[0]))),
                     logdet=float(np.max(abs(a[1]-b[1]))),
                     quadratic=float(np.max(abs(np.sum(rhs*(a[0]-b[0]), axis=-1)))))
    result = dict(command=cmd, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  binary_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
                  shape=list(gram.shape), differences=delta, timings=rows,
                  diagnostic_only=True, production_modified=False)
    (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
