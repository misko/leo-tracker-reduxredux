import json
from types import SimpleNamespace

import finite_set_rf_score as score
import numpy as np
from finite_set_likelihood import prepare_finite_set_likelihood


def _data():
    return SimpleNamespace(
        times=np.array([0.0, 1.0, 2.0, 3.0]),
        measured=np.array([15.0, -25.0, 35.0, -45.0]),
        rf=np.array([11.1e9, 11.4e9, 11.1e9, 11.4e9]),
        receiver=np.array([0, 0, 1, 1]),
        channel=np.array([1, 2, 1, 2]),
        group=np.arange(4),
        reference_time_s=1.5,
    )


def test_exact_rf_coefficient_score_matches_centered_finite_difference():
    data = _data()
    prepared = prepare_finite_set_likelihood(data.measured, data.group)
    predicted = np.array([[5.0], [-10.0], [20.0], [-20.0]])
    visible = np.ones_like(predicted, dtype=bool)
    design, _, _ = score.receiver_rf_design(data)
    kwargs = {
        "sigma_hz": 200.0,
        "detection_probability": 0.2,
        "clutter_rate": 2.0,
        "implementation": "batched",
    }

    result = score.coefficient_score(
        prepared, predicted, visible, design, kwargs
    )
    step = 1e-3
    finite = []
    for index in range(2):
        coefficients = np.zeros(2)
        coefficients[index] = step
        plus = prepared.evaluate(
            predicted + (design @ coefficients)[:, None], visible, **kwargs
        )["total_log_likelihood"]
        coefficients[index] = -step
        minus = prepared.evaluate(
            predicted + (design @ coefficients)[:, None], visible, **kwargs
        )["total_log_likelihood"]
        finite.append((plus - minus) / (2 * step))

    np.testing.assert_allclose(
        result["log_likelihood_score_at_zero"], finite, rtol=2e-6, atol=2e-8
    )
    np.testing.assert_allclose(
        result["negative_log_likelihood_gradient_at_zero"], -np.asarray(finite)
    )


def test_weighted_rf_summary_reports_receiver_and_channel_means():
    data = _data()
    predicted = np.zeros((4, 1))
    association = np.array([[1.0], [0.5], [0.25], [0.75]])
    design, _, _ = score.receiver_rf_design(data)
    result = {
        "row_association_probability": association,
        "alias_hz": 227272.72727272726,
    }

    summaries = score.posterior_residual_summaries(
        data, predicted, result, design
    )

    assert [row["receiver"] for row in summaries] == [0, 1]
    assert summaries[0]["signal_weight"] == 1.5
    assert np.isclose(summaries[0]["weighted_residual_mean_hz"], 5.0 / 3.0)
    assert [row["channel"] for row in summaries[0]["channels"]] == [1, 2]
    assert summaries[1]["weighted_residual_rf_slope_hz_per_ghz"] < 0


def test_complete_data_projection_removes_exact_rf_time_degeneracy():
    receiver = np.repeat([0, 1], 6)
    times = np.tile(np.linspace(-2.0, 2.0, 6), 2)
    nuisance = np.zeros((12, 4))
    rf_design = np.zeros((12, 2))
    for rx in (0, 1):
        rows = receiver == rx
        nuisance[rows, 2 * rx] = 1.0
        nuisance[rows, 2 * rx + 1] = times[rows]
        rf_design[rows, rx] = times[rows]
    row_score = np.linspace(-1.0, 1.0, 12)
    precision = np.ones(12)

    result = score.project_complete_data_fisher(
        rf_design, nuisance, row_score, precision
    )

    np.testing.assert_allclose(
        result["projected_complete_data_information"], np.zeros((2, 2)), atol=1e-12
    )
    np.testing.assert_allclose(result["projected_log_likelihood_score"], 0.0, atol=1e-12)
    assert result["nuisance_rank"] == 4
    assert result["prior_score_at_zero"] == [0.0, 0.0]


