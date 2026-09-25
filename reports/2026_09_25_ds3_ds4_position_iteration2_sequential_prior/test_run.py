from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

MODULE_PATH = Path(__file__).with_name("run.py")
SPEC = importlib.util.spec_from_file_location("sequential_prior", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_coordinate_round_trip() -> None:
    row = {"latitude_deg": 37.8, "longitude_deg": -122.5}
    assert MODULE.coordinate(MODULE.vector(row)) == pytest.approx((37.8, -122.5))


def test_update_uses_one_vote_per_scan() -> None:
    rows = [
        {"latitude_deg": 0.0, "longitude_deg": 0.0},
        {"latitude_deg": 0.0, "longitude_deg": 2.0},
    ]
    estimate = MODULE.coordinate(np.sum([MODULE.vector(row) for row in rows], axis=0))
    assert estimate == pytest.approx((0.0, 1.0))


def test_distribution_counts_sub_km() -> None:
    value = MODULE.distribution([0.2, 0.8, 1.2])
    assert value["count"] == 3
    assert value["sub_km_count"] == 2
    assert value["median_error_km"] == pytest.approx(0.8)
