from __future__ import annotations

import numpy as np
import pytest
from finite_set_likelihood import prepare_finite_set_likelihood
from soft_likelihood import SoftLikelihood, confident_matches


def test_soft_likelihood_matches_grouped_oracle_with_gradient():
    prepared = prepare_finite_set_likelihood([0., 120., 600., 10.], [0, 0, 0, 1])
    predicted = np.tile([20., 540.], (4, 1))
    visible = np.ones_like(predicted, dtype=bool)
    adapter = SoftLikelihood(prepared, 0.4)
    actual = adapter.evaluate(predicted, visible, sigma_hz=200.,
                              return_gradient=True, return_precision=True)
    expected = prepared.evaluate(predicted, visible, sigma_hz=200.,
                                 detection_probability=0.4, clutter_rate=2.,
                                 return_gradient=True, return_precision=True)
    for key in ("total_log_likelihood", "row_association_probability",
                "prediction_gradient", "prediction_precision"):
        np.testing.assert_allclose(actual[key], expected[key], atol=1e-12)
    assert adapter.last_result is actual


def test_no_support_discontinuity_at_old_reporting_cutoff():
    prepared = prepare_finite_set_likelihood([600.], [0])
    adapter = SoftLikelihood(prepared, 0.8)
    results = [adapter.evaluate(np.array([[shift]]), np.ones((1, 1), dtype=bool),
                                sigma_hz=200., return_gradient=True)
               for shift in (-1e-3, 0., 1e-3)]
    assert all(result["row_association_probability"][0, 0] > 0 for result in results)
    difference = (results[2]["total_log_likelihood"]
                  - results[0]["total_log_likelihood"]) / 2e-3
    assert difference == pytest.approx(results[1]["prediction_gradient"][0, 0], rel=1e-6)


def test_reporting_uses_probability_and_wrapped_residual_without_mutation():
    predicted = np.array([[0., 100.], [0., 100.], [0., 100.]])
    posterior = np.array([[0.9, 0.0], [0.7, 0.2], [0.9, 0.0]])
    original = posterior.copy()
    actual = confident_matches([1000., 0., 301.], predicted, posterior, 1000., 300.)
    assert actual["confident_rows"] == 1
    np.testing.assert_array_equal(actual["confident_rows_per_satellite"], [1, 0])
    np.testing.assert_array_equal(posterior, original)
    assert actual["median_absolute_residual_hz"] == 0


def test_empty_confident_report_is_explicit():
    actual = confident_matches([0.], [[0.]], [[0.1]], 1000., 300.)
    assert actual["confident_rows"] == 0
    assert actual["median_absolute_residual_hz"] is None
