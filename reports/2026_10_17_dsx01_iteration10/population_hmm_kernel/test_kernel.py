"""Independent tiny enumeration and normalized-distribution HMM oracles."""

from itertools import product

import numpy as np
import pytest
from kernel import evaluate
from numpy.testing import assert_allclose, assert_array_equal
from scipy.special import softmax


def enumerate_paths(e, w, s, observed):
    n, k = e.shape
    pi = softmax(w, axis=1)
    evidence = 0.0
    posterior = np.zeros((n, k))
    for path in product(range(k), repeat=n):
        p = pi[0, path[0]]
        for row in range(n):
            if row:
                i, j = path[row - 1], path[row]
                p *= s[row, i] * (i == j) + (1 - s[row, i]) * pi[row, j]
            if observed[row]:
                p *= np.exp(e[row, path[row]])
        evidence += p
        for row, state in enumerate(path):
            posterior[row, state] += p
    return -np.log(evidence), posterior / evidence


def sample():
    return (
        np.log(np.array([[0.2, 0.7], [0.6, 0.3], [0.4, 0.8]])),
        np.array([[0.2, -0.3], [-0.4, 0.7], [0.1, -0.2]]),
        np.array([[0.2, 0.3], [0.65, 0.25], [0.4, 0.75]]),
        np.array([True, False, True]),
    )


def test_explicit_latent_and_transition_enumeration_with_missing():
    e, w, s, use = sample()
    result = evaluate(e, w, s, use)
    nll, posterior = enumerate_paths(e, w, s, use)
    assert_allclose(result.nll, nll, atol=1e-14, rtol=0)
    assert_allclose(result.posterior, posterior, atol=1e-14, rtol=0)
    assert result.log_normalizers[1] == 0
    assert_array_equal(result.log_emission_gradient[1], 0)
    assert np.max(abs(result.reset_log_weight_gradient[1])) > 0


def test_all_three_gradient_fields_finite_difference_and_reset_gauge():
    args = list(sample())
    result = evaluate(*args)
    gradients = (
        result.log_emission_gradient,
        result.reset_log_weight_gradient,
        result.stay_probability_gradient,
    )
    for field, gradient in enumerate(gradients):
        for index in np.ndindex(args[field].shape):
            a, b = [x.copy() for x in args], [x.copy() for x in args]
            a[field][index] += 1e-6
            b[field][index] -= 1e-6
            numerical = (evaluate(*a).nll - evaluate(*b).nll) / 2e-6
            assert_allclose(gradient[index], numerical, atol=1e-9, rtol=1e-6)
    assert_allclose(result.reset_log_weight_gradient.sum(axis=1), 0, atol=2e-16)
    shifted = evaluate(args[0], args[1] + np.array([13.0, -7.0, 3.0])[:, None], args[2], args[3])
    assert_allclose(shifted.nll, result.nll, atol=1e-14, rtol=0)


@pytest.mark.parametrize("observed", [np.array([1, 1, 1], bool), np.array([1, 0, 1], bool)])
def test_discrete_normalized_emissions_integrate_to_one(observed):
    emission_probabilities = np.array([[0.7, 0.2], [0.3, 0.8]])  # outcomes x state
    _, w, s, _ = sample()
    total = 0.0
    for outcomes in product(range(2), repeat=int(observed.sum())):
        y = np.zeros(3, int)
        y[observed] = outcomes
        e = np.log(emission_probabilities[y])
        total += np.exp(-evaluate(e, w, s, observed).nll)
    assert_allclose(total, 1.0, atol=1e-14, rtol=0)


def test_all_missing_has_no_information_and_missing_input_is_ignored():
    e, w, s, _ = sample()
    missing = np.zeros(3, bool)
    r = evaluate(e, w, s, missing)
    assert r.nll == 0
    for gradient in (
        r.log_emission_gradient,
        r.reset_log_weight_gradient,
        r.stay_probability_gradient,
    ):
        assert_array_equal(gradient, 0)
    e[:] = np.array([np.nan, np.inf])
    other = evaluate(e, w, s, missing)
    assert_array_equal(r.posterior, other.posterior)
    use = np.array([1, 0, 1], bool)
    base = sample()
    changed = base[0].copy()
    changed[1] = [np.nan, -np.inf]
    a, b = evaluate(*base), evaluate(changed, w, s, use)
    for name in a.__dataclass_fields__:
        assert_array_equal(getattr(a, name), getattr(b, name))


