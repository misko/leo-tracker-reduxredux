from copy import deepcopy
import math

import pytest

from guided_selection import select_rx_guided_doppler


def point(east, north, d):
    return {"east_km": east, "north_km": north,
            "latitude_deg": 1., "longitude_deg": 2., "scores": {"D": d}}


def branch():
    return {
        "arms": {
            "D": {"evaluated_points": 2, "trace": [
                {"event": "evaluate", "east_km": 90., "north_km": 90.},
                {"event": "evaluate", "east_km": 80., "north_km": 80.},
            ]},
            "D_plus_geometry": {"evaluated_points": 2, "trace": [
                {"event": "evaluate", "east_km": 0., "north_km": 0.},
                {"event": "pop", "east_km": 0., "north_km": 0.},
                {"event": "evaluate", "east_km": 10., "north_km": 10.},
            ]},
        },
        "point_components": [
            point(90., 90., -100.),  # Better D, but found only by D arm.
            point(80., 80., 5.),
            point(0., 0., 2.),
            point(10., 10., 1.),
        ],
    }


def test_selects_d_only_within_geometry_arm_inventory():
    result = select_rx_guided_doppler(branch())
    assert (result["selected"]["east_km"], result["selected"]["north_km"]) == (10., 10.)
    assert result["selected"]["scores"]["D"] == 1.
    assert result["evaluated_points"] == result["admissible_coordinate_count"] == 2
    assert [90., 90.] not in result["admissible_coordinates"]


def test_ties_are_deterministic_by_east_then_north():
    value = branch()
    value["point_components"][-2]["scores"]["D"] = 1.
    result = select_rx_guided_doppler(value)
    assert (result["selected"]["east_km"], result["selected"]["north_km"]) == (0., 0.)


@pytest.mark.parametrize("mutation, message", [
    (lambda value: value["arms"]["D_plus_geometry"].update(evaluated_points=3), "count"),
    (lambda value: value["arms"]["D_plus_geometry"]["trace"].append(
        {"event": "evaluate", "east_km": 0., "north_km": 0.}), "more than once"),
    (lambda value: value["point_components"].pop(), "lacks a computed"),
    (lambda value: value["point_components"][-1]["scores"].update(D=math.nan), "finite"),
])
def test_malformed_or_incomplete_artifacts_fail_closed(mutation, message):
    value = branch()
    mutation(value)
    with pytest.raises(ValueError, match=message):
        select_rx_guided_doppler(value)


def test_input_artifact_is_not_mutated():
    value = branch()
    original = deepcopy(value)
    select_rx_guided_doppler(value)
    assert value == original
