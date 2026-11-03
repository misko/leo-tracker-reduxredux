"""Pure normalization, legacy closure and fixed-state availability controls."""

from types import SimpleNamespace

import numpy as np
import pytest
from kernel import ALIAS_HZ, TAIL_TOLERANCE, evaluate, unsupported_peak_ceiling, wrapped_normal
from leo.analysis.shared_scan_model import density as legacy_density
from numpy.testing import assert_allclose, assert_array_equal


def fixture(n=3, m=2):
    y = np.linspace(-80.0, 90.0, n)
    selected = y[:, None] + np.array([-60.0, 130.0, 19000.0])
    w = np.broadcast_to([0.8, 0.4, 0.7], selected.shape).copy()
    q = np.array([0.6, 0.5, 0.5])
    unsupported = y[:, None] + np.linspace(-100.0, 50000.0, m)[None, :]
    uw = np.full_like(unsupported, 0.6)
    g = np.broadcast_to(np.linspace(40.0, 90000.0, m), unsupported.shape).copy()
    return [y, selected, w, q, unsupported, uw, g]


def test_eta_zero_exact_legacy_pdf_classifier_and_available_gradients():
    args = fixture(n=9, m=5)
    args[1][::2, 0] += ALIAS_HZ / 2
    result = evaluate(*args, eta=0.0)
    y, mu, w, q = args[:4]
    legacy, details = legacy_density(
        y, mu, w, np.full(len(y), 125.0), q, SimpleNamespace(detection_budget=1.6, clutter_rate=0.5)
    )
    assert_array_equal(result.row_nll, details["row_nll"])
    assert result.nll == legacy.nll
    assert_array_equal(result.selected_responsibility, legacy.responsibilities)
    assert_array_equal(result.clutter_probability, legacy.clutter_probability)
    assert_array_equal(result.selected_mean_gradient, legacy.prediction_gradient)
    assert_array_equal(result.selected_visibility_gradient, details["visibility_weight_gradient"])
    assert_array_equal(result.selected_q_gradient, details["detection_probability_gradient"])
    best = legacy.responsibilities.argmax(axis=1)
    assert_array_equal(result.best_index, best)
    assert_array_equal(result.best_is_unsupported, False)
    assert_array_equal(result.residual_hz, legacy.residual_hz[np.arange(len(y)), best])
    assert_array_equal(
        result.associated,
        legacy.responsibilities[np.arange(len(y)), best] > legacy.clutter_probability,
    )
    assert_array_equal(result.unsupported_responsibility, 0.0)
    assert_array_equal(result.unsupported_mean_gradient, 0.0)
    assert_array_equal(result.unsupported_visibility_gradient, 0.0)


@pytest.mark.parametrize("zero_visibility,broad", [(False, False), (True, False), (False, True)])
def test_normalized_circle_pdf_zero_visibility_broad_width_and_seam(zero_visibility, broad):
    alias = 1000.0
    y = np.linspace(-alias / 2, alias / 2, 12001)
    selected = np.broadcast_to([-499.0, 40.0, 499.0], (len(y), 3)).copy()
    unsupported = np.broadcast_to([-500.0, 499.0], (len(y), 2)).copy()
    visibility = np.full_like(selected, 0.0 if zero_visibility else 0.8)
    uw = np.full_like(unsupported, 0.0 if zero_visibility else 0.7)
    slope = np.full_like(unsupported, 1e8 if broad else 200.0)
    result = evaluate(
        y, selected, visibility, np.array([0.6, 0.5, 0.5]), unsupported, uw, slope, alias_hz=alias
    )
    assert_allclose(np.trapezoid(np.exp(-result.row_nll), y), 1.0, atol=2e-12, rtol=0)
    assert_allclose(
        result.selected_responsibility.sum(1)
        + result.unsupported_responsibility.sum(1)
        + result.clutter_probability,
        1.0,
        atol=1e-15,
    )
    assert_allclose(result.row_nll[0], result.row_nll[-1], atol=1e-12)
    if zero_visibility:
        assert_allclose(result.row_nll, np.log(alias), atol=1e-15)
        assert_array_equal(result.clutter_probability, 1.0)


