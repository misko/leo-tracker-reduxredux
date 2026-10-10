import runpy
from pathlib import Path

api = runpy.run_path(str(Path(__file__).with_name("report.py")))


def test_raw_and_explicit_fallback_aggregation():
    rows = [
        {
            "arms": {
                "fitted-c": {
                    "archive": {"qualified": True, "error_km": 2},
                    "phase": {"qualified": False, "error_km": 0.1},
                }
            }
        },
        {"arms": {"fitted-c": {"archive": {"qualified": True, "error_km": 3}, "phase": None}}},
    ]
    raw = api["aggregate"](rows, "fitted-c", "phase")
    assert raw["position_metrics_withheld"] and "mean_km" not in raw
    fallback = api["aggregate"](rows, "fitted-c", "phase", True)
    assert fallback["fallbacks"] == 2 and fallback["mean_km"] == 2.5
