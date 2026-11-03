"""Exact low-dimensional integrals and the established Gaussian-prior oracle."""

import importlib
import sys
from functools import lru_cache
from math import gamma, lgamma
from pathlib import Path

import numpy as np
import pytest


def student_pdf(x, degrees, scale):
    return (
        gamma((degrees + 1) / 2)
        / gamma(degrees / 2)
        / (np.sqrt(degrees * np.pi) * scale)
        * (1 + (np.asarray(x) / scale) ** 2 / degrees) ** (-(degrees + 1) / 2)
    )


@lru_cache
def real_quadrature(size):
    nodes, weights = np.polynomial.legendre.leggauss(size)
    a = np.tan(np.pi * nodes / 2)
    return a, weights * np.pi / 2 * (1 + a**2)


@pytest.fixture
def tool():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    try:
        yield importlib.import_module("dsx01_hierarchical_bound")
    finally:
        sys.path.pop(0)


def test_gaussian_prior_reduces_to_the_existing_bound_with_full_normalization(tool):
    rng = np.random.default_rng(140)
    y, u = rng.normal(0, 100, 30), rng.normal(0, 50, (30, 8))
    groups, sigma = np.repeat([0, 1, 2], 10), np.linspace(40, 180, 30)
    oracle = importlib.import_module("dsx01_grouped_student").student_joint_bound
    expected = oracle(y, u, sigma, groups, iterations=256)
    actual = tool.hierarchical_bound(y, u, sigma, groups)
    np.testing.assert_allclose(actual["residual"], expected["residual"], atol=1e-10)
    constant = np.sum(np.log(2 * np.pi) + 2 * np.log(sigma))
    constant += 3 * (2 * lgamma(2) - 2 * lgamma(7) + 10 * np.log(2))
    np.testing.assert_allclose(actual["normalization_constant"], constant)


@pytest.mark.parametrize("y", [0.0, 1.0, 4.0])
@pytest.mark.parametrize("degrees", [4.0, 8.0])
def test_normalized_bound_is_above_exact_student_noise_and_prior_integral(tool, y, degrees):
    sigma, coefficient = 0.7, 1.2
    integrals = []
    for size in (384, 768):
        a, weights = real_quadrature(size)
        integrals.append(
            float(
                weights
                @ (
                    student_pdf(y - coefficient * a, 4, sigma)
                    * student_pdf(a, degrees, np.sqrt((degrees - 2) / degrees))
                )
            )
        )
    np.testing.assert_allclose(*integrals, rtol=1e-10, atol=1e-12)
    exact = integrals[-1]
    result = tool.hierarchical_bound(
        [y],
        [[coefficient]],
        sigma,
        np.array([0]),
        prior_groups=np.array([0]),
        prior_nu=degrees,
    )
    assert result["negative_twice_elbo"] >= -2 * np.log(exact) - 1e-9
    assert result["negative_twice_elbo"] < -2 * np.log(exact) + 2


@pytest.mark.parametrize("degrees", [4.0, 8.0])
def test_declared_student_prior_has_unit_marginal_variance(degrees):
    a, weights = real_quadrature(768)
    density = student_pdf(a, degrees, np.sqrt((degrees - 2) / degrees))
    np.testing.assert_allclose(weights @ density, 1, atol=1e-10)
    np.testing.assert_allclose(weights @ (density * a**2), 1, atol=1e-10)


def test_shared_three_dimensional_prior_bound_exceeds_its_exact_projected_integral(tool):
    u, sigma, y = np.array([1.2, 0.5, -0.2]), 0.7, 2.0
    a, weights = real_quadrature(768)
    exact = weights @ (
        student_pdf(y - np.linalg.norm(u) * a, 4, sigma) * student_pdf(a, 4, np.sqrt(0.5))
    )
    result = tool.hierarchical_bound(
        [y],
        u[None, :],
        sigma,
        np.array([0]),
        prior_groups=np.zeros(3, dtype=int),
    )
    assert result["negative_twice_elbo"] >= -2 * np.log(exact) - 1e-9
    assert result["negative_twice_elbo"] < -2 * np.log(exact) + 2


def test_fractional_likelihood_matches_an_exact_no_nuisance_gamma_integral(tool):
    y, sigma, power = np.array([100.0, -50.0, 70.0]), 80.0, 0.3
    n = len(y) * power
    alpha, beta = (4 + n) / 2, (4 + power * np.sum((y / sigma) ** 2)) / 2
    expected = (
        n * np.log(2 * np.pi * sigma**2)
        + 2 * lgamma(2)
        - 4 * np.log(2)
        - 2 * lgamma(alpha)
        + 2 * alpha * np.log(beta)
    )
    result = tool.hierarchical_bound(
        y, np.empty((3, 0)), sigma, np.zeros(3, dtype=int), powers=power
    )
    np.testing.assert_allclose(result["negative_twice_elbo"], expected, atol=1e-10)


def test_heavy_prior_coordinate_updates_monotonically_improve_the_bound(tool):
    rng = np.random.default_rng(141)
    y, u = rng.normal(0, 100, 70), rng.normal(0, 60, (70, 9))
    groups, prior = np.repeat(np.arange(7), 10), np.array([-1, 0, 0, 0, 1, 1, 1, -1, -1])
    scores = [
        tool.hierarchical_bound(y, u, 100, groups, prior_groups=prior, iterations=k)[
            "negative_twice_elbo"
        ]
        for k in (1, 2, 8, 128)
    ]
    assert np.all(np.diff(scores) <= 1e-9)
