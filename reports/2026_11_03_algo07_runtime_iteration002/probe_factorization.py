"""Diagnostic only: compare one Cholesky factorization with separate solve/det."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from leo.analysis.research.joint_predictive_families import two_family_phase_evidence


def factor_solve(gram, rhs):
    root = np.linalg.cholesky(gram)
    v = np.empty_like(rhs)
    for i in range(rhs.shape[-1]):
        v[..., i] = (rhs[..., i] - np.sum(root[..., i, :i] * v[..., :i], axis=-1)) / root[..., i, i]
    for i in reversed(range(rhs.shape[-1])):
        v[..., i] = (v[..., i] - np.sum(root[..., i+1:, i] * v[..., i+1:], axis=-1)) / root[..., i, i]
    return v, 2 * np.log(np.diagonal(root, axis1=-2, axis2=-1)).sum(axis=-1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    saved = np.linalg.solve
    batch = []

    def capture(a, b):
        if a.ndim == 4 and not batch:
            batch.extend([a.copy(), b[..., 0].copy()])
        return saved(a, b)

    with np.load(args.fixture) as z:
        values = [[z[f'{s}_{i}'] for i in range(2)]
                  for s in ['observed', 'means', 'modes', 'log_priors', 'visible']]
        values.insert(2, z['base_covariance'])
        np.linalg.solve = capture
        try:
            two_family_phase_evidence(*values)
        finally:
            np.linalg.solve = saved
    gram, rhs = batch
    rows = []
    for repeat in range(5):
        outputs = {}
        for variant in (['original', 'cholesky'] if repeat % 2 == 0 else ['cholesky', 'original']):
            began = time.perf_counter()
            if variant == 'original':
                v = saved(gram, rhs[..., None])[..., 0]
                sign, logdet = np.linalg.slogdet(gram)
                assert (sign > 0).all()
            else:
                v, logdet = factor_solve(gram, rhs)
            outputs[variant] = (v, logdet)
            rows.append(dict(repeat=repeat, variant=variant, seconds=time.perf_counter()-began))
        a, b = outputs['original'], outputs['cholesky']
        delta = dict(coefficient=float(np.max(abs(a[0]-b[0]))),
                     logdet=float(np.max(abs(a[1]-b[1]))),
                     quadratic=float(np.max(abs(np.sum(rhs*(a[0]-b[0]), axis=-1)))))
    result = dict(shape=list(gram.shape), differences=delta, timings=rows,
                  diagnostic_only=True, production_modified=False)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
