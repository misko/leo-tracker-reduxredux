"""Synthetic algebraic qualification; no RF data or nonlinear position fits."""

import numpy as np
import pytest
from linear_contrast import fit_projected_contrasts, projected_ridge, shrink_zero_sum_means


def null_basis(count):
    return np.linalg.svd(np.ones((1, count)), full_matrices=True)[2][1:].T


def augmented_reference(y, design, background, weights, sigma):
    """Independent full augmented ridge least squares, without projection."""
    root = np.sqrt(weights)
    matrix = np.column_stack([background, design]) * root[:, None]
    penalty = np.column_stack(
        [
            np.zeros((design.shape[1], background.shape[1])),
            np.eye(design.shape[1]) / sigma,
        ]
    )
    solution = np.linalg.lstsq(
        np.vstack([matrix, penalty]), np.r_[root * y, np.zeros(design.shape[1])], rcond=None
    )[0]
    return solution[background.shape[1] :]


def fixture():
    ids = np.tile([11, 22, 33], 20)
    times = np.arange(len(ids), dtype=float)
    channel = np.tile([0, 0, 1, 1, 2], 12)
    values = np.array([8, -3, -5])[np.searchsorted([11, 22, 33], ids)]
    values = values + 7 + 0.2 * times + 3 * (channel == 1) - 2 * (channel == 2)
    values = values + 0.1 * np.sin(times)
    weights = np.linspace(0.2, 2.0, len(ids))
    background = np.column_stack([np.ones(len(ids)), times, channel == 1, channel == 2])
    design = np.eye(3)[np.searchsorted([11, 22, 33], ids)]
    return values, ids, times, channel, weights, background, design


def test_projected_coefficients_equal_full_augmented_ridge():
    y, _, _, _, weights, background, onehot = fixture()
    design = onehot @ null_basis(3)
    result = projected_ridge(y, design, background, weights, 4.0)
    expected = augmented_reference(y, design, background, weights, 4.0)
    np.testing.assert_allclose(result["coefficients"], expected, atol=1e-11, rtol=1e-11)
    assert result["data_rank"] == 2
    assert result["background_rank"] == 4


def test_outer_contrasts_equal_augmented_solution_and_zero_sum():
    y, ids, times, channel, weights, background, onehot = fixture()
    result = fit_projected_contrasts(y, ids, times, channel, sigma_hz=4, weights=weights)
    basis = null_basis(3)
    expected = basis @ augmented_reference(y, onehot @ basis, background, weights, 4)
    np.testing.assert_array_equal(result["satellite_ids"], [11, 22, 33])
    np.testing.assert_allclose(result["contrasts_hz"], expected, atol=1e-10, rtol=1e-10)
    assert abs(sum(result["contrasts_hz"])) < 1e-12


def test_receiver_exchange_satellite_permutation_and_row_order():
    y, ids, times, channel, weights, _, _ = fixture()
    baseline = fit_projected_contrasts(y, ids, times, channel, sigma_hz=4, weights=weights)
    exchanged = fit_projected_contrasts(-y, ids, times, channel, sigma_hz=4, weights=weights)
    np.testing.assert_allclose(exchanged["contrasts_hz"], -baseline["contrasts_hz"], atol=1e-11)
    relabel = {11: 70, 22: 10, 33: 40}
    permuted_ids = np.array([relabel[int(i)] for i in ids])
    order = np.random.default_rng(728).permutation(len(ids))
    permuted = fit_projected_contrasts(
        y[order],
        permuted_ids[order],
        times[order],
        channel[order],
        sigma_hz=4,
        weights=weights[order],
    )
    mapped = dict(zip(permuted["satellite_ids"], permuted["contrasts_hz"], strict=True))
    for satellite, value in zip(baseline["satellite_ids"], baseline["contrasts_hz"], strict=True):
        assert mapped[relabel[int(satellite)]] == pytest.approx(value, abs=1e-10)


def test_background_reparameterization_redundancy_and_offset_invariance():
    y, _, _, _, weights, background, onehot = fixture()
    design = onehot @ null_basis(3)
    baseline = projected_ridge(y, design, background, weights, 4)
    transform = np.array([[1, 2, 0, 0], [0, 3, 1, 0], [0, 0, 2, 1], [0, 0, 0, 4]])
    alternative = np.column_stack(
        [background @ transform, background[:, 0], background[:, 1] + background[:, 2]]
    )
    changed = projected_ridge(
        y + background @ np.array([10, -2, 3, 7]), design, alternative, weights, 4
    )
    np.testing.assert_allclose(changed["coefficients"], baseline["coefficients"], atol=1e-10)
    assert changed["background_rank"] == baseline["background_rank"] == 4


def test_sigma_zero_is_exact_zero_and_ineligible_satellites_are_noop():
    y, ids, times, channel, weights, _, _ = fixture()
    result = fit_projected_contrasts(y, ids, times, channel, sigma_hz=0, weights=weights)
    np.testing.assert_array_equal(result["contrasts_hz"], np.zeros(3))
    # Only one satellite reaches the ten-pair threshold.
    mask = (ids == 11) | (np.arange(len(ids)) < 20)
    result = fit_projected_contrasts(y[mask], ids[mask], times[mask], channel[mask], sigma_hz=4)
    assert result["no_op"]
    np.testing.assert_array_equal(result["contrasts_hz"], np.zeros(3))


