import algo07v3_preworkspace_hierarchical_oracle as oracle
import numpy as np
import profile_algo07v3_posterior_parts as profile
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3_posterior_parts import hierarchical, instrument


@pytest.mark.parametrize('width', [0, 1, 16])
def test_all_parts_execute_without_changing_complete_bound(width):
    rng = np.random.default_rng(20261105)
    y, u, g = rng.normal(size=80), rng.normal(size=(80, width)), np.arange(80) % 4
    kwargs = dict(prior_groups=np.arange(width) // 2, iterations=16)
    before = fingerprint((y, u, g, kwargs))
    rows = {}
    operation, _, _ = instrument(rows)
    expected = hierarchical.hierarchical_bound(y, u, 20., g, **kwargs)
    actual = operation(y, u, 20., g, **kwargs)
    assert fingerprint(expected) == fingerprint(actual)
    assert before == fingerprint((y, u, g, kwargs))
    assert rows['inverse_solve']['calls'] == actual['precision_iterations']
    assert rows['two_mean_solves']['calls'] == actual['precision_iterations'] + 1
    assert all(r['seconds'] >= 0 for r in rows.values())


@pytest.mark.parametrize('old', [False, True])
@pytest.mark.parametrize('width', [0, 1, 175])
def test_profile_handles_original_and_buffered_boundaries_exactly(monkeypatch, old, width):
    if old:
        monkeypatch.setattr(profile.hierarchical, 'hierarchical_bound', oracle.hierarchical_bound)
    rng = np.random.default_rng(1106)
    args = (rng.normal(size=80), rng.normal(size=(80, width)), 1., np.arange(80) % 4)
    rows = {}
    operation, _, _ = profile.instrument(rows)
    expected = profile.hierarchical.hierarchical_bound(*args, iterations=3)
    assert fingerprint(operation(*args, iterations=3)) == fingerprint(expected)
    assert rows['inverse_solve']['calls'] == expected['precision_iterations']
    assert rows['cholesky']['calls'] == expected['precision_iterations'] + 1
