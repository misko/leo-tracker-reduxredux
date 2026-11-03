"""The common-position pilot must keep every scan's state and cost independent."""

import importlib.util
import sys
from pathlib import Path

import pytest


def test_common_position_sums_all_scan_costs_without_sharing_calibration():
    tools = Path(__file__).resolve().parents[2] / "tools"
    sys.path.insert(0, str(tools))
    try:
        spec = importlib.util.spec_from_file_location(
            "common_position_pilot", tools / "search_multiscan_fixed_families.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(tools))

    class Scan:
        receipt = {"regional_center": [30, -120], "radius_km": 100}

        def __init__(self, longitude, score, n, rms, compatible):
            self.source_fit = dict(latitude_deg=35, longitude_deg=longitude)
            self.score, self.n, self.rms, self.compatible = score, n, rms, compatible
            self.calls = []

        def fit(self, latitude, longitude):
            self.calls.append((latitude, longitude))
            return dict(
                score=self.score,
                private_scan_constant=self.score,
                detail=dict(
                    total_points=self.n,
                    overall_rms_hz=self.rms,
                    member_compatible_points=self.compatible,
                ),
            )

    first, second = Scan(-121, 10, 20, 100, 15), Scan(-123, 30, 10, 200, 0)
    study = module.CommonPosition([first, second])
    assert study.source_fit == dict(latitude_deg=35, longitude_deg=-122)
    result = study.fit(36, -122.5)
    assert result["score"] == 40  # Include even the scan with zero compatible points.
    assert result["detail"]["total_points"] == 30
    assert result["detail"]["member_compatible_points"] == 15
    assert result["detail"]["overall_rms_hz"] == pytest.approx((600000 / 30) ** 0.5)
    assert [f["private_scan_constant"] for f in result["scans"]] == [10, 30]
    assert first.calls == second.calls == [(36, -122.5)]
