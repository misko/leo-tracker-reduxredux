"""Check exact LU reuse against installed NumPy on captured phase-pair matrices."""

import argparse
import ctypes as ct
import json
import subprocess
import time
from pathlib import Path

import numpy as np
from profile_algo07_glrt import PROFILE


def run(fixture, output):
    from leo.analysis.research import joint_predictive_families as kernel

    if output.exists() or not output.resolve().is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private research directory required')
    output.mkdir()
    fixture_pin = PROFILE.digest(fixture)
    source = Path(__file__).with_name('native_batch_lu.c')
    source_pin = PROFILE.digest(source)
    libraries = list((Path(np.__file__).parent.parent/'numpy.libs').glob(
        'libscipy_openblas64_*.so'))
    if len(libraries) != 1:
        raise RuntimeError('Explicit installed NumPy ILP64 OpenBLAS library required')
    lapack_path = libraries[0]
    lapack_pin = PROFILE.digest(lapack_path)
    lapack = ct.CDLL(str(lapack_path))
    gesv = ct.cast(lapack.scipy_dgesv_64_, ct.c_void_p)
    library = output/'batch-lu.so'
    command = ['cc', '-O3', '-fPIC', '-shared', '-std=c11', '-ffp-contract=off',
               '-Wall', '-Wextra', str(source), '-o', str(library), '-lm']
    subprocess.run(command, check=True, capture_output=True)
    native = ct.CDLL(str(library)).batch_lu
    native.argtypes = [ct.c_void_p]*6+[ct.c_size_t, ct.c_int]
    native.restype = ct.c_int

    def fused(gram, rhs):
        gram, rhs = np.ascontiguousarray(gram, dtype=float), np.ascontiguousarray(rhs, dtype=float)
        d = gram.shape[-1]
        if gram.shape[-2] != d or rhs.shape != gram.shape[:-1] or not 1 <= d <= 32:
            raise ValueError('Matching small square matrices and one RHS required')
        if not np.isfinite(gram).all() or not np.isfinite(rhs).all():
            raise ValueError('Finite research inputs required')
        coef = np.empty_like(rhs)
        sign, logdet = [np.empty(rhs.shape[:-1]) for _ in range(2)]
        status = native(gesv, *(a.ctypes.data_as(ct.c_void_p) for a in
                               (gram, rhs, coef, sign, logdet)), sign.size, d)
        if status:
            raise np.linalg.LinAlgError(f'Native LU status {status}')
        return coef, sign, logdet

    solve = np.linalg.solve
    batch = []

    class Captured(Exception):
        pass

    def capture(a, b):
        if a.ndim == 4:
            batch.extend([a.copy(), np.ascontiguousarray(b[..., 0])])
            raise Captured
        return solve(a, b)

    with np.load(fixture, allow_pickle=False) as z:
        values = [[z[f'{s}_{i}'] for i in range(2)]
                  for s in ['observed', 'means', 'modes', 'log_priors', 'visible']]
        values.insert(2, z['base_covariance'])
        np.linalg.solve = capture
        try:
            kernel.two_family_phase_evidence(*values)
        except Captured:
            pass
        finally:
            np.linalg.solve = solve
    if len(batch) != 2:
        raise RuntimeError('No real phase-pair matrix batch captured')
    gram, rhs = batch
    np.savez(output/'captured.npz', gram=gram, rhs=rhs)
    rng = np.random.default_rng(20261103)
    checks = []
    for d in (1, 2, 3, 6, 12, 32):
        matrices = rng.normal(size=(31, d, d))
        vector = rng.normal(size=(31, d))
        expected = (solve(matrices, vector[..., None])[..., 0], *np.linalg.slogdet(matrices))
        actual = fused(matrices, vector)
        for a, b in zip(actual, expected, strict=True):
            np.testing.assert_array_equal(a.view(np.uint64), b.view(np.uint64))
        checks.append(dict(dimension=d, matrices=31, exact=True))
    try:
        fused(np.zeros((2, 6, 6)), np.ones((2, 6)))
    except np.linalg.LinAlgError:
        pass
    else:
        raise AssertionError('Singular system accepted')
    timings = []
    for repeat in range(7):
        results = {}
        for variant in (['numpy', 'fused'] if repeat % 2 == 0 else ['fused', 'numpy']):
            began = time.perf_counter()
            results[variant] = (solve(gram, rhs[..., None])[..., 0], *np.linalg.slogdet(gram)) \
                if variant == 'numpy' else fused(gram, rhs)
            timings.append(dict(repeat=repeat, variant=variant, seconds=time.perf_counter()-began))
        for a, b in zip(results['numpy'], results['fused'], strict=True):
            np.testing.assert_array_equal(a.view(np.uint64), b.view(np.uint64))
    # Research-only interception: consume the LU determinant only for the very
    # same matrix object whose solve just produced it. Restore NumPy afterward.
    slogdet = np.linalg.slogdet
    cached = []
    fused_calls = []

    def shared_solve(a, b):
        if a.ndim != 4 or b.shape != (*a.shape[:-1], 1):
            return solve(a, b)
        coef, sign, determinant = fused(a, b[..., 0])
        cached[:] = [a, sign, determinant]
        fused_calls.append(int(sign.size))
        return coef[..., None]

    def shared_determinant(a):
        if cached and cached[0] is a:
            _, sign, determinant = cached
            cached.clear()
            return sign, determinant
        return slogdet(a)

    phase_timings = []
    for repeat in range(3):
        results = {}
        for variant in (['numpy', 'fused'] if repeat % 2 == 0 else ['fused', 'numpy']):
            if variant == 'fused':
                np.linalg.solve, np.linalg.slogdet = shared_solve, shared_determinant
            began = time.perf_counter()
            try:
                results[variant] = kernel.two_family_phase_evidence(*values)
            finally:
                np.linalg.solve, np.linalg.slogdet = solve, slogdet
            phase_timings.append(dict(repeat=repeat, variant=variant,
                                      seconds=time.perf_counter()-began))
            if cached:
                raise AssertionError('Unconsumed factorization')
        for key in results['numpy']:
            left, right = results['numpy'][key], results['fused'][key]
            if isinstance(left, list):
                for a, b in zip(left, right, strict=True):
                    np.testing.assert_array_equal(np.asarray(a), np.asarray(b))
            else:
                np.testing.assert_array_equal(left, right)
    if PROFILE.digest(fixture) != fixture_pin or PROFILE.digest(source) != source_pin:
        raise ValueError('Fixture or source changed')
    result = dict(exact=True, shape=list(gram.shape), stress=checks, singular_rejected=True,
                  timings=timings, command=command, source_sha256=source_pin,
                  binary_sha256=PROFILE.digest(library), fixture=str(fixture),
                  fixture_sha256=fixture_pin, numpy_version=np.__version__,
                  lapack=str(lapack_path), lapack_sha256=lapack_pin,
                  kernel_sha256=PROFILE.digest(Path(kernel.__file__)),
                  captured_sha256=PROFILE.digest(output/'captured.npz'),
                  phase_timings=phase_timings, phase_outputs_exact=True,
                  phase_pairs_per_call=int(np.prod([len(v) for v in values[1]])),
                  fused_systems=sum(fused_calls),
                  tool_sha256=PROFILE.digest(Path(__file__)),
                  scope='One captured matrix batch and full phase likelihood, not a worker',
                  production_modified=False)
    PROFILE.write_new(output/'result.json', result)
    return {k: v for k, v in result.items() if k not in ('timings', 'stress')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.fixture, args.output)))