@pytest.mark.parametrize("ratio", [0.125, 0.4, 1.2, 2.0, 10.0])
def test_wrapped_normal_normalization_gradient_integrals_and_tail_certificates(ratio):
    alias = 1000.0
    r = np.linspace(-alias / 2, alias / 2, 12001)
    phi, dmu, dsigma, reports = wrapped_normal(r, np.full_like(r, ratio * alias), alias_hz=alias)
    assert_allclose(np.trapezoid(phi, r), 1.0, atol=2e-12)
    assert_allclose(np.trapezoid(dmu, r), 0.0, atol=1e-15)
    assert_allclose(np.trapezoid(dsigma, r), 0.0, atol=1e-15)
    assert_allclose(phi[0], phi[-1], atol=1e-18)
    for report in reports:
        for key, value in report.items():
            if key not in ("method", "radius"):
                assert value <= TAIL_TOLERANCE
    if ratio >= 2.0:
        assert_array_equal(phi, np.full_like(phi, 1 / alias))
        assert_array_equal(dmu, 0.0)
        assert_array_equal(dsigma, 0.0)


def test_mean_sigma_visibility_and_fixed_budget_q_gradients_finite_difference():
    args = fixture()
    result = evaluate(*args)
    for field, gradient in (
        (1, result.selected_mean_gradient),
        (2, result.selected_visibility_gradient),
        (4, result.unsupported_mean_gradient),
        (5, result.unsupported_visibility_gradient),
    ):
        step = 1e-3 if field in (1, 4) else 1e-6
        for index in np.ndindex(args[field].shape):
            a, b = [x.copy() for x in args], [x.copy() for x in args]
            a[field][index] += step
            b[field][index] -= step
            fd = (evaluate(*a).nll - evaluate(*b).nll) / (2 * step)
            assert_allclose(gradient[index], fd, atol=2e-8, rtol=2e-5)
    for index in range(2):
        a, b = [x.copy() for x in args], [x.copy() for x in args]
        a[3][index] += 1e-6
        a[3][-1] -= 1e-6
        b[3][index] -= 1e-6
        b[3][-1] += 1e-6
        fd = (evaluate(*a).nll - evaluate(*b).nll) / 2e-6
        assert_allclose(
            result.selected_q_gradient[index] - result.selected_q_gradient[-1], fd, atol=2e-8
        )
    for key, base, derivative, step in (
        ("sigma_hz", 125.0, result.base_sigma_gradient, 1e-3),
        ("sigma_relative_s", 2.0, result.relative_sigma_gradient, 1e-5),
    ):
        fd = (
            evaluate(*args, **{key: base + step}).nll - evaluate(*args, **{key: base - step}).nll
        ) / (2 * step)
        assert_allclose(derivative, fd, atol=2e-8, rtol=2e-5)


def test_wrapped_mean_and_effective_sigma_derivatives_at_seam_and_broad_width():
    residual = np.array([-499.99, 0.0, 450.0, 499.99])
    sigma = np.array([125.0, 400.0, 900.0, 1400.0])
    phi, mean_gradient, sigma_gradient, _ = wrapped_normal(residual, sigma, alias_hz=1000.0)
    h = 1e-3
    # Increasing prediction mean decreases the residual.
    a = wrapped_normal(residual - h, sigma, alias_hz=1000.0)[0]
    b = wrapped_normal(residual + h, sigma, alias_hz=1000.0)[0]
    assert_allclose(mean_gradient, (a - b) / (2 * h), atol=1e-13, rtol=1e-5)
    a = wrapped_normal(residual, sigma + h, alias_hz=1000.0)[0]
    b = wrapped_normal(residual, sigma - h, alias_hz=1000.0)[0]
    assert_allclose(sigma_gradient, (a - b) / (2 * h), atol=1e-13, rtol=1e-5)
    assert np.all(phi > 0)


