import pytest

from tools.pipeline_eval.scoring import validate_result
from tools.pipeline_eval.variants import final_region

TILE = {"center": [0.0, 0.0], "width_km": 25.0}


def result(c0, fitted):
    return dict(
        status="ok",
        boundary="two fitted compact positions",
        metrics=dict(c0_frequency_score=3.0, fitted_c_frequency_score=4.0),
        arms=dict(c0=dict(latlon=c0, rf_rms_hz=60.0), fitted_c=dict(latlon=fitted, rf_rms_hz=59.0)),
    )


@pytest.mark.parametrize("released", [False, True])
@pytest.mark.parametrize("near_arm", ["c0", "fitted_c"])
def test_selected_branch_withholds_the_pair_and_retains_rf_and_raw_positions(released, near_arm):
    face = [12.481 / 111.0, 0.0]
    interior = [0.0, 0.0]
    skim = result(face, interior) if near_arm == "c0" else result(interior, face)
    candidate, other = (
        dict(result=skim, tile=TILE),
        dict(result=result(interior, interior), tile=TILE),
    )
    early, full = (candidate, other) if released else (other, candidate)

    assert final_region.select(early, full, released=released) is candidate
    selected = final_region.select(early, full, released=released, enabled=True)["result"]
    validate_result(selected)
    assert selected["status"] == "withheld"
    assert selected["reason"] == "terminal_compact_fit_at_tile_face"
    assert selected["metrics"]["exact_tile_margin_km"][near_arm] == pytest.approx(0.019)
    assert selected["metrics"] | skim["metrics"] == selected["metrics"]
    for arm, raw in skim["arms"].items():
        assert selected["arms"][arm] == dict(raw, latlon=None, forced_latlon=raw["latlon"])


def test_twenty_one_meters_of_clearance_retains_both_publications():
    attempt = result([12.479 / 111.0, 0], [0, 0])
    selected = final_region.publish(attempt, TILE, enabled=True)
    assert selected["status"] == "ok"
    assert selected["arms"] == attempt["arms"]


@pytest.mark.parametrize("status", ["withheld", "failed", "timed_out"])
def test_preserves_the_existing_no_position_result(status):
    attempt = dict(status=status, boundary="compact position attempt", reason="test", metrics={})
    assert final_region.publish(attempt, TILE, enabled=True) is attempt


def test_guarded_success_requires_both_finite_endpoints():
    attempt = result(None, [0, 0])
    with pytest.raises(ValueError, match="both selected positions"):
        final_region.publish(attempt, TILE, enabled=True)
