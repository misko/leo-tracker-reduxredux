"""The bounded exact search can refine both geographic axes without GPS input."""

import importlib
import json
from pathlib import Path

import numpy as np


def test_binary_scales_reach_a_smooth_two_axis_minimum_within_budget(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    module = importlib.import_module("search_fixed_satellite_families")

    class Study:
        receipt = dict(regional_center=[37.5, -122], radius_km=250)
        source_fit = dict(latitude_deg=37.5, longitude_deg=-122)

        def fit(self, latitude, longitude):
            point = np.array(
                [(longitude + 122) * 111.32 * np.cos(np.deg2rad(37.5)), (latitude - 37.5) * 111]
            )
            value = float(np.sum((point - np.array([4.375, -6.1875])) ** 2))
            return dict(
                score=value,
                latitude_deg=latitude,
                longitude_deg=longitude,
                exact_phase_geometry=True,
                detail=dict(overall_rms_hz=np.sqrt(value), member_compatible_points=100),
            )

    result = module.locate(Study(), tmp_path)
    assert result["endpoint"]["score"] < 0.01
    assert result["locations"] <= 73
    assert not result["evaluation_position_used_in_search"]
    assert result["labels_and_calibration_population_frozen"]
    saved = json.loads((tmp_path / "fit.json").read_text())
    assert saved["endpoint"]["exact_phase_geometry"]
