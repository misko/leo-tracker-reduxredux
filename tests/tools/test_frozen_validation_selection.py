import importlib.util
from pathlib import Path


def load():
    path = Path(__file__).resolve().parents[2] / "reports/2026_09_23_frozen_validation/selection.py"
    spec = importlib.util.spec_from_file_location("selection", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def rows(model, scale, error):
    return [
        {
            "model": model,
            "scale_s": scale,
            "group": g,
            "view_scan_count": n,
            "prior": p,
            "reference_error_km": error,
            "within_prior": True,
            "stopping_rule_satisfied": True,
        }
        for g, size in [("a", 44), ("b", 80)]
        for n in (1, 6, 16, size)
        for p in ("sacramento", "reno")
    ]


def test_tie_prefers_simpler_not_smaller_residual():
    value = load().select(rows("baseline", 0, 1.005) + rows("scan", 5, 1.0), {"a": 44, "b": 80})
    assert value["selected"]["model"] == "baseline"


def test_missing_arm_cannot_win():
    value = load().select(rows("baseline", 0, 10) + rows("global", 1, 0.1)[:-1], {"a": 44, "b": 80})
    assert value["selected"]["model"] == "baseline"


def test_medium_views_share_one_regime_weight():
    data = rows("baseline", 0, 0)
    for row in data:
        if row["view_scan_count"] in (6, 16):
            row["reference_error_km"] = 3
    value = load().select(data, {"a": 44, "b": 80})
    assert value["selected"]["mean_regime_error_km"] == 1
