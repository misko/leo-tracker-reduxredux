import pytest

from tools.rx_background_audit import build_audit


def window(identifier, visible, rx0, rx1, *, role="reception"):
    return {
        "source_window_id": identifier,
        "role": role,
        "predictions": [{"visible": visible}],
        "observed": {
            "rx0": [{"canonical_rx0_hz": value, "candidate_id": f"a-{value}"} for value in rx0],
            "rx1": [{"canonical_rx0_hz": value, "candidate_id": f"b-{value}"} for value in rx1],
        },
    }


def dataset():
    return {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [
            {
                "recording_split": "calibration",
                "alias_period_hz": 16.0,
                "lane": {"session_id": "s", "channel": 1},
                "windows": [
                    window("negative", False, [], [1.0, 15.5]),
                    window("visible", True, [2.0], []),
                    window("held", False, [3.0], [], role="held_frequency"),
                ],
            },
            {
                "recording_split": "evaluation",
                "alias_period_hz": 16.0,
                "lane": {"session_id": "e", "channel": 1},
                "windows": [window("evaluation", False, [4.0], [])],
            },
        ],
    }


def test_audit_uses_only_calibration_reception_all_invisible_windows():
    result = build_audit(
        [("pilot", dataset()), ("confirmation", {"schema": "rx-geometry-dataset/v1", "lanes": []})]
    )
    assert result["negative_windows"] == 1
    assert result["calibration_reception_windows"] == 2
    assert result["negative_window_fraction"] == 0.5
    assert result["source_negative_windows"] == {"confirmation": 0, "pilot": 1}
    assert result["receiver_candidate_counts"]["rx0"]["mean"] == 0
    assert result["receiver_candidate_counts"]["rx1"]["population_variance"] == 0
    assert result["empty_fractions"]["rx0"] == 1
    assert result["empty_fractions"]["both_receivers"] == 0
    assert result["frequency_circle"]["counts"][1] == 1
    assert result["frequency_circle"]["counts"][15] == 1


def test_duplicate_negative_window_is_rejected_across_inputs():
    with pytest.raises(ValueError, match="duplicated"):
        build_audit([("one", dataset()), ("two", dataset())])


def test_unconditional_mode_keeps_visible_calibration_reception_windows():
    result = build_audit([("pilot", dataset())], population="unconditional")
    assert result["population_windows"] == 2
    assert result["negative_windows"] is None
    assert result["population"] == "unconditional"
    assert result["receiver_candidate_counts"]["rx0"]["mean"] == 0.5
    assert result["receiver_candidate_counts"]["rx1"]["mean"] == 1.0
    assert result["poisson_count_diagnostics"]["rx0"]["variance_to_mean"] == 0.5
