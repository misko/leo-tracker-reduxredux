from __future__ import annotations

import math

import numpy as np
import pytest

from leo.analysis.gaussian_sum_location import gaussian_logpdf
from leo.analysis.robust_likelihood import student_t_logpdf, student_t_weight


def test_student_t_matches_known_standard_cauchy_density() -> None:
    for value in (-2.0, 0.0, 3.5):
        actual = student_t_logpdf(np.array([value]), np.eye(1), 1.0)
        assert actual == pytest.approx(-math.log(math.pi) - math.log1p(value**2))


def test_large_degrees_of_freedom_approaches_gaussian() -> None:
    residual = np.array([0.3, -1.2])
    covariance = np.array([[2.0, 0.4], [0.4, 0.7]])
    assert student_t_logpdf(residual, covariance, 1e7) == pytest.approx(
        gaussian_logpdf(residual, covariance), abs=2e-7
    )
    distance = residual @ np.linalg.solve(covariance, residual)
    assert student_t_weight(distance, 2, 1e7) == pytest.approx(1.0, abs=2e-7)


@pytest.mark.parametrize("nu", [0.0, -1.0, np.inf])
def test_degrees_of_freedom_must_be_finite_and_positive(nu: float) -> None:
    with pytest.raises(ValueError, match="nu"):
        student_t_logpdf(np.zeros(1), np.eye(1), nu)
