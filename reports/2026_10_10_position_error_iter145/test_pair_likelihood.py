from dataclasses import replace

import numpy as np
import pytest
from pair_likelihood import exclusive, omitted_image_log_bound, paired_likelihood

from leo.analysis.hard60_score import likelihood
from leo.analysis.regional_position_score import ALIAS_HZ
from leo.contracts.regional_position import PositionScore

SCORE = PositionScore("V16", 125.0, 1.6, 0.5, 3.0, 0.15)


def example():
    return (
        np.array([30.0, -50.0, 400.0]),
        np.array([[0.0, 80.0, 1000.0], [40.0, -90.0, 1000.0], [200.0, 500.0, 1000.0]]),
        np.array([[True, True, False], [True, False, True], [True, True, True]]),
    )


def test_exact_zero_and_unpaired():
    y, p, v = example()
    a = likelihood(y, p, v, SCORE)
    b = paired_likelihood(y, p, v, SCORE, [(0, 1)], rho=0)
    assert a.nll == b.nll
    for key in ("responsibilities", "clutter_probability", "prediction_gradient", "residual_hz"):
        np.testing.assert_array_equal(getattr(a, key), getattr(b, key))
    c = paired_likelihood(y, p, v, SCORE, [(0, 1)])
    np.testing.assert_array_equal(c.prediction_gradient[2], a.prediction_gradient[2])
    np.testing.assert_array_equal(c.responsibilities[2], a.responsibilities[2])


def test_chunk_boundary_preserves_every_pair_and_unpaired_tail():
    y, p, v = example()
    one = paired_likelihood(y[:2], p[:2], v[:2], SCORE, [(0, 1)])
    tail = likelihood(y[2:], p[2:], v[2:], SCORE)
    repeated = 257
    yy = np.r_[np.tile(y[:2], repeated), y[2:]]
    pp = np.vstack((np.tile(p[:2], (repeated, 1)), p[2:]))
    vv = np.vstack((np.tile(v[:2], (repeated, 1)), v[2:]))
    pairs = np.arange(2 * repeated).reshape(-1, 2)
    result = paired_likelihood(yy, pp, vv, SCORE, pairs)
    assert result.nll == pytest.approx(repeated * one.nll + tail.nll, abs=1e-10)
    np.testing.assert_allclose(
        result.responsibilities[:-1], np.tile(one.responsibilities, (repeated, 1))
    )
    np.testing.assert_allclose(
        result.prediction_gradient[:-1], np.tile(one.prediction_gradient, (repeated, 1))
    )
    np.testing.assert_array_equal(result.prediction_gradient[-1:], tail.prediction_gradient)


def test_finite_difference_and_pair_exchange():
    y, p, v = example()
    a = paired_likelihood(y, p, v, SCORE, [(0, 1)])
    b = paired_likelihood(y, p, v, SCORE, [(1, 0)])
    assert a.nll == pytest.approx(b.nll, abs=1e-14)
    np.testing.assert_allclose(a.responsibilities, b.responsibilities, atol=1e-15)
    for index in np.ndindex(p.shape):
        step = np.zeros_like(p)
        step[index] = 0.001
        fd = (
            paired_likelihood(y, p + step, v, SCORE, [(0, 1)]).nll
            - paired_likelihood(y, p - step, v, SCORE, [(0, 1)]).nll
        ) / 0.002
        assert fd == pytest.approx(a.prediction_gradient[index], abs=2e-9)
    np.testing.assert_allclose(
        a.responsibilities.sum(axis=1) + a.clutter_probability, 1, atol=3e-16
    )