def test_complete_data_projection_retains_non_time_rf_information():
    receiver = np.repeat([0, 1], 8)
    times = np.tile(np.linspace(-1.0, 1.0, 8), 2)
    nuisance = np.zeros((16, 4))
    rf_design = np.zeros((16, 2))
    pattern = np.array([-1.0, 1.0, -1.0, 1.0, 1.0, -1.0, 1.0, -1.0])
    for rx in (0, 1):
        rows = receiver == rx
        nuisance[rows, 2 * rx] = 1.0
        nuisance[rows, 2 * rx + 1] = times[rows]
        rf_design[rows, rx] = pattern
    result = score.project_complete_data_fisher(
        rf_design, nuisance, np.zeros(16), np.ones(16)
    )

    assert np.all(np.diag(result["projected_complete_data_information"]) > 0)
    assert np.all(np.isfinite(result["projected_information_plus_prior"]))


def test_run_streams_units_and_preserves_failures_without_fitting(tmp_path):
    units = ["DS10-S01", "DS10-S02", "DS11-S01"]
    active = 0
    maximum_active = 0

    def diagnostic(unit_id, **kwargs):
        nonlocal active, maximum_active
        del kwargs
        active += 1
        maximum_active = max(maximum_active, active)
        try:
            if unit_id == "DS10-S02":
                raise ValueError("sealed input mismatch")
            return {
                "unit_id": unit_id,
                "exact_score": {"log_likelihood_score_at_zero": [1.0, 2.0]},
                "complete_data_fisher_projection": {
                    "projected_log_likelihood_score": [0.5, 1.0],
                    "projected_complete_data_information": [[2.0, 0.0], [0.0, 3.0]],
                },
            }
        finally:
            active -= 1

    result = score.run(
        units,
        profile_root=tmp_path,
        grouped_root=tmp_path,
        exports=tmp_path,
        unit_diagnostic=diagnostic,
        budget_s=10.0,
    )

    assert maximum_active == 1
    assert result["requested_unit_count"] == 3
    assert result["complete_unit_count"] == 2
    assert result["failed_unit_count"] == 1
    assert result["failures"][0]["unit_id"] == "DS10-S02"
    np.testing.assert_allclose(
        result["aggregate"]["projected_log_likelihood_score_sum"], [1.0, 2.0]
    )
    assert result["provenance"]["fit_performed"] is False
    json.dumps(score.jsonable(result), allow_nan=False)


def test_authoritative_bindings_require_every_loader_input_and_full_geometry(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.npz"
    first.write_text("first")
    second.write_bytes(b"second")
    authoritative = {
        str(first.resolve()): score.digest(first),
        str(second.resolve()): score.digest(second),
    }
    geometry = {
        "fitted_array_sha256": {"times": "same"},
        "children": [{"session_id": "capture", "raw_row_count": 4}],
        "representative_original_rows": np.array([1, 3]),
    }
    expected_geometry = score.jsonable(geometry)

    observed = score.validate_authoritative_bindings(
        authoritative, [first, second], geometry, expected_geometry
    )

    assert observed == authoritative
    with np.testing.assert_raises_regex(ValueError, "absent"):
        score.validate_authoritative_bindings(
            authoritative, [first, tmp_path / "missing"], geometry, expected_geometry
        )
    with np.testing.assert_raises_regex(ValueError, "complete loaded geometry"):
        score.validate_authoritative_bindings(
            authoritative,
            [first, second],
            geometry,
            {**expected_geometry, "children": []},
        )


def test_authoritative_snapshot_mutation_is_rejected(tmp_path):
    path = tmp_path / "input.json"
    path.write_text("sealed")
    authoritative = {str(path.resolve()): score.digest(path)}
    path.write_text("changed")

    with np.testing.assert_raises_regex(RuntimeError, "provenance changed"):
        score.validate_authoritative_bindings(
            authoritative, [path], {"geometry": 1}, {"geometry": 1}
        )
