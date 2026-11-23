from pathlib import Path
import runpy

import pytest


GUARD = runpy.run_path(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/short_graph_guard.py"))
lane_counts = GUARD["lane_counts"]


def row(radio=1, channel=3, rf=10_900_000_000.0):
    return {"receiver": radio, "channel": channel, "actual_rf_hz": rf}


def test_small_lanes_remain_separate_at_all_three_original_boundaries():
    rows = [row()] * 7 + [row(radio=2)] * 7 + [row(channel=4)] * 7 + [row(rf=10_900_000_001.0)] * 7
    bound = lane_counts(rows, 8)
    assert bound["proven"] and bound["winning_rows"] == 28
    assert len(bound["lanes"]) == 4 and all(lane["rows"] == 7 for lane in bound["lanes"])


def test_one_lane_at_the_exact_minimum_requires_the_full_graph():
    bound = lane_counts([row()] * 8 + [row(radio=2)], 8)
    assert not bound["proven"]
    assert bound["minimum_points"] == 8


def test_configuration_is_integer_and_validated():
    with pytest.raises(ValueError, match="minimum point count"):
        lane_counts([row()], 8.0)


def test_curvature_certificate_preserves_exact_20_second_threshold_and_lane_keys():
    from math import nextafter

    curvature_extent = GUARD["curvature_extent"]
    rows = [dict(row(), time_s=k / 40) for k in range(400)]
    rows += [dict(row(), time_s=nextafter(20., 0.)), dict(row(radio=2), time_s=60.),
             dict(row(channel=4), time_s=61.), dict(row(rf=10_900_000_001.), time_s=62.)]
    assert curvature_extent(rows)["proven"]
    rows.append(dict(row(), time_s=20.))
    assert not curvature_extent(rows)["proven"]


def test_nonfinite_or_overflow_span_never_proves_curvature():
    prove_extent = GUARD["curvature_extent"]
    with pytest.raises(ValueError, match="Nonfinite"):
        prove_extent([dict(row(), time_s=float("nan"))])
    with pytest.raises(ValueError, match="Overflowing"):
        prove_extent([dict(row(), time_s=t) for t in (-1.7e308, 1.7e308)])


def test_certified_inactive_retains_named_reason_for_a_far_offer(monkeypatch):
    from leo.analysis.localization_v3.region import SearchRegion
    from tools.pipeline_eval.variants.experimental.regional_reassignment import probes
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal

    monkeypatch.syspath_prepend(str(Path(GUARD["__file__"]).parent))
    from early_region import before_fit

    offer = SearchRegion((-23.5, 121.0))
    points = list(probes(offer))
    winner = next(p for p in points if p["side"] == "exterior" and max(map(abs, p["xy_km"])) >= 37.5)
    full = evaluate_terminal(points, offer.width_km, lambda p: {"1": float(p is winner), "2": float(p is winner)})
    assert full["complete"] and full["would_withhold"]

    def fit(prepared, *_):
        return {"reason": prepared["status"]}

    called = []

    def check(*_, **kwargs):
        called.append(kwargs)
        return full

    def status(phase, named):
        audit = []
        route = before_fit(fit, None, check, audit, None, named_inactive=named)
        return route({"status": phase, "tracks": {"tracks": [object()]}}, offer, None, {})["reason"]

    assert status("no_active_curvature", True) == "no_active_curvature" and not called
    assert status("no_active_curvature", False) == "both_receivers_support_far_exterior"
    assert status("inputs_prepared", True) == "both_receivers_support_far_exterior"
    assert len(called) == 2
