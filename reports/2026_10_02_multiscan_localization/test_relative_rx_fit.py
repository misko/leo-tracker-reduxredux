import hashlib
import json
from types import SimpleNamespace

import numpy as np
import relative_rx_fit


def quadratic_calibration():
    return relative_rx_fit.RelativeCalibration(
        model="quadratic",
        parameters=np.array([10.0, -8.0, 14.0]),
        reference_time_s=None,
        start_time_s=0.0,
        end_time_s=10.0,
    )


def test_measurement_correction_has_opposite_half_delta_signs():
    source = SimpleNamespace(
        times=np.array([0.0, 0.0, 10.0, 10.0]),
        receiver=np.array([0, 1, 0, 1]),
        measured=np.array([100.0, 110.0, 200.0, 250.0]),
    )
    calibration = relative_rx_fit.RelativeCalibration(
        model="line",
        parameters=np.array([10.0, 2.0]),
        reference_time_s=0.0,
        start_time_s=0.0,
        end_time_s=10.0,
    )

    corrected = relative_rx_fit.CalibratedData(source, calibration)

    np.testing.assert_allclose(corrected.measured, [105.0, 105.0, 215.0, 235.0])
    np.testing.assert_array_equal(source.measured, [100.0, 110.0, 200.0, 250.0])


class DenseJacobian:
    def __init__(self, matrix):
        self.matrix = np.asarray(matrix)

    def transpose_multiply(self, weights):
        return self.matrix.T @ np.asarray(weights)

    def normal_matrix(self, weights):
        weights = np.asarray(weights)
        return self.matrix.T @ (weights[:, None] * self.matrix)


def test_tied_vjp_sums_receiver_columns_and_matches_finite_difference():
    rng = np.random.default_rng(9)
    candidate_count = 3
    full_jacobian = rng.normal(size=(11, 6 + candidate_count))
    reduced = rng.normal(size=4 + candidate_count)
    weights = rng.normal(size=11)
    tied = relative_rx_fit.TiedJacobian(DenseJacobian(full_jacobian), candidate_count)
    analytic = tied.transpose_multiply(weights)

    def scalar(parameters):
        full = relative_rx_fit.expand_tied_parameters(parameters)
        return float(weights @ (full_jacobian @ full))

    finite = np.empty_like(reduced)
    step = 1e-6
    for index in range(len(reduced)):
        delta = np.zeros_like(reduced)
        delta[index] = step
        finite[index] = (scalar(reduced + delta) - scalar(reduced - delta)) / (2 * step)

    np.testing.assert_allclose(analytic, finite, rtol=1e-8, atol=1e-8)
    full_gradient = full_jacobian.T @ weights
    assert analytic[2] == full_gradient[2] + full_gradient[4]
    assert analytic[3] == full_gradient[3] + full_gradient[5]


def test_common_slope_intersection_preserves_both_physical_rx_bounds():
    endpoint_slopes = np.array([-7.59, 13.90])
    lower, upper = relative_rx_fit.common_slope_bounds(endpoint_slopes)

    np.testing.assert_allclose([lower, upper], [-43.05, 43.05])
    for common in (lower, upper):
        for delta_slope in endpoint_slopes:
            assert -50 <= common - delta_slope / 2 <= 50
            assert -50 <= common + delta_slope / 2 <= 50


def test_differential_selection_uses_parameter_count_penalty():
    case = {
        "pairing": {"paired_group_count": 100},
        "fit": {
            "reference_time_s": 5.0,
            "minimum_objective_model": "quadratic",
            "line": {
                "objective": 100.0,
                "intercept_hz_at_reference": 10.0,
                "slope_hz_s": 1.0,
            },
            "quadratic": {
                "objective": 98.0,
                "intercept_hz_at_start": 5.0,
                "slope_start_hz_s": 0.0,
                "slope_end_hz_s": 2.0,
            },
        },
        "selected_model": "line",
    }
    pair_count = case["pairing"]["paired_group_count"]
    case["penalized_scores"] = {
        "line": 100.0 + np.log(pair_count),
        "quadratic": 98.0 + 1.5 * np.log(pair_count),
    }

    calibration, receipt = relative_rx_fit.select_differential_calibration(
        case, np.linspace(0, 10, 100)
    )

    assert calibration.model == "line"
    assert receipt["selected_by_penalized_score"] is True
    assert receipt["selection_source"].startswith("sealed cohort receipt")
    assert receipt["diagnostic_minimum_objective_field_ignored"] is True
    scores = {row["model"]: row["penalized_score"] for row in receipt["candidates"]}
    assert scores["line"] < scores["quadratic"]


def test_localization_score_counts_calibration_but_not_differential_likelihood():
    result = relative_rx_fit.localization_selection_score(
        objective=1000.0,
        satellite_count=8,
        group_count=200,
        calibration_model="quadratic",
    )

    expected = 1000.0 + 0.5 * 9 * np.log(200)
    assert np.isclose(result["selection_score"], expected)
    assert result["calibration_effective_parameter_delta_vs_rx4"] == 1
    assert result["differential_likelihood_added_to_localization_objective"] is False


def test_source_full_vector_roundtrip_retains_tau_and_ties_rx():
    full = np.array([1.0, 2.0, 100.0, 3.0, 140.0, 7.0, -1.0, 2.0])
    reduced = relative_rx_fit.reduce_tied_parameters(full)
    tied = relative_rx_fit.expand_tied_parameters(reduced)

    np.testing.assert_allclose(tied[:2], full[:2])
    np.testing.assert_allclose(tied[6:], full[6:])
    np.testing.assert_allclose(tied[2:6], [120.0, 5.0, 120.0, 5.0])


def test_cohort_receipt_is_bound_through_summary(tmp_path):
    unit_id = "DS10-S01"
    fit_path = tmp_path / unit_id / "fit.json"
    fit_path.parent.mkdir()
    receipt = {
        "schema": "rx-difference-cohort/v1",
        "unit": {"unit_id": unit_id, "session_ids": ["scan-one"]},
        "dataset": "DS10",
        "selection_sha256": "selection",
        "source_sha256": "source",
        "reference_read": False,
        "ephemeris_read": False,
        "selected_model": "line",
        "pairing": {"paired_group_count": 10},
        "penalized_scores": {"line": 1.0, "quadratic": 2.0},
        "fit": {},
    }
    fit_path.write_text(json.dumps(receipt))
    fit_sha256 = hashlib.sha256(fit_path.read_bytes()).hexdigest()
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "units": [
                    {
                        "unit_id": unit_id,
                        "fit_sha256": fit_sha256,
                        "selected_model": "line",
                    }
                ],
                "selection_sha256": "selection",
                "source_sha256": "source",
                "reference_read": False,
            }
        )
    )

    case, provenance = relative_rx_fit._load_differential_case(unit_id, tmp_path)

    assert case["session_id"] == "scan-one"
    assert provenance["kind"] == "cohort_unit_receipt"
    assert provenance["source_sha256"] == fit_sha256
    assert provenance["summary_sha256"] == hashlib.sha256(summary_path.read_bytes()).hexdigest()
