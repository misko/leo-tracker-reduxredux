from types import SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import region_halo_trial as study
from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.variants import region_halo as halo


def point(x, y, radius=1.0):
    return dict(xy_km=[x, y], radius_km=radius)


def test_votes_are_signed_and_require_independent_common_face_confidence():
    east = [point(15, 0), point(20, 1), point(30, 2)] * 2
    result = halo.vote(east, 12.5)
    assert result["state"] == "outside"
    assert result["exterior_face"] == "east"
    assert result["robust_outside_distance_km"] == pytest.approx(1.5)
    assert halo.vote([*east[:5], point(-20, 0)], 12.5)["state"] == "ambiguous"
    assert halo.vote([*east[:5], point(15, 0, 3)], 12.5)["state"] == "ambiguous"
    assert halo.vote([point(-3, 5)] * 6, 12.5)["state"] == "inside"
    assert halo.vote(east[:5], 12.5)["state"] == "ambiguous"


def test_orbit_split_is_disjoint_balanced_and_invariant_to_track_order():
    rows = [SimpleNamespace(orbit=i) for i in [1, 2, 3, 1, 2, 5, 6, 9, 13, 28, 38]]
    left, right = halo.partition(rows)
    assert not left & right
    assert left | right == {r.orbit for r in rows}
    assert abs(len(left) - len(right)) <= 1
    assert halo.partition(rows[::-1]) == (left, right)


@pytest.mark.parametrize("site", [[44, -116], [-37, 175]])
def test_geographic_offer_margins_translate_at_both_latitudes(site):
    for margin in (12.5, 1.5, -1.5, -15):
        tile = study.offer(site, axis=0, sign=-1, along=2.5, margin=margin, ident="opaque")
        xy = study.geometry.tangent(site, tile["center"])
        assert 12.5 - max(abs(xy)) == pytest.approx(margin, abs=1e-6)
        assert set(tile) == {"id", "center", "width_km"}


def test_veto_only_affects_an_existing_publication():
    point = dict(latlon=[44, -116], forced_latlon=[44, -116], region_id="offer", rf_rms_hz=70)
    original = dict(status="ok", arms={"c0": point, "fitted_c": point})
    assert halo.qualify(original, dict(state="ambiguous"))["arms"] == original["arms"]
    result = halo.qualify(original, dict(state="outside"))
    assert result["status"] == "withheld"
    assert result["arms"]["c0"]["latlon"] is None
    assert result["arms"]["c0"]["forced_latlon"] == point["latlon"]
    assert result["arms"]["c0"]["rf_rms_hz"] == 70


def test_sealed_chart_scopes_keep_episode_and_calibration_denominators():
    cases = {plot.id: len(plot.cases) for plot in screening_figures.charts(evidence=study.REPORT)}
    assert cases == {
        f"{study.METHOD}-fresh-synthetic": 8,
        f"{study.METHOD}-archived-roof": 2,
        f"{study.METHOD}-archived-majority": 1,
    }
