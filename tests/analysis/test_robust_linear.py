from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.robust_linear import fit_huber_linear_irls


def test_huber_linear_irls_resists_a_large_frequency_outlier() -> None:
    time_s = np.arange(21, dtype=np.float64)
    frequency_hz = 125.0 * time_s + 12_000.0
    frequency_hz[10] += 100_000.0
    reference_time_s = 10.0
    relative_time = time_s - reference_time_s
    ordinary = np.polyfit(relative_time, frequency_hz, 1)

    robust = fit_huber_linear_irls(
        time_s,
        frequency_hz,
        initial_coefficients_hz=(float(ordinary[0]), float(ordinary[1])),
        reference_time_s=reference_time_s,
    )

    assert robust.converged
    assert abs(robust.slope_hz_per_s - 125.0) < 1e-9
    assert abs(robust.intercept_at_reference_hz - 13_250.0) < 1_000.0
    assert robust.median_absolute_residual_hz < 1_000.0
    assert robust.residual_max_hz > 90_000.0


def test_huber_linear_irls_is_permutation_invariant() -> None:
    time_s = np.arange(12, dtype=np.float64)
    frequency_hz = -42.5 * time_s + 8_000.0
    frequency_hz[[2, 9]] += (8_000.0, -6_000.0)
    permutation = np.asarray([8, 2, 11, 1, 6, 5, 0, 10, 3, 9, 7, 4])
    arguments = {
        "initial_coefficients_hz": (-40.0, 7_800.0),
        "reference_time_s": 0.0,
    }

    first = fit_huber_linear_irls(time_s, frequency_hz, **arguments)
    permuted = fit_huber_linear_irls(time_s[permutation], frequency_hz[permutation], **arguments)

    assert np.allclose(first.coefficients_hz, permuted.coefficients_hz, atol=1e-9, rtol=0.0)
    assert first.mad_scale_hz == permuted.mad_scale_hz
    assert first.huber_objective == pytest.approx(permuted.huber_objective, abs=1e-12)


def test_huber_linear_irls_recovers_an_exact_line() -> None:
    time_s = np.linspace(4.0, 18.0, 15)
    frequency_hz = 73.25 * (time_s - 11.0) - 2_500.0

    fitted = fit_huber_linear_irls(
        time_s,
        frequency_hz,
        initial_coefficients_hz=(70.0, -2_400.0),
        reference_time_s=11.0,
    )

    assert fitted.converged
    assert np.allclose(fitted.coefficients_hz, (73.25, -2_500.0), atol=1e-10, rtol=0.0)
    assert fitted.median_absolute_residual_hz < 1e-10
    assert fitted.mad_scale_hz == 100.0
