import importlib.util
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).parents[2] / "tools/research/ablate_blind_circular_offset.py"
SPEC = importlib.util.spec_from_file_location("ablate_blind_circular_offset", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_dimensionless_circular_factor_has_unit_uniform_mean():
    grid = np.linspace(
        -MODULE.PILOT_ALIAS_HZ / 2, MODULE.PILOT_ALIAS_HZ / 2, 2048, endpoint=False
    )
    for sigma in (3_000.0, 30_000.0, 1_000_000.0):
        factor = MODULE.circular_factor(np.array([31_000.0]), grid, sigma, 0.2)[0]
        assert np.mean(factor) == pytest.approx(1.0, abs=2e-12)


def test_wrapped_normal_matches_independent_image_sum_at_broad_sigma():
    period = MODULE.PILOT_ALIAS_HZ
    grid = np.linspace(-period / 2, period / 2, 257, endpoint=False)
    offset = 0.173 * period
    sigma = period / 2
    actual = MODULE.circular_factor(np.array([offset]), grid, sigma, 0.0)[0]
    residual = offset - grid
    expected = period / (np.sqrt(2 * np.pi) * sigma) * sum(
        np.exp(-0.5 * ((residual + image * period) / sigma) ** 2)
        for image in range(-20, 21)
    )
    np.testing.assert_allclose(actual, expected, rtol=2e-15, atol=2e-15)

    very_broad = MODULE.circular_factor(
        np.array([offset]), grid, 10 * period, 0.0
    )[0]
    assert np.ptp(very_broad) < 2e-12
    assert np.mean(very_broad) == pytest.approx(1.0, abs=2e-12)


def test_circular_factor_is_invariant_to_integer_period_offsets():
    period = MODULE.PILOT_ALIAS_HZ
    grid = np.linspace(-period / 2, period / 2, 513, endpoint=False)
    base = MODULE.circular_factor(np.array([31_234.0]), grid, 30_000.0, 0.05)
    shifted = MODULE.circular_factor(
        np.array([31_234.0 + 10 * period]), grid, 30_000.0, 0.05
    )
    np.testing.assert_allclose(base, shifted, rtol=0, atol=2e-14)


def test_uniform_training_posterior_has_zero_predictive_delta_even_with_null():
    grid = np.linspace(-1, 1, 64, endpoint=False)
    likelihood = np.vstack((np.zeros_like(grid), np.sin(grid), np.full_like(grid, 7.0)))
    delta = MODULE.predictive_delta(
        likelihood, np.array([True, False, False]), np.array([False, True, False])
    )
    assert delta == pytest.approx(0.0, abs=1e-14)


def test_synthetic_shared_circular_offset_predicts_heldout_with_outlier():
    grid = np.linspace(
        -MODULE.PILOT_ALIAS_HZ / 2, MODULE.PILOT_ALIAS_HZ / 2, 1024, endpoint=False
    )
    offsets = np.array([30_000.0, 31_000.0, 29_000.0, -90_000.0, 30_500.0])
    likelihood = np.log(MODULE.circular_factor(offsets, grid, 3_000.0, 0.1))
    delta = MODULE.predictive_delta(
        likelihood, np.array([True, True, True, True, False]), np.array([False] * 4 + [True])
    )
    assert delta > 1.0


def test_null_dominated_track_is_offset_insensitive():
    grid = np.linspace(
        -MODULE.PILOT_ALIAS_HZ / 2, MODULE.PILOT_ALIAS_HZ / 2, 512, endpoint=False
    )
    log_likelihood = MODULE.track_log_likelihood(
        np.array([-1000.0]), 0.0, np.array([20_000.0]), grid, 3_000.0, 0.05
    )
    assert np.ptp(log_likelihood) < 1e-12
