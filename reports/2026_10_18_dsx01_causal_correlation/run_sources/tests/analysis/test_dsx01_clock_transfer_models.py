"""Normalized mixture priors and grouped point-contamination controls."""

from types import SimpleNamespace

import numpy as np
import pytest
from dsx01_clock_transfer_models import SparsePriors, grouped_mixture_profile, mixture_cost


def test_mixture_prior_has_correct_gaussian_limits_and_density_ratio():
    x = np.array([-4.0, 0.0, 3.0])
    np.testing.assert_allclose(mixture_cost(x, 2, 10, 1), (x / 2) ** 2)
    np.testing.assert_allclose(mixture_cost(x, 2, 10, 0), (x / 10) ** 2)
    density = 0.9 / 2 * np.exp(-0.5 * (x / 2) ** 2) + 0.1 / 10 * np.exp(-0.5 * (x / 10) ** 2)
    np.testing.assert_allclose(
        mixture_cost(x, 2, 10, 0.9), -2 * np.log(density / (0.9 / 2 + 0.1 / 10))
    )
    assert mixture_cost(np.array([1000.0]), 0.5, 10, 0.9)[0] < (1000 / 0.5) ** 2
    with pytest.raises(ValueError):
        mixture_cost(x, 0, 10, 0.9)


def test_group_bias_matches_gaussian_solution_when_components_match():
    y = np.array([2.0, 3.0, 4.0, 10.0, 14.0])
    c = np.array([1.0, 1.0, 1.0, np.sqrt(2), np.sqrt(2)])
    g = np.array([0, 0, 0, 1, 1])
    result = grouped_mixture_profile(y, c, g, 2, narrow=150, broad=150)
    expected = np.bincount(g, weights=c * y) / (np.bincount(g, weights=c * c) + 150**2 / 1000**2)
    np.testing.assert_allclose(result["bias"], expected)
    assert len(result["cost"]) == len(y)


def test_point_mixture_retains_good_points_in_contaminated_group():
    y = np.r_[np.full(30, 80.0), 7000.0]
    groups = np.zeros(len(y), dtype=int)
    result = grouped_mixture_profile(y, np.ones(len(y)), groups, 1)
    assert result["bias"][0] == pytest.approx(80, abs=2)
    assert np.min(result["signal_probability"][:-1]) > 0.99
    assert result["signal_probability"][-1] < 1e-4
    assert len(result["cost"]) == 31 and np.isfinite(result["cost"]).all()


def test_grouped_profile_is_independent_across_source_groups():
    y = np.array([40.0, 50.0, 60.0, 8000.0, -70.0, -75.0, -80.0])
    design = np.ones(len(y))
    groups = np.array([0, 0, 0, 0, 1, 1, 1])
    together = grouped_mixture_profile(y, design, groups, 2)
    for g in (0, 1):
        mask = groups == g
        separate = grouped_mixture_profile(y[mask], design[mask], np.zeros(mask.sum(), int), 1)
        assert together["bias"][g] == pytest.approx(separate["bias"][0])
        np.testing.assert_allclose(together["cost"][mask], separate["cost"])


@pytest.mark.parametrize("phase_mixture", [False, True])
def test_sparse_prior_replaces_only_means_and_declared_phase_priors(phase_mixture):
    class Problem:
        method = "receiver_smooth"
        labels = np.array([0, 1])
        scan = SimpleNamespace(sky={"phase_sigma_s": np.array([0.2, 0.4])})

        def residual(self, x, *, details=False):
            value = np.array([10.0, 20.0, 30.0, 0.3, 2.0, 0.0, 2.0, 0.5, 1.0, 7.0, 8.0])
            return (value, ["diagnostic"]) if details else value

        def decode(self, x):
            return dict(
                beta=np.r_[np.zeros(4), 150 * np.array([2.0, 4.0, -1.0, 1.0])],
                phases=np.array([0.1, 0.4]),
                smooth=np.array([[1400.0], [1600.0]]),
            )

    base = Problem()
    wrapped = SparsePriors(base, phase_mixture=phase_mixture)
    r, diagnostics = wrapped.residual(None, details=True)
    np.testing.assert_array_equal(
        r[[0, 1, 2, 4, 6, 9, 10]], base.residual(None)[[0, 1, 2, 4, 6, 9, 10]]
    )
    np.testing.assert_allclose(r[[3, 5]], np.sqrt(mixture_cost(np.array([3.0, 0.0]), 0.5, 10, 0.9)))
    if phase_mixture:
        np.testing.assert_allclose(
            r[7:9], np.sqrt(mixture_cost(np.array([0.1, 0.4]), np.array([0.2, 0.4]), 3, 0.9))
        )
    else:
        np.testing.assert_allclose(r[7:9], [0.5, 1.0])
    assert diagnostics == ["diagnostic"]
