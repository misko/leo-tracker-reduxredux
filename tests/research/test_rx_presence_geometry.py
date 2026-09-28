import copy

import numpy as np
import pytest
from scipy.special import logsumexp

from tools import rx_presence_geometry as presence
from tools.rx_geometry_fit import raw_features, signal_arrays


def _source(split="calibration"):
    components = [
        {"kind": "track_candidate", "log_prior": np.log(0.12)},
        {"kind": "track_candidate", "log_prior": np.log(0.48)},
        {"kind": "other", "log_prior": np.log(0.4)},
    ]

    def window(role, time_ns, observed):
        return {
            "role": role,
            "prediction_utc_ns": time_ns,
            "sample_rate_hz": 5_000_000,
            "source_window_id": f"{role}-{time_ns}",
            "observed": {
                "rx0": [{"canonical_rx0_hz": value} for value in observed],
                "rx1": [],
            },
            "predictions": [
                {
                    "los_enu_unit": {"east": east, "north": 0.2, "up": 0.95},
                    "mu_canonical_rx0_hz": 100.0 + index,
                    "visible": True,
                }
                for index, east in enumerate((-0.1, 0.1))
            ],
        }

    return {
        "recording_split": split,
        "lane": {"session_id": f"{split}-session"},
        "alias_period_hz": 227_000.0,
        "components": components,
        "windows": [
            window("reception", 1_000_000_000, [100.0]),
            window("held_frequency", 2_000_000_000, [200.0]),
        ],
    }


def _selection_lane(split, reception_emission, held_emission):
    return {
        "source": {"recording_split": split},
        "roles": np.array(["reception", "held_frequency"]),
        "times": np.array([0.0, 1.0]),
        "prior": np.log([0.25, 0.75]),
        "test_emission": np.asarray([reception_emission, held_emission], dtype=float),
    }


def test_pi_zero_grid_score_is_exact_absent_reference(monkeypatch) -> None:
    lane = _selection_lane(
        "calibration",
        np.log([0.7, 0.01, 0.99]),
        np.log([0.3, 0.8, 0.2]),
    )
    monkeypatch.setattr(
        presence,
        "emission",
        lambda item, beta, lambdas, center, scale: item["test_emission"],
    )
    selection = presence.select_state(
        [lane], np.zeros(3), np.ones(2), np.zeros(8), np.ones(8)
    )
    absent = next(row for row in selection["grid"] if row["occupancy"] == 0.0)
    assert absent["tau_s"] == 1.0
    assert absent["calibration_log_score"] == pytest.approx(np.log(0.7))


def test_pi_zero_real_evaluation_is_exact_absent_model() -> None:
    source = _source("evaluation")
    dataset = {"schema": "rx-geometry-dataset/v1", "lanes": [source]}
    center, scale = np.zeros(8), np.ones(8)
    lanes = presence.prepare_lanes(dataset, center, scale)
    signal_arrays(lanes, 500.0)
    lambdas = np.array([1.3, 0.7])
    result = presence.evaluate(
        lanes,
        np.zeros(3),
        lambdas,
        center,
        scale,
        {"occupancy": 0.0, "tau_s": 1.0},
    )
    lane = lanes[0]
    held = lane["roles"] == "held_frequency"
    expected = presence.absent_loglik(lane, lambdas)[held]
    exported = result["lanes"][0]
    np.testing.assert_array_equal(exported["window_presence"], [0.0, 0.0])
    np.testing.assert_allclose(exported["held_log_scores"], expected)
    record = result["records"]["evaluation-session"]
    assert record["log_score"] == pytest.approx(float(expected.sum()))
    assert record["versus_absent_per_window"] == pytest.approx(0.0)


