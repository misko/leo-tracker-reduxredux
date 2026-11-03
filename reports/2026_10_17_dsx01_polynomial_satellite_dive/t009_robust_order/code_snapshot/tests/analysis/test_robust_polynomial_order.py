"""An unsupported endpoint must not create a degree-four calibration curve."""

import numpy as np
import pytest

from leo.analysis.research.robust_polynomial_order import polynomial_orders


def test_isolated_endpoint_is_explicit_clutter_instead_of_a_quartic_bend():
    t = np.r_[np.linspace(0, 26, 26), 34.0]
    rng = np.random.default_rng(15)
    y = 60000 - 2800 * t + 5 * t * t + rng.normal(0, 75, len(t))
    y[-1] += 9500
    original = y.copy()
    fits = polynomial_orders(t, y)
    best = fits[0]
    assert best["degree"] == 2
    assert best["inlier_mask"].tolist() == [True] * 26 + [False]
    assert len(best["residual_hz"]) == len(y) == best["points"]
    assert best["residual_hz"][-1] > 9000
    assert best["inlier_rms_hz"] < 100
    np.testing.assert_array_equal(y, original)


def test_well_supported_quartic_curvature_is_retained():
    t = np.linspace(-1, 1, 60)
    y = 10000 - 1000 * t + 4000 * t**2 - 3000 * t**3 + 8000 * t**4
    y += np.random.default_rng(91).normal(0, 40, len(t))
    best = polynomial_orders(t, y)[0]
    assert best["degree"] == 4
    assert best["inlier_mask"].all()
    assert best["inlier_rms_hz"] < 55


def test_alias_branch_translation_preserves_order_membership_and_score():
    t = np.r_[np.linspace(0, 26, 26), 34.0]
    y = 60000 - 2800 * t + 5 * t * t
    y[-1] += 9500
    a, b = (polynomial_orders(t, y + shift)[0] for shift in (0, 1 / 4.4e-6))
    assert a["degree"] == b["degree"] == 2
    np.testing.assert_array_equal(a["inlier_mask"], b["inlier_mask"])
    np.testing.assert_allclose(a["residual_hz"], b["residual_hz"], atol=1e-7)
    assert a["score"] == pytest.approx(b["score"], abs=1e-7)


def test_score_counts_every_observation_and_charges_higher_orders():
    t = np.linspace(0, 25, 26)
    y = 50000 - 2000 * t + np.random.default_rng(6).normal(0, 30, len(t))
    fits = polynomial_orders(t, y)
    assert fits[0]["degree"] == 1
    for fit in fits:
        assert fit["points"] == len(t)
        assert fit["parameter_penalty"] == pytest.approx((fit["degree"] + 1) * np.log(len(t)))
        assert fit["score"] == pytest.approx(fit["data_cost"] + fit["parameter_penalty"])


@pytest.mark.parametrize(
    "times,values",
    [
        ([0, 1, 2, 3], [1, 2, 3, 4]),
        ([0, 1, 1, 3, 4], [1, 2, 3, 4, 5]),
        ([0, 1, 2, 3, 4], [1, 2, 3, 4, np.nan]),
    ],
)
def test_invalid_samples_are_rejected(times, values):
    with pytest.raises(ValueError, match="paired observations"):
        polynomial_orders(times, values)
