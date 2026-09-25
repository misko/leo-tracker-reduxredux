from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds3_ds4_iteration1", HERE / "run.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def rows(points, rms=None):
    rms = rms or [100.0] * len(points)
    return [
        {"latitude_deg": point[0], "longitude_deg": point[1], "rf_rms_hz": score}
        for point, score in zip(points, rms, strict=True)
    ]


def test_equal_mean_does_not_depend_on_rf_score() -> None:
    points = [(38.0, -122.0), (38.1, -122.1), (37.9, -121.9)]
    first = MODULE.estimate("equal_spherical_mean", rows(points, [10, 20, 30]))
    second = MODULE.estimate("equal_spherical_mean", rows(points, [300, 20, 1]))
    assert np.allclose(first, second)


def test_inverse_rms_mean_favours_lower_rf_residual() -> None:
    value = MODULE.estimate(
        "inverse_rf_rms2_mean",
        rows([(38.0, -122.0), (39.0, -121.0)], [10.0, 1000.0]),
    )
    assert MODULE.haversine_km(value, (38.0, -122.0)) < 0.1


def test_robust_centres_reject_one_remote_outlier() -> None:
    points = [(38.0, -122.0), (38.001, -122.001), (38.002, -122.002), (48.0, -80.0)]
    for method in ("rf_trimmed_mean", "spatial_trimmed_mean", "geometric_median", "huber_center"):
        value = MODULE.estimate(method, rows(points))
        assert MODULE.haversine_km(value, (38.001, -122.001)) < 1.0
