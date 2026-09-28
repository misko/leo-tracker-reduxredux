import copy
import math

import pytest

from tools.rx_paired_mark_support import analyze


def _window(session, role, index, rx0, rx1):
    return {
        "source_window_id": f"{session}-{role}-{index}",
        "prediction_utc_ns": index * 1_000_000_000,
        "role": role,
        "observed": {"rx0": rx0, "rx1": rx1},
    }


def _candidate(margin, frequency=100.0):
    return {"fractional_margin": margin, "canonical_rx0_hz": frequency}


def _document():
    lanes = []
    for index in range(6):
        session = f"s{index}"
        lanes.append(
            {
                "recording_split": "calibration",
                "lane": {"session_id": session, "channel": 1, "edge": "lower"},
                "windows": [
                    _window(session, "reception", 1, [], []),
                    _window(
                        session,
                        "held_frequency",
                        2,
                        [_candidate(0.2)],
                        [_candidate(0.6), _candidate(None), _candidate(float("nan"))],
                    ),
                ],
            }
        )
    lanes.append(
        {
            "recording_split": "evaluation",
            "lane": {"session_id": "ignored"},
            "windows": None,
        }
    )
    return {"schema": "rx-geometry-dataset/v1", "lanes": lanes}


def test_frequency_perturbations_do_not_change_output():
    document = _document()
    changed = copy.deepcopy(document)
    for lane in changed["lanes"]:
        if lane["recording_split"] == "calibration":
            for window in lane["windows"]:
                for candidates in window["observed"].values():
                    for candidate in candidates:
                        candidate["canonical_rx0_hz"] = -9e99
    assert analyze(changed) == analyze(document)


def test_empty_windows_and_margin_quality_are_preserved():
    result = analyze(_document())
    lane = result["lanes"][0]
    empty = lane["windows"][0]
    assert empty["count_asymmetry_rx1_minus_rx0"] is None
    assert empty["mean_fractional_margin"] == {"rx0": None, "rx1": None}
    held = lane["roles"]["held_frequency"]
    assert held["window_support"] == {
        "both_empty": 0,
        "only_rx0": 0,
        "only_rx1": 0,
        "both_nonempty": 1,
    }
    assert held["fractional_margin"]["rx1"]["finite_values"] == [0.6]
    assert held["fractional_margin"]["rx1"]["missing_count"] == 1
    assert held["fractional_margin"]["rx1"]["nonfinite_count"] == 1


def test_receiver_swap_reverses_signed_metrics():
    document = _document()
    first = analyze(document)["lanes"][0]["windows"][1]
    swapped = copy.deepcopy(document)
    observed = swapped["lanes"][0]["windows"][1]["observed"]
    observed["rx0"], observed["rx1"] = observed["rx1"], observed["rx0"]
    second = analyze(swapped)["lanes"][0]["windows"][1]
    assert second["count_asymmetry_rx1_minus_rx0"] == -first["count_asymmetry_rx1_minus_rx0"]
    assert second["count_difference_rx1_minus_rx0"] == -first["count_difference_rx1_minus_rx0"]
    assert second["mean_margin_contrast_rx1_minus_rx0"] == pytest.approx(
        -first["mean_margin_contrast_rx1_minus_rx0"]
    )


def test_missing_or_malformed_receivers_are_rejected():
    missing = _document()
    del missing["lanes"][0]["windows"][0]["observed"]["rx1"]
    with pytest.raises(ValueError, match="exactly rx0 and rx1"):
        analyze(missing)
    malformed = _document()
    malformed["lanes"][0]["windows"][0]["observed"]["rx0"] = None
    with pytest.raises(ValueError, match="must be lists"):
        analyze(malformed)


def test_non_numeric_margin_rejected_but_nonfinite_is_accounted():
    document = _document()
    document["lanes"][0]["windows"][1]["observed"]["rx0"][0]["fractional_margin"] = "bad"
    with pytest.raises(ValueError, match="numeric"):
        analyze(document)
    assert math.isnan(float("nan"))
