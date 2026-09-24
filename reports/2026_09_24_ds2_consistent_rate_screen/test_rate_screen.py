from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def module():
    path = Path(__file__).parent / "run_rate_screen.py"
    spec = importlib.util.spec_from_file_location("ds2_rate_screen_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_point_grid_is_symmetric_and_contains_the_sealed_centre():
    tool = module()
    points = tool.point_grid({"latitude_deg": 37.0, "longitude_deg": -122.0}, 0.25)
    assert len(points) == 9
    observed = {
        (row["east_from_sealed_winner_km"], row["north_from_sealed_winner_km"])
        for row in points
    }
    assert observed == {
        (east, north) for east in (-0.25, 0.0, 0.25) for north in (-0.25, 0.0, 0.25)
    }


def test_control_uses_nominal_score_and_rate_arm_uses_rate_selection_score():
    tool = module()
    row = {
        "east_from_sealed_winner_km": 0.0,
        "north_from_sealed_winner_km": 0.0,
        "rate_aware": {"fit": {"selection_objective": 0.2}},
        "nominal_control": {"selection_objective": 0.3},
    }
    assert tool.row_key(row, "rate_aware")[0] == 0.2
    assert tool.row_key(row, "nominal_control")[0] == 0.3
