import copy
import math

import numpy as np
import pytest

from tools.rx_empirical_background import fit, log_density
from tools.rx_geometry_likelihood import periodic_signal_ratio
from tools.rx_joint_geometry import attach_reference, evaluate
from tools.rx_presence_geometry import prepare_lanes


def source(split="calibration"):
    def window(role, time_ns, left, right):
        return {
            "role": role,
            "prediction_utc_ns": time_ns,
            "sample_rate_hz": 5_000_000,
            "source_window_id": f"{split}-{role}",
            "observed": {
                "rx0": [{"canonical_rx0_hz": value} for value in left],
                "rx1": [{"canonical_rx0_hz": value} for value in right],
            },
            "predictions": [
                {
                    "los_enu_unit": {"east": 0.1, "north": 0.2, "up": 0.97},
                    "mu_canonical_rx0_hz": 100.0,
                    "visible": True,
                }
            ],
        }

    return {
        "recording_split": split,
        "lane": {"session_id": f"{split}-session"},
        "alias_period_hz": 1_000.0,
        "components": [
            {"kind": "track_candidate", "log_prior": 0.0},
            {"kind": "other", "log_prior": None},
        ],
        "windows": [
            window("reception", 1_000_000_000, [90.0, 110.0], []),
            window("held_frequency", 2_000_000_000, [250.0], [300.0]),
        ],
    }


def background():
    rows = [
        {"counts": [2, 0], "frequencies": [[0.1, 0.2], []], "rate_hz": 5_000_000},
        {"counts": [1, 1], "frequencies": [[0.3], [0.4]], "rate_hz": 5_000_000},
        {"counts": [0, 0], "frequencies": [[], []], "rate_hz": 5_000_000},
    ]
    return fit(rows, "joint")


def prepared(split="calibration"):
    dataset = {"schema": "rx-geometry-dataset/v1", "lanes": [source(split)]}
    lanes = prepare_lanes(dataset, np.zeros(8), np.ones(8))
    return attach_reference(lanes, background(), 20.0)


def test_adapter_matches_uniform_signal_ratio_and_shifted_count_probabilities():
    lane = prepared()[0]
    observed = [90.0, 110.0]
    expected = periodic_signal_ratio(observed, np.array([100.0]), 1_000.0, 20.0)
    np.testing.assert_allclose(lane["signal"][0, :, 0], expected)

    model = background()
    shifted = {"counts": [1, 0], "frequencies": [[0.0], []], "rate_hz": 5_000_000}
    expected_count = log_density(model, shifted) - math.lgamma(2) - math.lgamma(1)
    assert lane["log_count_probabilities"][0, 1, 0] == pytest.approx(expected_count)
    assert lane["log_count_probabilities"][0, 0, 1] == -np.inf


def test_all_absent_evaluation_equals_reference_and_full_is_additive():
    lane = prepared("evaluation")
    result = evaluate(lane, {"beta": [0.0, 0.0, 0.0], "occupancy": 0.0, "tau_s": 1.0})
    record = result["records"]["evaluation-session"]
    assert record["relative_log_score"] == pytest.approx(0.0)
    assert record["versus_reference_per_window"] == pytest.approx(0.0)
    assert record["full_log_score"] == pytest.approx(record["reference_log_score"])
    assert record["full_log_score"] == pytest.approx(
        record["reference_log_score"] + record["relative_log_score"]
    )


def test_calibration_reference_extraction_ignores_held_and_evaluation_mutations():
    calibration = source("calibration")
    evaluation = source("evaluation")
    original = {"schema": "rx-geometry-dataset/v1", "lanes": [calibration, evaluation]}
    changed = copy.deepcopy(original)
    changed["lanes"][0]["windows"][1]["observed"]["rx0"] = []
    for window in changed["lanes"][1]["windows"]:
        window["observed"]["rx0"] = [{"canonical_rx0_hz": 999.0}]
        window["observed"]["rx1"] = [{"canonical_rx0_hz": -999.0}]

    def extract(document):
        lanes = prepare_lanes(document, np.zeros(8), np.ones(8))
        return attach_reference(lanes, background(), 20.0, calibration_only=True)

    first, second = extract(original), extract(changed)
    assert len(first) == len(second) == 1
    assert first[0]["indices"] == second[0]["indices"] == [0]
    np.testing.assert_array_equal(first[0]["counts"], second[0]["counts"])
    np.testing.assert_array_equal(first[0]["reference"], second[0]["reference"])
    np.testing.assert_array_equal(first[0]["signal"], second[0]["signal"])
