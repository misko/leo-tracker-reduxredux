import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_shared_lu import bind, candidate

from leo.analysis.localization_v3.joint_density import two_family_phase_evidence
from tests.analysis.test_joint_predictive_families import fixture


@pytest.mark.parametrize('mode', [True, False])
@pytest.mark.parametrize('chunk', [1, 6, 32768])
def test_explicit_factor_boundary_preserves_entire_density(mode, chunk):
    def factor(a, b):
        return np.linalg.solve(a, b[..., None])[..., 0], *np.linalg.slogdet(a)
    fn, _ = candidate(factor)
    args = fixture()
    before = fingerprint(args)
    assert fingerprint(fn(*args, max_pairs=chunk, optimize_contractions=mode)) == fingerprint(
        two_family_phase_evidence(*args, max_pairs=chunk, optimize_contractions=mode))
    assert fingerprint(args) == before


def test_source_drift_fails_closed():
    with pytest.raises(ValueError, match='boundaries'):
        candidate(None, 'def f(): return 0')


def test_real_native_factor_matches_bytes_and_rejects_singular(tmp_path):
    from pathlib import Path

    factor, _, _ = bind(Path('tools/native_batch_lu.c'), tmp_path)
    rng = np.random.default_rng(20261106)
    for n in (1, 2, 6, 12, 32):
        a, b = rng.normal(size=(15, n, n)), rng.normal(size=(15, n))
        before = fingerprint((a, b))
        expected = np.linalg.solve(a, b[..., None])[..., 0], *np.linalg.slogdet(a)
        assert fingerprint(factor(a, b)) == fingerprint(expected)
        assert fingerprint((a, b)) == before
    with pytest.raises(np.linalg.LinAlgError):
        factor(np.zeros((2, 6, 6)), np.ones((2, 6)))
    with pytest.raises(ValueError, match='float64'):
        factor(np.eye(2, dtype=np.float32), np.ones(2))
