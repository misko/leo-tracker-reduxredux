"""Shadow primitive observations preserve mutation, failures and full trajectories."""

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from profile_algo07v3_blas_primitives import Shadow, hierarchical, instrument


def test_shadow_owns_mutable_rhs_and_returns_original_result():
    configured = []
    shadow = Shadow(lambda *args: configured.append(args), 2)
    original = np.arange(6.)

    def operation(rhs):
        rhs += 1
        return rhs

    actual = shadow.call('mutable', 'scipy', operation, original)
    assert actual is original
    np.testing.assert_array_equal(actual, np.arange(6.) + 1)
    assert shadow.rows['mutable']['first_difference'] is None
    assert configured == [('scipy', 2), ('scipy', 1)]


def test_shadow_records_first_difference_but_keeps_original_trajectory():
    state = [1]
    shadow = Shadow(lambda owner, threads: state.__setitem__(0, threads), 3)
    def operation(a):
        return a + state[0]
    for _ in range(4):
        assert shadow.call('addition', 'numpy', operation, 10) == 11
    row = shadow.rows['addition']
    assert row['calls'] == 4 and row['tested'] == 1
    assert row['first_difference']['call'] == 1
    assert state == [1]


def test_shadow_restores_threads_on_candidate_exception():
    state = [1]
    shadow = Shadow(lambda owner, threads: state.__setitem__(0, threads), 2)

    def operation():
        if state[0] == 2:
            raise RuntimeError('candidate failure')
        return 1

    with pytest.raises(RuntimeError, match='candidate failure'):
        shadow.call('failure', 'numpy', operation)
    assert state == [1]


@pytest.mark.parametrize('width', [0, 1, 16, 177])
def test_instrumentation_preserves_every_likelihood_field_and_inputs(width):
    rng = np.random.default_rng(61106)
    args = (rng.normal(size=80), rng.normal(size=(80, width)), 20., np.arange(80) % 4)
    kwargs = dict(prior_groups=np.arange(width) // 2, iterations=3)
    before = fingerprint((args, kwargs))
    shadow = Shadow(lambda *args: None, 2)
    function, _, _ = instrument(shadow)
    assert fingerprint(function(*args, **kwargs)) == fingerprint(
        hierarchical.hierarchical_bound(*args, **kwargs))
    assert fingerprint((args, kwargs)) == before
    assert all(row['first_difference'] is None for row in shadow.rows.values())
    if width:
        assert shadow.rows['dgetrs-matrix']['tested'] == 3
        assert shadow.rows['inv_root.T @ inv_root']['tested'] == 3