def test_candidate_permutation_preserves_pdf_classification_and_gradients():
    args = fixture(n=7, m=3)
    old = evaluate(*args)
    a = [x.copy() for x in args]
    selected_order, population_order = np.array([2, 0, 1]), np.array([1, 2, 0])
    a[1], a[2], a[3] = a[1][:, selected_order], a[2][:, selected_order], a[3][selected_order]
    a[4], a[5], a[6] = (
        a[4][:, population_order],
        a[5][:, population_order],
        a[6][:, population_order],
    )
    new = evaluate(*a)
    assert_allclose(new.row_nll, old.row_nll, atol=1e-14)
    assert_array_equal(new.associated, old.associated)
    assert_allclose(
        new.selected_mean_gradient, old.selected_mean_gradient[:, selected_order], atol=1e-15
    )
    assert_allclose(
        new.unsupported_visibility_gradient,
        old.unsupported_visibility_gradient[:, population_order],
        atol=1e-15,
    )
    mapped = np.where(
        new.best_is_unsupported, population_order[new.best_index], selected_order[new.best_index]
    )
    assert_array_equal(mapped, old.best_index)
    assert_array_equal(new.best_is_unsupported, old.best_is_unsupported)


def test_q_mass_is_fixed_across_bank_sizes_and_empty_population_exactly_nests():
    for count in (0, 1, 8, 800):
        args = fixture(n=1, m=count)
        r = evaluate(*args)
        assert_allclose(r.selected_q.sum() + r.unsupported_q.sum(), 1.6, atol=1e-15)
        assert_allclose(r.unsupported_q.sum(), 0.16 if count else 0.0, atol=1e-15)
        if count == 0:
            zero = evaluate(*args, eta=0.0)
            assert_array_equal(r.row_nll, zero.row_nll)
            assert_array_equal(r.selected_mean_gradient, zero.selected_mean_gradient)
            assert r.diagnostics["effective_eta"] == 0.0


def test_800_object_analytic_ceiling_prohibits_new_fixed_state_associations():
    ceiling = unsupported_peak_ceiling(800)
    assert 0.289 < ceiling < 0.291
    rng = np.random.default_rng(500)
    args = fixture(n=31, m=800)
    args[1] = args[0][:, None] + np.broadcast_to([0.0, 2000.0, 3000.0], (31, 3))
    args[1][:, 0] += np.linspace(0.0, 1000.0, 31)
    args[4] = args[0][:, None] + rng.uniform(-ALIAS_HZ / 2, ALIAS_HZ / 2, size=(31, 800))
    args[6][:] = 0.0  # Maximum possible wrapped peak; larger slopes only dilute it.
    old, changed = evaluate(*args, eta=0.0), evaluate(*args, eta=0.1)
    assert np.any(old.associated) and np.any(~old.associated)
    assert not np.any(changed.associated & ~old.associated)
    assert not np.any(changed.unsupported_responsibility > changed.clutter_probability[:, None])
    assert not changed.diagnostics["unsupported_association_possible"]


def test_invalid_inputs_and_numeric_overflow_fail_explicitly():
    args = fixture()
    with pytest.raises(ValueError, match="eta"):
        evaluate(*args, eta=0.2)
    bad = [x.copy() for x in args]
    bad[3][0] += 0.01
    with pytest.raises(ValueError, match="fixed total"):
        evaluate(*bad)
    bad = [x.copy() for x in args]
    bad[5][0, 0] = 1.1
    with pytest.raises(ValueError, match="Visibility"):
        evaluate(*bad)
    bad = [x.copy() for x in args]
    bad[6][:] = 1e308
    with pytest.raises(FloatingPointError):
        evaluate(*bad)
    with pytest.raises(ValueError, match="positive Gaussian"):
        wrapped_normal([0.0], [0.0])
