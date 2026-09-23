import numpy as np
import pytest

from tools.research.shared_cfo_optimizer_v2 import fit, mapping, objective


def case(shared=True):
    rng = np.random.default_rng(841)
    n = np.arange(0, 50000, 50, dtype=float)
    n = n[(n % 250 >= 16) & (n % 250 < 234)]
    t = np.exp(1j * rng.uniform(-np.pi, np.pi, size=(2, 2, 8, len(n))))
    nominal = np.array([[100.0, 300.0], [250.0, 450.0]])
    residual = np.array([[150.0, -200.0], [250.0, -100.0]])
    if not shared:
        residual[1, 1] += 200.0
    weights = rng.normal(size=(2, 2, 8)) + 1j * rng.normal(size=(2, 2, 8))
    y = np.zeros((len(n), 2), complex)
    for rx in (0, 1):
        for s in (0, 1):
            y[:, rx] += (weights[rx, s] @ t[rx, s]) * np.exp(
                2j * np.pi * residual[rx, s] * n / 2500000
            )
    groups = (n // 250).astype(int)
    chosen = rng.permutation(np.unique(groups))[:100]
    train = np.isin(groups, chosen)
    return y, t, n, train, nominal, residual


def test_profile_gradient_matches_finite_difference():
    y, t, n, train, nominal, _ = case()
    for shared in (False, True):
        matrix, offset = mapping(nominal, shared)
        p = np.arange(matrix.shape[1]) * 31.0 + 8.0
        value, gradient = objective(y[train], t[:, :, :, train], n[train], p, matrix, offset)
        assert value > 0
        for j in range(len(p)):
            direction = np.eye(len(p))[j] * 0.001
            plus = objective(y[train], t[:, :, :, train], n[train], p + direction, matrix, offset)[
                0
            ]
            minus = objective(y[train], t[:, :, :, train], n[train], p - direction, matrix, offset)[
                0
            ]
            assert np.isclose(gradient[j], (plus - minus) / 0.002, rtol=1e-5, atol=1e-5)


def test_nonzero_shared_truth_recovered_from_wrong_frequency_peaks():
    y, t, n, train, nominal, truth = case()
    result = fit(y, t, n, train, nominal, np.zeros((2, 2)), True)
    assert np.all(np.diff(result["training_objective_history"]) <= 1e-9)
    assert np.max(abs(np.array(result["residual_cfo_hz"]) - truth)) < 0.1
    assert sum(r["held_sse"] for r in result["receivers"]) < 1e-4


def test_independent_truth_and_held_independence():
    y, t, n, train, nominal, truth = case(False)
    a = fit(y, t, n, train, nominal, np.zeros((2, 2)), False)
    assert np.max(abs(np.array(a["residual_cfo_hz"]) - truth)) < 0.1
    changed = y.copy()
    changed[~train] *= 30j
    b = fit(changed, t, n, train, nominal, np.zeros((2, 2)), False)
    assert a["residual_cfo_hz"] == b["residual_cfo_hz"]
    assert a["training_objective_history"] == b["training_objective_history"]


def test_shared_constraint_detects_synthetic_source_specific_rate():
    y, t, n, train, nominal, _ = case(False)
    independent = fit(y, t, n, train, nominal, np.zeros((2, 2)), False)
    shared = fit(y, t, n, train, nominal, np.zeros((2, 2)), True)
    assert sum(r["held_sse"] for r in independent["receivers"]) < 1e-4
    assert sum(r["held_sse"] for r in shared["receivers"]) > 10
    residual = np.array(shared["residual_cfo_hz"])
    delta = nominal[1] - nominal[0] + residual[1] - residual[0]
    assert abs(delta[0] - delta[1]) < 1e-8


def test_degenerate_columns_abstain():
    y, t, n, train, nominal, _ = case()
    t[:, 1] = t[:, 0]
    with pytest.raises(ValueError, match="rank-deficient"):
        fit(y, t, n, train, nominal, np.zeros((2, 2)), True)
