import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_upper_triangular import candidate_function, reference, solve_upper


@pytest.mark.parametrize('width', [0, 1, 16, 190])
@pytest.mark.parametrize('layout', ['C', 'F'])
@pytest.mark.parametrize('density', [0., .2, 1.])
def test_complete_bound_and_inputs_exact(width, layout, density):
    rng = np.random.default_rng(2391)
    u = rng.normal(size=(96, width))
    u[rng.random(u.shape) >= density] = 0
    u = np.array(u, order=layout)
    y, s, g = rng.normal(size=96) * 100, rng.uniform(3, 40, 96), np.arange(96) % 5 * 3
    kwargs = dict(prior_groups=np.arange(width) // 5 - 1,
                  powers=np.linspace(.1, 1., 5), iterations=16)
    before = fingerprint((y, u, s, g, kwargs))
    operation, _, _ = candidate_function()
    assert fingerprint(operation(y, u, s, g, **kwargs)) == fingerprint(
        reference.hierarchical_bound(y, u, s, g, **kwargs))
    assert fingerprint((y, u, s, g, kwargs)) == before


@pytest.mark.parametrize('n', [1, 3, 175])
@pytest.mark.parametrize('value', [0., -0., 1e-300, -1e-300, 1e100])
def test_upper_solve_records_known_signed_zero_rejection(n, value):
    rng = np.random.default_rng(101)
    a = rng.normal(size=(n, n))
    upper = np.linalg.cholesky(a @ a.T + np.eye(n)).T
    rhs = np.full(n, value)
    before = fingerprint((upper, rhs))
    expected = reference._solve_factor(upper, np.arange(n, dtype=np.int32), rhs)
    exact = fingerprint(solve_upper(upper, rhs)) == fingerprint(expected)
    # This experiment must remain rejected: even identity-lower elimination
    # changes signed zero for multi-row right-hand sides. No xfail/relaxed gate.
    assert exact == (not (value == 0 and np.signbit(value) and n > 1))
    assert before == fingerprint((upper, rhs))


def test_lapack_failure_propagates(monkeypatch):
    import probe_algo07v3_upper_triangular as probe
    monkeypatch.setattr(probe, 'dtrtrs', lambda *args: (None, -1))
    with pytest.raises(np.linalg.LinAlgError, match='DTRTRS'):
        probe.solve_upper(np.eye(1), np.ones(1))