@pytest.mark.parametrize("confound", ["time", "channel"])
def test_fully_confounded_contrast_is_zero_and_not_identified(confound):
    ids = np.repeat([1, 2], 12)
    times = np.repeat([0.0, 1.0], 12) if confound == "time" else np.tile(np.arange(12), 2)
    channel = np.zeros(24, int) if confound == "time" else np.repeat([0, 1], 12)
    result = fit_projected_contrasts(np.repeat([50.0, -50.0], 12), ids, times, channel, sigma_hz=50)
    np.testing.assert_allclose(result["contrasts_hz"], 0, atol=1e-12)
    assert result["data_rank"] == 0


def test_unit_conversion_preserves_physical_solution():
    y, ids, times, channel, weights, _, _ = fixture()
    hz = fit_projected_contrasts(y, ids, times, channel, sigma_hz=4, weights=weights)
    scaled = fit_projected_contrasts(
        y * 1000, ids, times * 0.001 + 1000, channel, sigma_hz=4000, weights=weights / 1000**2
    )
    np.testing.assert_allclose(scaled["contrasts_hz"] / 1000, hz["contrasts_hz"], atol=1e-8)


def test_profiled_solution_matches_zero_sum_constrained_quadratic_kkt():
    y, ids, times, channel, weights, background, onehot = fixture()
    sigma = 4.0
    result = fit_projected_contrasts(y, ids, times, channel, sigma_hz=sigma, weights=weights)
    full = np.column_stack([background, onehot])
    precision = full.T @ (weights[:, None] * full)
    precision[4:, 4:] += np.eye(3) / sigma**2
    constraint = np.r_[np.zeros(4), np.ones(3)]
    kkt = np.block([[precision, constraint[:, None]], [constraint[None, :], np.zeros((1, 1))]])
    rhs = np.r_[full.T @ (weights * y), 0]
    expected = np.linalg.solve(kkt, rhs)
    np.testing.assert_allclose(result["contrasts_hz"], expected[4:7], atol=1e-10)
    delta = np.asarray(result["contrasts_hz"])
    beta = np.linalg.lstsq(
        background * np.sqrt(weights)[:, None], (y - onehot @ delta) * np.sqrt(weights), rcond=None
    )[0]
    gradient = onehot.T @ (weights * (background @ beta + onehot @ delta - y)) + delta / sigma**2
    np.testing.assert_allclose(gradient, np.full(3, gradient.mean()), atol=1e-10)


def test_intercept_only_shrinkage_matches_closed_form_equal_counts():
    ids = np.tile([1, 2, 3], 10)
    y = np.tile([9.0, 2.0, -2.0], 10)
    result = shrink_zero_sum_means(y, ids, sigma_hz=2)
    centered = np.array([9.0, 2.0, -2.0]) - 3.0
    expected = centered * 10 / (10 + 1 / 2**2)
    np.testing.assert_allclose(result["contrasts_hz"], expected, atol=1e-12)


def test_ineligible_rows_do_not_change_eligible_fit():
    ids = np.tile([1, 2], 10)
    y = np.tile([3.0, -3.0], 10)
    times = np.arange(20, dtype=float)
    channels = np.zeros(20, int)
    baseline = fit_projected_contrasts(y, ids, times, channels, sigma_hz=3)
    result = fit_projected_contrasts(
        np.r_[y, np.full(9, 1e9)],
        np.r_[ids, np.full(9, 3)],
        np.r_[times, np.arange(9) + 1000],
        np.r_[channels, np.ones(9, int)],
        sigma_hz=3,
    )
    np.testing.assert_allclose(result["contrasts_hz"][:2], baseline["contrasts_hz"], atol=1e-12)
    assert result["contrasts_hz"][2] == 0
    np.testing.assert_array_equal(result["eligible_satellite_ids"], [1, 2])


def test_grouped_shrinkage_matches_unequal_weight_constrained_quadratic():
    ids = np.repeat([1, 2, 3], [10, 12, 15])
    y = 0.2 * np.arange(len(ids)) + np.repeat([4.0, -3.0, 8.0], [10, 12, 15])
    weights = np.linspace(0.2, 3, len(ids))
    sigma = 3.0
    result = shrink_zero_sum_means(y, ids, sigma_hz=sigma, weights=weights)
    design = np.eye(3)[ids - 1]
    hessian = design.T @ (weights[:, None] * design) + np.eye(3) / sigma**2
    rhs = design.T @ (weights * y)
    kkt = np.block([[hessian, np.ones((3, 1))], [np.ones((1, 3)), np.zeros((1, 1))]])
    expected = np.linalg.solve(kkt, np.r_[rhs, 0])
    np.testing.assert_allclose(result["contrasts_hz"], expected[:3], atol=1e-12)
    assert result["lagrange_multiplier"] == pytest.approx(expected[3], abs=1e-12)
    assert abs(sum(result["contrasts_hz"])) < 1e-12


@pytest.mark.parametrize("sigma", [-1, float("nan"), float("inf")])
def test_invalid_prior_scales_fail_explicitly(sigma):
    y, ids, times, channel, _, _, _ = fixture()
    with pytest.raises(ValueError, match="sigma_hz"):
        fit_projected_contrasts(y, ids, times, channel, sigma_hz=sigma)
