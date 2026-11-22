import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental.analytic_radio_variance import (
    LOWER,
    UPPER,
    RadioProfile,
    fit_variance,
)

MARGINS = np.array([.025, .06, .12, .2, .35, .63])


@pytest.mark.parametrize(("ratio", "floor", "strength"), (
    (.7, 8_000., 11_000.),
    (3., 8_000., 11_000.),
    (3., 800., 2_000.),
    (.7, 550_000., 90_000.),
    (3., 150_000., 550_000.),
))
def test_profile_gradient_matches_the_original_model_around_smooth_points(
    ratio, floor, strength,
):
    squares = floor + strength / MARGINS
    profile = RadioProfile(MARGINS, squares)
    step = 1e-5
    precise = [profile.profile(ratio + sign * step, dtype=np.longdouble)[0] for sign in (-1, 1)]
    expected = float((precise[1] - precise[0]) / (2 * step))
    assert profile.gradient(ratio, moving_cap=ratio > 1.) == pytest.approx(
        expected, abs=1e-9,
    )


def test_interior_root_recovers_the_planted_float_profile():
    squares = 8_000. + 11_000. / MARGINS
    np.testing.assert_allclose(fit_variance(MARGINS, squares), [8_000., 11_000.],
                               rtol=1e-13, atol=0.)


@pytest.mark.parametrize(("squares", "which", "limit"), (
    (1200. + 6000. / MARGINS, 0, LOWER),
    (390_000. + 140_000. / MARGINS, 0, UPPER),
    (120_000. + 365_000. / MARGINS, 1, UPPER),
))
def test_refinement_handles_active_floor_and_strength_bounds(squares, which, limit):
    estimate = fit_variance(MARGINS, squares)
    assert estimate[which] == pytest.approx(limit, abs=1e-10, rel=0.)
    ratio = estimate[1] / estimate[0]
    profile = RadioProfile(MARGINS, squares)
    assert abs(profile.gradient(ratio, moving_cap=ratio > 1.)) < 1e-12


def test_kink_and_ratio_endpoints_are_valid_minima():
    squares = np.full_like(MARGINS, 1e9)
    profile = RadioProfile(MARGINS, squares)
    assert profile.gradient(1., moving_cap=False) < 0
    assert profile.gradient(1., moving_cap=True) > 0
    np.testing.assert_array_equal(fit_variance(MARGINS, squares), [UPPER, UPPER])
    np.testing.assert_array_equal(fit_variance(MARGINS, np.zeros_like(MARGINS)), [LOWER, 0.])
    squares = LOWER * (1 + 225 / MARGINS)
    np.testing.assert_array_equal(fit_variance(MARGINS, squares), [LOWER, UPPER])
