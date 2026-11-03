import copy
import math

import pytest

from tools.rx_direction_support import analyze, nominee_support


def test_eastbound_westbound_and_sign_swap():
    times = [0, 1, 3, 6, 10]
    east = [-1.0, -0.7, 0.1, 0.7, 1.0]
    up = [0.1, 0.9, 0.8, 0.9, 0.1]
    forward = nominee_support(times, east, up)
    reverse = nominee_support(times, [-value for value in east], up)
    assert forward["order"] == "rx0_before_rx1"
    assert reverse["order"] == "rx1_before_rx0"
    assert forward["crossing_slope_per_s"] > 0
    assert reverse["crossing_slope_per_s"] < 0


@pytest.mark.parametrize(
    ("east", "up", "reason"),
    [
        ([-1, 0, 0, 1], [0, 1, 1, 0], "zero_plateau"),
        ([-1, -0.5, 0.5], [1, 0.5, 0], "boundary_scheduled_peak"),
        ([-1, 0, 1], [0, 1, 0], "simultaneous_scheduled_peaks"),
    ],
)
def test_ambiguous_or_boundary_peaks_are_unavailable(east, up, reason):
    result = nominee_support(range(len(east)), east, up)
    assert result["order"] == "unavailable"
    assert result["unavailable_reason"] == reason


def _document(second_east, second_log_prior=None):
    if second_log_prior is None:
        second_log_prior = -math.log(2)
    components = [
        {
            "kind": "track_candidate", "track_id": "t0", "catalog_number": 7,
            "rank": 1, "log_prior": -math.log(2),
        },
        {
            "kind": "track_candidate", "track_id": "t1", "catalog_number": 7,
            "rank": 2, "log_prior": second_log_prior,
        },
        {"kind": "other", "log_prior": None},
    ]
    windows = []
    first_east = [-1.0, -0.7, 0.1, 0.7, 1.0]
    up = [0.1, 0.9, 0.8, 0.9, 0.1]
    for index, time in enumerate((0, 1, 3, 6, 10)):
        windows.append(
            {
                "prediction_utc_ns": time,
                "role": "held_frequency",
                "predictions": [
                    {
                        "track_id": "t0", "catalog_number": 7,
                        "visible": True,
                        "los_enu_unit": {
                            "east": first_east[index],
                            "up": up[index],
                        },
                    },
                    {
                        "track_id": "t1", "catalog_number": 7,
                        "visible": True,
                        "los_enu_unit": {
                            "east": second_east[index],
                            "up": up[index],
                        },
                    },
                ],
            }
        )
    return {
        "schema": "rx-geometry-dataset/v1",
        "lanes": [
            {
                "lane": {
                    "session_id": "s", "channel": 1, "edge": "lower",
                    "actual_rf_hz": 1.0,
                },
                "recording_split": "evaluation",
                "components": components,
                "windows": windows,
            }
        ],
    }


def test_same_order_has_zero_disagreement_and_needs_no_observed_field():
    result = analyze(_document([-0.9, -0.6, 0.2, 0.8, 1.1]))["lanes"][0]
    assert result["pair_disagreement_mass"] == 0
    assert len(result["nominees"]) == 2
    assert {row["track_id"] for row in result["nominees"]} == {"t0", "t1"}


def test_tiny_prior_is_preserved_in_weighted_disagreement():
    document = _document([1.0, 0.7, -0.1, -0.7, -1.0], second_log_prior=-30.0)
    result = analyze(copy.deepcopy(document))["lanes"][0]
    assert result["pair_disagreement_mass"] > 0
    assert result["order_mass"]["rx1_before_rx0"] > 0
    assert result["nominees"][0]["catalog_number"] == result["nominees"][1]["catalog_number"]


def test_zero_prior_serializes_as_null_and_all_zero_is_rejected():
    document = _document([1.0, 0.7, -0.1, -0.7, -1.0])
    document["lanes"][0]["components"][1]["log_prior"] = None
    lane = analyze(document)["lanes"][0]
    assert lane["nominees"][1]["log_prior"] is None
    assert lane["nominees"][1]["normalized_log_prior"] is None
    assert lane["nominees"][1]["prior"] == 0
    document["lanes"][0]["components"][0]["log_prior"] = None
    with pytest.raises(ValueError, match="finite"):
        analyze(document)


def test_invisible_peak_and_multiple_crossings_are_unavailable():
    document = _document([-0.9, -0.6, 0.2, 0.8, 1.1])
    document["lanes"][0]["windows"][1]["predictions"][0]["visible"] = False
    lane = analyze(document)["lanes"][0]
    assert lane["nominees"][0]["unavailable_reason"] == "crossing_bracket_not_visible"
    assert lane["nominees"][0]["crossing_event_visible"] is False
    assert lane["nominees"][0]["rx0_peak_visible"] is False
    support = nominee_support([0, 1, 2, 3], [-1, 0, 1, -1], [0, 1, 0.8, 0])
    assert support["unavailable_reason"] == "no_unique_linear_zero_crossing"


@pytest.mark.parametrize("mutation", ("duplicate", "missing", "unknown_kind"))
def test_component_prediction_membership_is_exact(mutation):
    document = _document([-0.9, -0.6, 0.2, 0.8, 1.1])
    if mutation == "duplicate":
        document["lanes"][0]["components"][1]["track_id"] = "t0"
    elif mutation == "missing":
        document["lanes"][0]["windows"][0]["predictions"].pop()
    else:
        document["lanes"][0]["components"].insert(-1, {"kind": "mystery"})
    with pytest.raises(ValueError):
        analyze(document)