def test_state_selection_ignores_evaluation_and_calibration_held_outcomes(monkeypatch) -> None:
    calibration = _selection_lane(
        "calibration",
        np.log([0.6, 0.3, 0.1]),
        np.log([0.2, 0.1, 0.9]),
    )
    evaluation = _selection_lane(
        "evaluation",
        np.log([0.1, 0.8, 0.1]),
        np.log([0.1, 0.1, 0.8]),
    )
    monkeypatch.setattr(
        presence,
        "emission",
        lambda item, beta, lambdas, center, scale: item["test_emission"],
    )
    first = presence.select_state(
        [calibration, evaluation], np.zeros(3), np.ones(2), np.zeros(8), np.ones(8)
    )
    changed_calibration = copy.deepcopy(calibration)
    changed_evaluation = copy.deepcopy(evaluation)
    changed_calibration["test_emission"][1] = [-1000.0, 1000.0, 1000.0]
    changed_evaluation["test_emission"][:] = [[1000.0, -1000.0, 500.0], [700.0, 800.0, -900.0]]
    second = presence.select_state(
        [changed_calibration, changed_evaluation],
        np.zeros(3),
        np.ones(2),
        np.zeros(8),
        np.ones(8),
    )
    assert second == first


def test_real_selection_ignores_source_evaluation_and_calibration_held_outcomes() -> None:
    calibration = _source("calibration")
    evaluation = _source("evaluation")
    document = {"schema": "rx-geometry-dataset/v1", "lanes": [calibration, evaluation]}
    center, scale = np.zeros(8), np.ones(8)

    def selected(dataset):
        lanes = presence.prepare_lanes(dataset, center, scale)
        signal_arrays(lanes, 500.0, calibration_only=True)
        return presence.select_state(lanes, np.zeros(3), np.array([1.1, 0.9]), center, scale)

    first = selected(document)
    changed = copy.deepcopy(document)
    changed["lanes"][0]["windows"][1]["observed"]["rx0"] = [
        {"canonical_rx0_hz": -90_000.0},
        {"canonical_rx0_hz": 70_000.0},
    ]
    for window in changed["lanes"][1]["windows"]:
        window["observed"]["rx0"] = [{"canonical_rx0_hz": 80_000.0}]
        window["observed"]["rx1"] = [{"canonical_rx0_hz": -80_000.0}]
    assert selected(changed) == first


def test_candidate_permutation_preserves_real_hmm_selection() -> None:
    source = _source("calibration")
    document = {"schema": "rx-geometry-dataset/v1", "lanes": [source]}
    center, scale = np.zeros(8), np.ones(8)

    def selected(dataset):
        lanes = presence.prepare_lanes(dataset, center, scale)
        signal_arrays(lanes, 500.0, calibration_only=True)
        return presence.select_state(lanes, np.zeros(3), np.array([1.1, 0.9]), center, scale)

    expected = selected(document)
    permuted = copy.deepcopy(document)
    components = permuted["lanes"][0]["components"]
    components[0], components[1] = components[1], components[0]
    for window in permuted["lanes"][0]["windows"]:
        predictions = window["predictions"]
        predictions[0], predictions[1] = predictions[1], predictions[0]
    actual = selected(permuted)
    assert actual["selected"]["occupancy"] == expected["selected"]["occupancy"]
    assert actual["selected"]["tau_s"] == expected["selected"]["tau_s"]
    np.testing.assert_allclose(
        [row["calibration_log_score"] for row in actual["grid"]],
        [row["calibration_log_score"] for row in expected["grid"]],
        atol=1e-14,
    )


def test_prepare_uses_saved_scaler_and_normalizes_retained_prior() -> None:
    source = _source()
    dataset = {"schema": "rx-geometry-dataset/v1", "lanes": [source]}
    center = np.arange(8, dtype=float) / 10
    scale = np.arange(1, 9, dtype=float)
    lane = presence.prepare_lanes(dataset, center, scale)[0]
    raw = raw_features(source)[0]
    np.testing.assert_allclose(lane["x"], (raw - center) / scale)
    assert logsumexp(lane["prior"]) == pytest.approx(0.0)
    np.testing.assert_allclose(np.exp(lane["prior"]), [0.2, 0.8])
    assert lane["prior"].shape == (2,)


def test_conditional_nomination_posterior_is_distinct_from_joint_state_mass() -> None:
    summary = presence.posterior_summary(np.log([0.5, 0.4, 0.1]))
    assert summary["presence_probability"] == pytest.approx(0.5)
    np.testing.assert_allclose(np.exp(summary["state_log_weights"]), [0.5, 0.4, 0.1])
    np.testing.assert_allclose(
        np.exp(summary["nomination_log_weights_given_presence"]), [0.8, 0.2]
    )
