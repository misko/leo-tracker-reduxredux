"""Independent dense Gaussian checks for curved-only posterior transfer."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from dsx01_cut_linear import (  # noqa: E402
    bounded_scalar_newton,  # noqa: E402
    posterior_root,
    predictive_gaussian,
)


def test_predictive_density_matches_dense_conditional_and_preserves_inputs():
    rng = np.random.default_rng(42)
    u = rng.normal(size=(9, 3))
    sigma = np.linspace(1, 2, 9)
    weight = np.linspace(0.5, 1.5, 9)
    precision = np.array([1, 2, 3])
    root = posterior_root(u, sigma, weight, precision)
    covariance = np.linalg.inv(np.diag(precision) + (u.T * (weight / sigma**2)) @ u)
    np.testing.assert_allclose(root @ root.T, covariance, atol=1e-14)
    design = rng.normal(size=(6, 3))
    mean = rng.normal(size=3)
    copy = mean.copy()
    raw = rng.normal(size=6)
    groups = np.array([0, 0, 0, 1, 1, 1])
    result = predictive_gaussian(raw, design, mean, root, sigma=2, bias_sigma=3, groups=groups)
    c = 4 * np.eye(6) + design @ covariance @ design.T + 9 * (groups[:, None] == groups)
    z = raw - design @ mean
    expected = z @ np.linalg.solve(c, z) + np.linalg.slogdet(c)[1] + 6 * np.log(2 * np.pi)
    assert result["negative_twice_log_probability"] == pytest.approx(expected, abs=1e-12)
    np.testing.assert_array_equal(mean, copy)


def test_shared_calibration_uncertainty_is_not_independent_per_fragment():
    u, root, mean, raw = np.ones((2, 1)), np.array([[10.0]]), np.zeros(1), np.array([5.0, -5.0])
    joint = predictive_gaussian(raw, u, mean, root, sigma=1, bias_sigma=0.1, groups=np.arange(2))
    independent = sum(
        predictive_gaussian(raw[k : k + 1], u[k : k + 1], mean, root, sigma=1, bias_sigma=0.1)[
            "negative_twice_log_probability"
        ]
        for k in range(2)
    )
    assert joint["negative_twice_log_probability"] > independent + 30


def test_invalid_groups_rejected():
    with pytest.raises(ValueError, match="group"):
        predictive_gaussian(np.ones(2), np.ones((2, 1)), np.ones(1), np.eye(1), groups=[-1, 0])


@pytest.mark.parametrize("target", [[1.2, -3.4], [20.0, -20.0]])
def test_bounded_search_solves_independent_quadratic_inside_box(target):
    target = np.array(target)
    queries = []

    def objective(x):
        queries.append(np.array(x))
        return float(np.sum((x - target) ** 2))

    result = bounded_scalar_newton(objective, [12.5, 12.5])
    np.testing.assert_allclose(result["parameters"], np.clip(target, -12.5, 12.5), atol=1e-5)
    assert result["converged"]
    assert np.all(np.abs(queries) <= 12.5 + 1e-12)
    scores = [h["score"] for h in result["history"]]
    assert np.all(np.diff(scores) <= 1e-10)


def test_linear_values_change_geometry_score_without_updating_calibration(monkeypatch):
    import probe_dsx01_cut_linear as probe

    result = dict(
        features=np.ones((3, 1)),
        coefficient=np.array([2.0]),
        coefficient_prior_precision=np.ones(1),
        noise_precision=np.ones(1),
        residual=np.array([3.0]),
        elevation=np.ones(3),
    )
    track = dict(values=np.zeros(6), times=np.arange(6.0))
    p = SimpleNamespace(
        calculate=lambda x: result,
        point_noise=np.ones(3),
        noise_groups=np.zeros(3, dtype=int),
        scan=SimpleNamespace(tracks=[track]),
    )
    monkeypatch.setattr(
        probe,
        "transfer_design",
        lambda *args: (np.zeros(6), np.ones((6, 1)), np.ones(6)),
    )
    row = dict(accepted=True, index=0, alias=0, candidate_index=1, same_channel_gap_s=None)
    first = probe.CutScore(p, [row], "joint").score([0.0, 0.0])
    track["values"] = np.full(6, 10000.0)
    second = probe.CutScore(p, [row], "joint").score([0.0, 0.0])
    assert second["linear"] > first["linear"] + 90
    assert first["curved"] == second["curved"] == 9
    np.testing.assert_array_equal(result["coefficient"], [2.0])
    assert probe.CutScore(p, [row], "continuation").selected == []


def test_white_subset_keeps_original_aliases_and_does_not_promote_rejected_nominations():
    from run_dsx01_white_cut_linear import keep_white

    original = [dict(component=str(k), accepted=k < 2, alias=3 + k) for k in range(3)]
    selected = keep_white(original, {"1", "2"})
    assert [r["accepted"] for r in selected] == [False, True, False]
    assert [r["alias"] for r in selected] == [3, 4, 5]
    assert original[0]["accepted"]
