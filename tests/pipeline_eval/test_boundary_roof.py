from collections import Counter

import pytest

from tools.pipeline_eval.qualification import boundary_roof_offers as offers
from tools.pipeline_eval.qualification import boundary_roof_results as results
from tools.pipeline_eval.scoring import ARMS


def test_roof_faces_use_exact_solver_tangent_geometry():
    truth = [37.9, -122.5]
    tiles = list(offers.build_offers("fixed-input", truth, {"id": "original", "center": truth}))
    assert len({tile["id"] for tile, _ in tiles}) == 4
    assert len({label["id"] for _, label in tiles}) == 4
    assert all(set(tile) == {"id", "center", "width_km"} for tile, _ in tiles)
    margins = [results.shared.roi_margin(truth, tile) for tile, _ in tiles]
    assert margins[0] == pytest.approx(12.5)
    assert 1.0 < margins[1] < 2.0
    assert margins[2] == pytest.approx(-margins[1], abs=1e-6)
    assert margins[3] == pytest.approx(-6.0, abs=1e-6)
    assert len({label["face"] for _, label in tiles[1:]}) == 1


def test_roster_balances_datasets_with_disjoint_sealed_reserve():
    plan = offers.phase._read(offers.clock.REPORT / "plan.json")
    roster = offers.roster(plan)
    assert not set(roster["primary"]) & set(roster["reserve"])
    for cohort, count in (("primary", 5), ("reserve", 3)):
        assert Counter(ident[:4] for ident in roster[cohort]) == {"DS26": count, "DS29": count}


def test_containment_requires_both_calibration_circles_and_preserves_forced_diagnostic():
    truth = [37.9, -122.5]
    tile, _ = list(offers.build_offers("example", truth, {"id": "original", "center": truth}))[1]
    point = dict(latlon=truth, forced_latlon=truth, radius_km=1.0, region_id=tile["id"])
    row = dict(tile=tile, result=dict(status="ok", arms={arm: point.copy() for arm in ARMS}))
    assert results.gate(row) is row
    row["result"]["arms"]["fitted_c"]["radius_km"] = 2.0
    withheld = results.gate(row)["result"]
    assert withheld["status"] == "withheld"
    assert withheld["reason"] == "nominal_position_radius_crosses_tile_edge"
    assert all(
        arm["forced_latlon"] == truth and arm["latlon"] is None for arm in withheld["arms"].values()
    )
    assert row["result"]["arms"]["c0"]["latlon"] == truth
