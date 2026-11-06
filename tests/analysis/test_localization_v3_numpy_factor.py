"""Owned factor reuse must reproduce NumPy, including fallback and failures."""

import ctypes as ct
from types import SimpleNamespace

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import joint_density
from leo.analysis.localization_v3 import numpy_factor as factor


def reference(a, b):
    return np.linalg.solve(a, np.asarray(b)[..., None])[..., 0], *np.linalg.slogdet(a)


@pytest.mark.parametrize('dimension', [1, 2, 6, 12, 32, 33])
@pytest.mark.parametrize('layout', ['C', 'F', 'strided'])
def test_real_backend_exact_for_pivoted_matrices_and_layouts(dimension, layout):
    assert factor._backend() is not None, 'Build the optional extension for native qualification'
    rng = np.random.default_rng(1106 + dimension)
    a = rng.normal(size=(2, 7, dimension, dimension))
    b = rng.normal(size=(2, 7, dimension))
    if layout == 'F':
        a, b = np.asfortranarray(a), np.asfortranarray(b)
    elif layout == 'strided':
        a, b = a[:, ::2, ::-1, ::-1], b[:, ::2, ::-1]
    before = fingerprint((a, b))
    assert fingerprint(factor.solve_and_slogdet(a, b)) == fingerprint(reference(a, b))
    assert fingerprint((a, b)) == before


@pytest.mark.parametrize('dtype', [np.float32, np.complex128, np.float64])
def test_missing_provider_and_unsupported_types_use_numpy(monkeypatch, dtype):
    monkeypatch.setattr(factor, '_backend', lambda: None)
    a, b = np.eye(3, dtype=dtype), np.arange(3, dtype=dtype)
    assert fingerprint(factor.solve_and_slogdet(a, b)) == fingerprint(reference(a, b))


@pytest.mark.parametrize('dtype', [np.float32, np.complex128])
def test_installed_backend_falls_back_for_unsupported_types(dtype):
    a, b = np.eye(3, dtype=dtype), np.arange(3, dtype=dtype)
    assert fingerprint(factor.solve_and_slogdet(a, b)) == fingerprint(reference(a, b))


@pytest.mark.parametrize('shape', [(0, 3, 3), (3, 3)])
def test_empty_batch_and_unbatched(shape):
    a = np.broadcast_to(np.eye(3), shape).copy()
    b = np.ones(shape[:-1])
    assert fingerprint(factor.solve_and_slogdet(a, b)) == fingerprint(reference(a, b))


def test_singular_and_internal_failure(monkeypatch):
    with pytest.raises(np.linalg.LinAlgError, match='Singular matrix'):
        factor.solve_and_slogdet(np.zeros((2, 6, 6)), np.ones((2, 6)))
    monkeypatch.setattr(factor, '_backend', lambda: (None, None, lambda *args: -2, None))
    with pytest.raises(RuntimeError, match='status -2'):
        factor.solve_and_slogdet(np.eye(3), np.ones(3))


@pytest.mark.parametrize('configuration', [b'OpenBLAS USE32BITINT', b'', None])
def test_wrong_or_missing_abi_rejects_backend(monkeypatch, configuration):
    class Config:
        def __call__(self):
            return configuration
    provider = SimpleNamespace(scipy_openblas_get_config64_=Config())
    monkeypatch.setattr(ct, 'CDLL', lambda name: provider)
    try:
        factor._backend.cache_clear()
        assert factor._backend() is None
    finally:
        factor._backend.cache_clear()


def test_missing_library_returns_fallback(monkeypatch):
    def missing(*args):
        raise OSError('unavailable')
    monkeypatch.setattr(ct, 'CDLL', missing)
    try:
        factor._backend.cache_clear()
        assert factor._backend() is None
    finally:
        factor._backend.cache_clear()


@pytest.mark.parametrize('bad', [np.nan, np.inf])
def test_nonfinite_input_uses_original_numpy_path(monkeypatch, bad):
    a, b = np.eye(2), np.ones(2)
    b[0] = bad
    calls = []
    original = np.linalg.solve
    def observed(*args):
        calls.append(True)
        return original(*args)
    monkeypatch.setattr(np.linalg, 'solve', observed)
    assert fingerprint(factor.solve_and_slogdet(a, b)) == fingerprint(reference(a, b))
    assert len(calls) == 2


def test_mismatched_shape_preserves_numpy_exception():
    with pytest.raises(ValueError):
        factor.solve_and_slogdet(np.eye(3), np.ones(2))


def test_missing_extension_returns_fallback(monkeypatch):
    import sys

    from leo import analysis
    monkeypatch.setitem(sys.modules, 'leo.analysis._joint_lu', None)
    monkeypatch.delattr(analysis, '_joint_lu', raising=False)
    try:
        factor._backend.cache_clear()
        assert factor._backend() is None
    finally:
        factor._backend.cache_clear()


@pytest.mark.parametrize('mode', [True, False])
@pytest.mark.parametrize('chunk', [1, 6, 32768])
def test_whole_joint_evidence_exact_against_original_factorization(monkeypatch, mode, chunk):
    rng = np.random.default_rng(93)
    y = [rng.normal(size=3), rng.normal(size=2)]
    means = [rng.normal(size=(3, 3)), rng.normal(size=(4, 2))]
    modes = [rng.normal(size=(3, 3, 2)) * .4, rng.normal(size=(4, 2, 1)) * .3]
    h = rng.normal(size=(5, 2))
    args = (y, means, np.eye(5) + h @ h.T, modes,
            [np.log([.2, .3, .5]), np.log([.1, .2, .3, .4])],
            [np.array([True, False, True]), np.ones(4, bool)])
    before = fingerprint(args)
    actual = joint_density.two_family_phase_evidence(
        *args, max_pairs=chunk, optimize_contractions=mode)
    monkeypatch.setattr(joint_density, 'solve_and_slogdet', reference)
    expected = joint_density.two_family_phase_evidence(
        *args, max_pairs=chunk, optimize_contractions=mode)
    assert fingerprint(actual) == fingerprint(expected)
    assert fingerprint(args) == before
