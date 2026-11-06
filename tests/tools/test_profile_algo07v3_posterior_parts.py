import numpy as np
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
