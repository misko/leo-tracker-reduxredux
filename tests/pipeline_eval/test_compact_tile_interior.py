import pytest

from tools.pipeline_eval.qualification import screening_figures, transfer_edge_trial
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants.compact_tile_interior import guard, margin

TILE = dict(center=[30, -50], width_km=25.0)


def endpoint(north):
    return [30 + north / 111.0, -50.0]


def result(zero, fitted):
    return dict(
        status="ok",
        metrics={},
        arms={
            "c0": {"latlon": endpoint(zero), "rf_rms_hz": 10},
            "fitted_c": {"latlon": endpoint(fitted), "rf_rms_hz": 11},
        },
    )


def test_paired_face_guard_preserves_original_rf_and_conditional_endpoints():
    raw = result(3, 12.5)
    assert margin(raw["arms"]["fitted_c"]["latlon"], TILE) == pytest.approx(0.0, abs=1e-10)
    guarded = guard(raw, TILE)
    assert guarded["status"] == "withheld"
    for arm in ARMS:
        assert guarded["arms"][arm]["latlon"] is None
        assert guarded["arms"][arm]["forced_latlon"] == raw["arms"][arm]["latlon"]
        assert guarded["arms"][arm]["rf_rms_hz"] == raw["arms"][arm]["rf_rms_hz"]
    assert raw["status"] == "ok"


def test_guard_only_admits_both_arms_interior_and_propagates_unavailable():
    inside = result(12.470, -7)
    assert guard(inside, TILE)["arms"] == inside["arms"]
    assert guard(result(12.490, -7), TILE)["status"] == "withheld"
    unavailable = {"status": "timed_out"}
    assert guard(unavailable, TILE) is unavailable


def test_new_interior_chart_has_three_paired_offers_and_two_calibration_arms():
    [card] = screening_figures.charts(evidence=transfer_edge_trial.REPORT)
    assert len(card.cases) == 3
    for arm in ARMS:
        for name in ("candidate", "stock"):
            assert len([mark for mark in card.page(arm).rows if mark.series == name]) == 3