@pytest.mark.parametrize(
    "mask",
    [
        np.zeros((2, 3), bool),
        np.array([[True, False, False], [False, True, False]]),
        np.ones((2, 3), bool),
    ],
)
def test_explicit_quadratic_label_enumeration(mask):
    y, p, _ = example()
    y, p = y[:2], p[:2]
    out = paired_likelihood(y, p, mask, SCORE, [(0, 1)])
    r = out.residual_hz
    q = SCORE.detection_budget / 3
    a, u, sigma, rho = q / (1 - q), SCORE.clutter_rate / ALIAS_HZ, 125.0, 0.25
    s = a * mask * np.exp(-0.5 * (r / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
    matrix = np.outer(np.r_[u, s[0]], np.r_[u, s[1]])
    for k in range(3):
        matrix[k + 1, k + 1] = (
            a
            * a
            * mask[0, k]
            * mask[1, k]
            * np.exp(
                -(r[0, k] ** 2 - 2 * rho * r[0, k] * r[1, k] + r[1, k] ** 2)
                / (2 * sigma**2 * (1 - rho**2))
            )
            / (2 * np.pi * sigma**2 * np.sqrt(1 - rho**2))
        )
    total = matrix.sum()
    np.testing.assert_allclose(out.responsibilities[0], matrix.sum(axis=1)[1:] / total)
    np.testing.assert_allclose(out.responsibilities[1], matrix.sum(axis=0)[1:] / total)
    logp0 = -SCORE.clutter_rate + mask.sum(axis=1) * np.log1p(-q)
    expected = -np.sum(logp0 - np.log(-np.expm1(logp0))) - np.log(total)
    assert out.nll == pytest.approx(expected, abs=1e-13)


def test_emission_mass_normalization():
    # Correlation replaces a normalized diagonal density by another normalized
    # one; independent label weights and singleton-event masses stay unchanged.
    z = np.linspace(-9, 9, 501)
    x, y = np.meshgrid(z, z)
    rho = 0.25
    density = np.exp(-(x * x - 2 * rho * x * y + y * y) / (2 * (1 - rho * rho))) / (
        2 * np.pi * np.sqrt(1 - rho * rho)
    )
    mass = np.trapezoid(np.trapezoid(density, z, axis=1), z)
    assert mass == pytest.approx(1, abs=2e-14)
    pi = np.array([0.1, 0.2, 0.7])
    assert np.outer(pi, pi).sum() == pytest.approx(1)


def test_winding_seams_and_omitted_image_bound():
    assert omitted_image_log_bound(SCORE, 0.25) < -300000
    for ri, rj in [(ALIAS_HZ / 2 - 1, 0), (ALIAS_HZ / 2, -ALIAS_HZ / 2), (100, -200)]:
        x = np.array([ri, rj])
        result = paired_likelihood(x, np.zeros((2, 3)), np.ones((2, 3), bool), SCORE, [(0, 1)])
        residual = result.residual_hz[:, 0]
        wrapped = 0.0
        for wi in (-1, 0, 1):
            for wj in (-1, 0, 1):
                a, b = residual + ALIAS_HZ * np.array([wi, wj])
                wrapped += np.exp(-(a * a - 0.5 * a * b + b * b) / (2 * 125**2 * (1 - 0.25**2))) / (
                    2 * np.pi * 125**2 * np.sqrt(1 - 0.25**2)
                )
        nearest = np.exp(
            -(residual[0] ** 2 - 0.5 * np.prod(residual) + residual[1] ** 2)
            / (2 * 125**2 * (1 - 0.25**2))
        ) / (2 * np.pi * 125**2 * np.sqrt(1 - 0.25**2))
        assert nearest == wrapped
        assert np.isfinite(result.nll)


def test_cancellation_extremes_and_seam():
    np.testing.assert_array_equal(exclusive(np.array([1.0, 1e-30, 1e-30])), [2e-30, 1.0, 1.0])
    for center in (0.0, ALIAS_HZ / 2, 1e8):
        y = np.array([center, center])
        p = np.zeros((2, 3))
        result = paired_likelihood(
            y, p, np.ones_like(p, bool), replace(SCORE, clutter_rate=1e-200), [(0, 1)]
        )
        assert np.isfinite(result.nll)
        assert np.isfinite(result.prediction_gradient).all()
        np.testing.assert_allclose(
            result.responsibilities.sum(axis=1) + result.clutter_probability, 1, atol=1e-15
        )


@pytest.mark.parametrize(
    "mask",
    [
        np.zeros((2, 3), bool),
        np.array([[True, False, False], [False, False, False]]),
        np.array([[False, True, False], [True, False, False]]),
    ],
)
def test_tiny_clutter_invisible_zero_residual(mask):
    score = replace(SCORE, clutter_rate=1e-200)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        result = paired_likelihood(np.zeros(2), np.zeros((2, 3)), mask, score, [(0, 1)])
    assert np.isfinite(result.nll)
    assert np.isfinite(result.prediction_gradient).all()
    np.testing.assert_allclose(result.responsibilities.sum(axis=1) + result.clutter_probability, 1)


@pytest.mark.parametrize("pairs", [[(0, 0)], [(0, 1), (1, 2)], [(0, 3)], [(0.0, 1.0)]])
def test_pair_validation(pairs):
    y, p, v = example()
    with pytest.raises(ValueError):
        paired_likelihood(y, p, v, SCORE, pairs)
