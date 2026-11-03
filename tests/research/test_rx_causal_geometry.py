import copy

import numpy as np
import pytest

from tools.rx_causal_geometry import attach_causal_frequency
from tools.rx_empirical_background import fit
from tools.rx_geometry_likelihood import periodic_signal_ratio
from tools.rx_joint_geometry import attach_reference
from tools.rx_presence_geometry import prepare_lanes


def _source():
    def window(window_id, role, time_ns, rx0, rx1):
        return {
            "source_window_id": window_id,
            "role": role,
            "prediction_utc_ns": time_ns,
            "sample_rate_hz": 5_000_000,
            "observed": {
                "rx0": [{"canonical_rx0_hz": value} for value in rx0],
                "rx1": [{"canonical_rx0_hz": value} for value in rx1],
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
        "recording_split": "calibration",
        "lane": {"session_id": "record", "channel": 1, "edge": "lower"},
        "alias_period_hz": 1_000.0,
        "components": [
            {"kind": "track_candidate", "log_prior": 0.0},
            {"kind": "other", "log_prior": None},
        ],
        "windows": [
            window("r0", "reception", 1_000_000_000, [90.0, 110.0], []),
            window("r1", "reception", 2_000_000_000, [120.0], [300.0]),
            window("h0", "held_frequency", 3_000_000_000, [140.0], [320.0]),
        ],
    }


def _prepared():
    rows = [
        {"counts": [2, 0], "frequencies": [[0.1, 0.2], []], "rate_hz": 5_000_000},
        {"counts": [1, 1], "frequencies": [[0.3], [0.4]], "rate_hz": 5_000_000},
    ]
    document = {"schema": "rx-geometry-dataset/v1", "lanes": [_source()]}
    lanes = prepare_lanes(document, np.zeros(8), np.ones(8))
    return attach_reference(lanes, fit(rows, "joint"), 20.0)


def test_initial_uniform_density_recovers_uniform_reference_and_signal_ratio():
    original = _prepared()
    causal, diagnostics = attach_causal_frequency(copy.deepcopy(original), sigma_hz=20.0)
    first = diagnostics[0]["receivers"][0]["windows"][0]
    assert first["predictor"]["mode"] == "uniform"
    np.testing.assert_allclose(first["phase_density"], [1.0, 1.0])
    assert causal[0]["reference"][0] == pytest.approx(original[0]["reference"][0])
    expected = periodic_signal_ratio([90.0, 110.0], np.array([100.0]), 1_000.0, 20.0)
    np.testing.assert_allclose(causal[0]["signal"][0, :, 0], expected)


def test_causal_phase_change_preserves_count_terms_and_scores_before_update():
    original = _prepared()
    causal, diagnostics = attach_causal_frequency(copy.deepcopy(original), sigma_hz=20.0)
    np.testing.assert_array_equal(
        causal[0]["log_count_probabilities"], original[0]["log_count_probabilities"]
    )
    rx0 = diagnostics[0]["receivers"][0]["windows"]
    assert rx0[1]["predictor"]["mode"] == "one_history"
    assert rx0[1]["predictor"]["history_candidate_counts"] == [2]
    assert rx0[2]["predictor"]["mode"] == "two_history"
    assert rx0[2]["predictor"]["history_candidate_counts"] == [2, 1]
    assert causal[0]["reference"][1] - original[0]["reference"][1] == pytest.approx(
        np.log(rx0[1]["phase_density"]).sum()
        + np.log(diagnostics[0]["receivers"][1]["windows"][1]["phase_density"]).sum()
    )


def test_empty_receiver_advances_history_without_creating_candidates():
    causal, diagnostics = attach_causal_frequency(_prepared(), sigma_hz=20.0)
    rx1 = diagnostics[0]["receivers"][1]["windows"]
    assert rx1[0]["candidate_count"] == 0
    assert rx1[0]["phase_density"] == []
    assert rx1[1]["predictor"]["mode"] == "uniform"
    assert causal[0]["signal"][0, 0, 1] == 0.0