def test_zero_stay_is_independent_mixture_for_value_posterior_and_gradients():
    e, w, s, observed = sample()
    s[:] = 0
    r = evaluate(e, w, s, observed)
    pi = softmax(w, axis=1)
    g = np.where(observed[:, None], np.exp(e), 1.0)
    total = np.sum(pi * g, axis=1)
    posterior = pi * g / total[:, None]
    assert_allclose(r.nll, -np.log(total).sum(), atol=1e-14)
    assert_allclose(r.posterior, posterior, atol=1e-14)
    assert_allclose(r.log_emission_gradient, -posterior * observed[:, None], atol=1e-14)
    assert_allclose(r.reset_log_weight_gradient, pi - posterior, atol=1e-14)
    for row, state in product(range(1, 3), range(2)):
        changed = s.copy()
        changed[row, state] = 1e-7
        fd = (evaluate(e, w, changed, observed).nll - r.nll) / 1e-7
        assert_allclose(r.stay_probability_gradient[row, state], fd, atol=1e-7)


def test_inactive_states_and_stay_boundaries_match_enumeration_and_one_sided_gradients():
    e, w, s, observed = sample()
    w[1, 1] = -np.inf
    e[2, 0] = -np.inf
    s[1] = [0.0, 1.0]
    s[2] = [1.0, 0.0]
    r = evaluate(e, w, s, observed)
    nll, posterior = enumerate_paths(e, w, s, observed)
    assert_allclose(r.nll, nll, atol=1e-14)
    assert_allclose(r.posterior, posterior, atol=1e-14)
    assert r.reset_log_weight_gradient[1, 1] == 0
    assert r.log_emission_gradient[2, 0] == 0
    for row, state in product(range(1, 3), range(2)):
        direction = 1 if s[row, state] == 0 else -1
        changed = s.copy()
        changed[row, state] += direction * 1e-7
        fd = (evaluate(e, w, changed, observed).nll - r.nll) / (direction * 1e-7)
        assert_allclose(r.stay_probability_gradient[row, state], fd, atol=2e-6)


def test_long_tiny_density_stability_and_state_permutation():
    rng = np.random.default_rng(1729)
    e = -10000.0 + rng.normal(size=(1000, 5))
    w = rng.normal(size=e.shape)
    s = rng.uniform(0.01, 0.99, size=e.shape)
    observed = rng.random(len(e)) > 0.2
    r = evaluate(e, w, s, observed)
    assert np.isfinite(r.nll)
    assert_allclose(r.posterior.sum(axis=1), 1.0, atol=1e-14)
    order = np.array([3, 0, 4, 1, 2])
    p = evaluate(e[:, order], w[:, order], s[:, order], observed)
    assert_allclose(p.nll, r.nll, atol=1e-8, rtol=0)
    for name in (
        "posterior",
        "log_emission_gradient",
        "reset_log_weight_gradient",
        "stay_probability_gradient",
    ):
        assert_allclose(getattr(p, name), getattr(r, name)[:, order], atol=1e-10)


def test_log_domain_rescues_underflowed_state_without_zero_times_infinity():
    e = np.array([[np.nan, np.nan], [0.0, -1000.0]])
    w = np.array([[-1000.0, 0.0], [-np.inf, 0.0]])
    s = np.array([[0.0, 0.0], [1.0, 0.0]])
    r = evaluate(e, w, s, np.array([False, True]))
    assert_allclose(r.nll, 1000.0 - np.log(2), atol=1e-12)
    assert_allclose(r.posterior, 0.5, atol=1e-12)
    assert_allclose(r.stay_probability_gradient[1, 0], -0.5, atol=1e-12)


def test_genuine_gradient_overflow_is_rejected_not_clipped():
    e = np.array([[0.0, 0.0], [0.0, -2000.0]])
    w = np.array([[0.0, -np.inf], [-1000.0, 0.0]])
    with pytest.raises(FloatingPointError, match="overflow"):
        evaluate(e, w, np.zeros_like(e), np.array([False, True]))


def test_single_state_single_row_and_input_immutability():
    r = evaluate(np.log([[0.4]]), np.array([[17.0]]), np.array([[1.0]]), np.array([True]))
    assert_allclose(r.nll, -np.log(0.4))
    assert_array_equal(r.posterior, 1.0)
    assert_array_equal(r.log_emission_gradient, -1.0)
    assert_array_equal(r.reset_log_weight_gradient, 0.0)
    assert_array_equal(r.stay_probability_gradient, 0.0)
    args = sample()
    copies = [a.copy() for a in args]
    evaluate(*args)
    for original, copy in zip(args, copies, strict=True):
        assert_array_equal(original, copy)


