import itertools

import numpy as np
import pytest

from leo.analysis.sparse_glrt_likelihood import (
    FrequencyEvidence,
    SparseConfig,
    candidate_ratios,
    fit_sparse,
    fit_weights,
    select_sparse,
)


def evidence(y, groups=None, weights=None):
    y = np.asarray(y, dtype=float)
    if y.ndim == 1:
        y = y[:, None]
    n = len(y)
    return FrequencyEvidence(
        tuple(map(str, range(n))),
        y,
        np.full(y.shape, 1 / y.shape[1]) if weights is None else weights,
        np.full(n, 0.95),
        np.zeros(n, dtype=int) if groups is None else groups,
        np.arange(n, dtype=float),
    )


def test_conditional_density_normalizes_against_background_quadrature():
    # Uniform quantiles of a Cauchy are deterministic integration nodes under H0.
    n = 200000
    config = SparseConfig(scale_hz=5000.0)
    y = config.background_scale_hz * np.tan(np.pi * ((np.arange(n) + 0.5) / n - 0.5))
    data = evidence(y)
    ratios = candidate_ratios(
        data, np.full((n, 1), 47000.0), np.ones((n, 1), bool), [23000.0], config
    )
    assert ratios.mean() == pytest.approx(1.0, abs=2e-6)


def test_exact_offset_gradient_and_invisible_null():
    data = evidence([[200.0, 2100.0], [4500.0, -700.0]])
    pred = np.array([[0.0, 1000.0], [100.0, -500.0]])
    visible = np.array([[True, False], [True, True]])
    config = SparseConfig()
    ratio, derivative, _ = candidate_ratios(data, pred, visible, [100.0], config, True)
    delta = 0.01
    numerical = (
        candidate_ratios(data, pred, visible, [100 + delta], config)
        - candidate_ratios(data, pred, visible, [100 - delta], config)
    ) / (2 * delta)
    np.testing.assert_allclose(derivative, numerical, rtol=1e-7, atol=1e-10)
    assert ratio[0, 1] == 1
    assert derivative[0, 1] == 0


def test_two_satellites_and_shared_band_offsets_recovered():
    n = 160
    t = np.linspace(-1, 1, n)
    pred = np.column_stack((12000 * np.sin(t * 2), -15000 * np.cos(t * 3), 50000 + 100 * t))
    groups = np.arange(n) % 4
    truth = np.array([1200.0, -800.0, 2100.0, -1600.0])
    identity = (np.arange(n) // 4) % 2
    data = evidence(pred[np.arange(n), identity] + truth[groups], groups)
    config = SparseConfig(
        scale_hz=100, satellite_penalty=8, iterations=12, maximum_satellites=3, em_iterations=50
    )
    result = fit_sparse(data, pred, np.ones(pred.shape, bool), [truth + 100], config)
    assert set(result["active"]) == {0, 1}
    np.testing.assert_allclose(result["offsets_hz"], truth, atol=5)
    assert result["score"] > 500
    assert result["effective_background"] < 0.02


def test_subset_search_matches_exhaustive_small_oracle_and_penalty():
    ratios = np.array([[30, 0.1, 0.1]] * 20 + [[0.1, 30, 0.1]] * 20 + [[0.1, 0.1, 1]] * 10)
    config = SparseConfig(maximum_satellites=3, satellite_penalty=5.0, em_iterations=200)
    chosen, _, score, _ = select_sparse(ratios, config)
    exhaustive = []
    for count in range(4):
        for subset in itertools.combinations(range(3), count):
            _, ll = fit_weights(ratios[:, subset], 200)
            exhaustive.append((ll - count * 5, subset))
    assert score == pytest.approx(max(exhaustive)[0], abs=1e-7)
    assert set(chosen) == {0, 1}
    assert select_sparse(np.ones((20, 3)), config)[0] == []


def test_duplicate_physical_ids_rejected_and_candidate_alternatives_normalized():
    data = evidence([100, 200])
    with pytest.raises(ValueError, match="unique"):
        FrequencyEvidence(
            ("same", "same"),
            data.frequency_hz,
            data.candidate_weight,
            data.signal_probability,
            data.group,
            data.time_s,
        )
    pred = np.zeros((2, 1))
    a = candidate_ratios(data, pred, np.ones_like(pred, bool), [0], SparseConfig())
    repeated = evidence(np.repeat(data.frequency_hz, 3, axis=1))
    b = candidate_ratios(repeated, pred, np.ones_like(pred, bool), [0], SparseConfig())
    np.testing.assert_allclose(a, b)


def test_missing_true_satellite_goes_to_background():
    data = evidence(np.linspace(-1000, 1000, 30))
    result = fit_sparse(
        data,
        np.full((30, 2), 1e7),
        np.ones((30, 2), bool),
        [[0]],
        SparseConfig(scale_hz=100, maximum_satellites=2),
    )
    assert result["active"] == []
    assert result["score"] == 0
    assert result["effective_background"] == 1


def test_null_model_does_not_pay_for_an_arbitrary_offset_start():
    data = evidence(np.linspace(-1000, 1000, 30))
    result = fit_sparse(
        data,
        np.full((30, 1), 1e7),
        np.ones((30, 1), bool),
        [[100000.0]],
        SparseConfig(scale_hz=100, maximum_satellites=1),
    )
    assert result["score"] == 0
    assert result["active"] == []
    assert result["offsets_hz"] == [0.0]


def test_seeded_subset_is_preserved_as_a_feasible_solution():
    pred = np.column_stack((np.arange(40.0) * 1000, -np.arange(40.0) * 1000))
    data = evidence(pred[:, 0] + 500.0)
    config = SparseConfig(scale_hz=100.0, iterations=3, maximum_satellites=2)
    a = fit_sparse(data, pred, np.ones_like(pred, bool), [[500.0]], config)
    b = fit_sparse(
        data,
        pred,
        np.ones_like(pred, bool),
        [dict(offsets_hz=a["offsets_hz"], active=a["active"])],
        config,
    )
    assert b["score"] >= a["score"] - 1e-6
    with pytest.raises(ValueError, match="seed satellite"):
        fit_sparse(
            data, pred, np.ones_like(pred, bool), [dict(offsets_hz=[500.0], active=[999])], config
        )


def test_satellite_specific_prior_cost_can_replace_an_expensive_incumbent():
    from leo.analysis.sparse_glrt_likelihood import select_sparse

    ratio = np.full((20, 2), 10.0)
    active, weights, score, _ = select_sparse(
        ratio, SparseConfig(maximum_satellites=1), [0], penalties=[30.0, 2.0]
    )
    assert active == [1]
    assert score == pytest.approx(20 * np.log(10) - 2, abs=1e-5)
    with pytest.raises(ValueError, match="penalty"):
        select_sparse(ratio, SparseConfig(), penalties=[-1.0, 2.0])


def test_sparse_reselection_retains_a_feasible_learned_weight_solution():
    from leo.analysis.sparse_glrt_likelihood import select_sparse

    ratio = np.full((40, 1), 1.02)
    active, weights, score, _ = select_sparse(
        ratio,
        SparseConfig(maximum_satellites=1, satellite_penalty=0),
        [0],
        initial_weights=[0.0, 1.0],
    )
    assert active == [0]
    np.testing.assert_allclose(weights, [0.0, 1.0])
    assert score == pytest.approx(40 * np.log(1.02))
    with pytest.raises(ValueError, match="normalized incumbent"):
        select_sparse(ratio, SparseConfig(), [0], initial_weights=[1.0, 1.0])
