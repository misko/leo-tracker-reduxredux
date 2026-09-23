"""Unit checks for the sealed first-six phase-transfer input adapter."""

import importlib.util
from pathlib import Path

import numpy as np

PATH = (
    Path(__file__).parents[2] / "reports/2026_09_23_train_orbit_uncertainty_design/view_inputs.py"
)
SPEC = importlib.util.spec_from_file_location("view_inputs", PATH)
VIEW_INPUTS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VIEW_INPUTS)


def test_inverse_offset_round_trips_sealed_first_six_coordinates():
    cases = (
        ((38.5816, -121.4944), (37.901880219031874, -122.3959378819135)),
        ((39.5296, -119.8138), (37.90230600858144, -122.39601220145329)),
        ((38.5816, -121.4944), (37.80164701877604, -122.41026766208763)),
        ((39.5296, -119.8138), (37.80184772652388, -122.41023886955833)),
    )
    for origin, point in cases:
        east, north = VIEW_INPUTS.inverse_offset(origin, point)
        distance = np.hypot(east, north)
        assert distance > 0
        latitude, longitude = _offset_coordinate(origin, east, north)
        np.testing.assert_allclose([latitude, longitude], point, atol=1e-10)


def _offset_coordinate(centre, east_km, north_km):
    distance = float(np.hypot(east_km, north_km))
    bearing = np.arctan2(east_km, north_km)
    angular = distance / VIEW_INPUTS.RADIUS_KM
    latitude, longitude = np.deg2rad(centre)
    target_latitude = np.arcsin(
        np.sin(latitude) * np.cos(angular) + np.cos(latitude) * np.sin(angular) * np.cos(bearing)
    )
    target_longitude = longitude + np.arctan2(
        np.sin(bearing) * np.sin(angular) * np.cos(latitude),
        np.cos(angular) - np.sin(latitude) * np.sin(target_latitude),
    )
    return tuple(np.rad2deg([target_latitude, target_longitude]))