def test_logarithmic_overflow_and_observed_invalid_emissions_are_rejected():
    with pytest.raises(FloatingPointError):
        evaluate(np.zeros((1, 2)), np.array([[1e308, -1e308]]), np.zeros((1, 2)), np.array([True]))
    for invalid in (np.nan, np.inf):
        e, w, s, observed = sample()
        e[0, 0] = invalid
        with pytest.raises(ValueError, match="Observed log emissions"):
            evaluate(e, w, s, observed)


def test_huge_common_reset_and_emission_gauges_preserve_mass_and_derivatives():
    zero = np.zeros((3, 2))
    stay = np.full_like(zero, 0.4)
    observed = np.ones(3, bool)
    baseline = evaluate(zero, zero, stay, observed)
    reset_shift = evaluate(zero, np.full_like(zero, 1e100), stay, observed)
    assert_allclose(reset_shift.nll, 0.0, atol=1e-14)
    assert_allclose(reset_shift.reset_log_weight_gradient, 0.0, atol=1e-14)
    both_shift = evaluate(np.full_like(zero, -1e100), np.full_like(zero, 1e100), stay, observed)
    assert abs(both_shift.nll - 3e100) <= np.spacing(3e100)
    for name in (
        "posterior",
        "log_emission_gradient",
        "reset_log_weight_gradient",
        "stay_probability_gradient",
    ):
        assert_allclose(getattr(reset_shift, name), getattr(baseline, name), atol=1e-14)
        assert_allclose(getattr(both_shift, name), getattr(baseline, name), atol=1e-14)
    assert_allclose(both_shift.posterior.sum(axis=1), 1.0, atol=1e-14)


def test_unsafe_extreme_contrasts_fail_closed_instead_of_spurious_normalization():
    with pytest.raises(FloatingPointError, match="dynamic range/resolution"):
        evaluate(
            np.array([[0.0, -1e100]]), np.array([[-1e100, 0.0]]), np.zeros((1, 2)), np.array([True])
        )


def test_supported_billion_log_contrast_keeps_forward_mass_and_gradients():
    r = evaluate(
        np.array([[0.0, -1.6e9]]), np.array([[-1.6e9, 0.0]]), np.zeros((1, 2)), np.array([True])
    )
    assert_allclose(r.posterior, 0.5, atol=1e-14)
    assert_allclose(r.log_emission_gradient, -0.5, atol=1e-14)
    assert_allclose(r.reset_log_weight_gradient, [[-0.5, 0.5]], atol=1e-14)


def test_cloned_identical_state_preserves_value_posterior_and_shared_gradients():
    e, w, s, observed = sample()
    original = evaluate(e, w, s, observed)
    ec, sc = e[:, [0, 0, 1]], s[:, [0, 0, 1]]
    wc = w[:, [0, 0, 1]] + np.log(np.array([0.3, 0.7, 1.0]))
    cloned = evaluate(ec, wc, sc, observed)
    assert_allclose(cloned.nll, original.nll, atol=1e-14)
    for name in (
        "posterior",
        "log_emission_gradient",
        "reset_log_weight_gradient",
        "stay_probability_gradient",
    ):
        x, y = getattr(original, name), getattr(cloned, name)
        assert_allclose(y[:, 0] + y[:, 1], x[:, 0], atol=1e-14)
        assert_allclose(y[:, 2], x[:, 1], atol=1e-14)


def test_conditional_missing_point_pdf_matches_train_posterior_and_integrates():
    e, w, s, observed = sample()
    train = evaluate(e, w, s, observed)
    probabilities = np.array([[0.7, 0.2], [0.3, 0.8]])
    total = 0.0
    for state_pdf in probabilities:
        complete = e.copy()
        complete[1] = np.log(state_pdf)
        all_rows = evaluate(complete, w, s, np.ones(3, bool))
        conditional_pdf = np.exp(train.nll - all_rows.nll)
        assert_allclose(conditional_pdf, train.posterior[1] @ state_pdf, atol=1e-14)
        total += conditional_pdf
    assert_allclose(total, 1.0, atol=1e-14)


def test_invalid_shapes_probabilities_reset_rows_and_impossible_data():
    e, w, s, observed = sample()
    with pytest.raises(ValueError, match="boolean"):
        evaluate(e, w, s, observed.astype(int))
    bad = w.copy()
    bad[1] = -np.inf
    with pytest.raises(ValueError, match="active reset"):
        evaluate(e, bad, s, observed)
    bad = s.copy()
    bad[1, 0] = 1.1
    with pytest.raises(ValueError, match="Stay"):
        evaluate(e, w, bad, observed)
    bad = e.copy()
    bad[0] = -np.inf
    with pytest.raises(ValueError, match="zero or nonfinite"):
        evaluate(bad, w, s, observed)
    with pytest.raises(ValueError, match="Aligned"):
        evaluate(e, w[:, :1], s, observed)
