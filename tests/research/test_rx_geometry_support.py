import copy

import numpy as np
import pytest

from tools.rx_geometry_support import analyze


def _model():
    return {
        "schema": "rx-geometry-association-pilot/v1",
        "status": "complete",
        "sigma_hz": 500.0,
        "clutter_intensities": [1.0, 1.0],
        "feature_center": [0.0] * 8,
        "feature_scale": [1.0] * 8,
        "fits": {
            "D": {"success": True, "parameters": [0.0] * 3},
            "S": {"success": True, "parameters": [0.0] * 6},
            "T": {"success": True, "parameters": [0.0] * 8},
        },
    }


def _lane(session, split="calibration", moving=True, offset=0.0):
    windows = []
    for index in range(3):
        east = offset + (0.1 * index if moving else 0.0)
        north = 0.2 - (0.03 * index if moving else 0.0)
        up = np.sqrt(1.0 - east**2 - north**2)
        role = "held_frequency" if index == 2 else "reception"
        windows.append(
            {
                "role": role,
                "prediction_utc_ns": index * 1_000_000_000,
                "sample_rate_hz": 5_000_000,
                "observed": {"rx0": [], "rx1": []},
                "predictions": [
                    {
                        "los_enu_unit": {"east": east, "north": north, "up": up},
                        "mu_canonical_rx0_hz": 0.0,
                        "visible": True,
                    },
                    {
                        "los_enu_unit": {
                            "east": east / 2,
                            "north": north,
                            "up": np.sqrt(1 - (east / 2) ** 2 - north**2),
                        },
                        "mu_canonical_rx0_hz": 1.0,
                        "visible": True,
                    },
                ],
            }
        )
    return {
        "recording_split": split,
        "lane": {"session_id": session, "channel": 1},
        "components": [
            {"kind": "track_candidate", "log_prior": np.log(0.25)},
            {"kind": "track_candidate", "log_prior": np.log(0.75)},
            {"kind": "other", "log_prior": np.log(0.1)},
        ],
        "windows": windows,
    }


def _document(lanes):
    return {"schema": "rx-geometry-dataset/v1", "lanes": lanes}


def test_static_geometry_has_zero_within_temporal_variance() -> None:
    result = analyze(_document([_lane("a", moving=False)]), _model())
    np.testing.assert_allclose(result["variance_decomposition"]["within_temporal"], 0.0)
    assert all(
        value is None or value == pytest.approx(0.0)
        for value in result["variance_decomposition"]["within_fraction"]
    )


def test_changing_geometry_has_positive_within_support() -> None:
    result = analyze(_document([_lane("a", moving=True)]), _model())
    within = np.asarray(result["variance_decomposition"]["within_temporal"])
    assert np.any(within > 0)
    assert result["within_motion_design_eigenvalues"][0] > 0
    assert result["lanes"][0]["weighted_nominee_los_first_last_excursion_deg"] > 0


def test_variance_decomposition_is_exact() -> None:
    result = analyze(
        _document([_lane("a", moving=True), _lane("b", moving=True, offset=0.3)]), _model()
    )
    decomposition = result["variance_decomposition"]
    np.testing.assert_allclose(
        decomposition["total"],
        np.asarray(decomposition["within_temporal"])
        + np.asarray(decomposition["between_group_means"]),
        atol=2e-15,
    )


def test_held_and_evaluation_geometry_cannot_change_audit() -> None:
    calibration = _lane("a", moving=True)
    evaluation = _lane("e", split="evaluation", moving=True, offset=0.2)
    first = analyze(_document([calibration, evaluation]), _model())
    changed_calibration = copy.deepcopy(calibration)
    changed_evaluation = copy.deepcopy(evaluation)
    changed_calibration["windows"][2]["predictions"][0]["los_enu_unit"] = {
        "east": 0.9,
        "north": 0.0,
        "up": np.sqrt(0.19),
    }
    for window in changed_evaluation["windows"]:
        window["predictions"][0]["los_enu_unit"] = {"east": 0.0, "north": 0.0, "up": 1.0}
    second = analyze(_document([changed_calibration, changed_evaluation]), _model())
    assert second == first


def test_weights_normalize_and_records_receive_equal_mass() -> None:
    # Recording a has two lanes while b has one; global summaries still assign
    # each recording one half of total mass.
    result = analyze(
        _document(
            [
                _lane("a", moving=False, offset=0.0),
                _lane("a", moving=False, offset=0.0),
                _lane("b", moving=False, offset=0.4),
            ]
        ),
        _model(),
    )
    assert result["weight_sum"] == pytest.approx(1.0)
    # Recording b's nominee-weighted east is .25; equal recording weights give .125.
    assert result["weighted_mean"][2] == pytest.approx(0.125)


def test_nomination_concentration_and_endpoint_directions_are_exported() -> None:
    result = analyze(_document([_lane("a", moving=True)]), _model())
    lane = result["lanes"][0]
    summary = lane["nomination_prior_summary"]
    assert summary["maximum_weight"] == pytest.approx(0.75)
    assert summary["finite_log_prior_count"] == 2
    assert summary["weight_ge_1e_6_count"] == 2
    assert summary["effective_count"] == pytest.approx(np.exp(summary["entropy_nats"]))
    assert len(lane["nominee_forecast_directions"]) == 2
    for nominee in lane["nominee_forecast_directions"]:
        np.testing.assert_allclose(
            np.asarray(nominee["end_los_enu"]) - nominee["start_los_enu"],
            nominee["endpoint_delta_los_enu"],
        )


def test_underflowed_nominee_is_reported_but_does_not_create_nan_group() -> None:
    lane = _lane("a", moving=True)
    lane["components"][0]["log_prior"] = 0.0
    lane["components"][1]["log_prior"] = -2_000.0
    result = analyze(_document([lane]), _model())
    exported = result["lanes"][0]
    assert exported["nomination_prior_summary"]["finite_log_prior_count"] == 2
    assert exported["nomination_prior_summary"]["weight_ge_1e_6_count"] == 1
    assert exported["conditional_nominee_weights"] == [1.0, 0.0]
    assert np.all(np.isfinite(result["weighted_covariance"]))


def test_malformed_held_geometry_is_never_extracted() -> None:
    lane = _lane("a", moving=True)
    lane["windows"][2]["predictions"] = None
    result = analyze(_document([lane]), _model())
    assert result["lanes"][0]["reception_windows"] == 2
