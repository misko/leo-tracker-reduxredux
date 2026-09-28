import copy

import pytest

import run_dual_track_diagnostic as runner


def scores(value):
    return {"D": value, "D_plus_detection": value + 1,
            "D_plus_geometry": value + 2, "D_plus_reversed_geometry": value + 3}


def fixture():
    rows = [{"east_km": x, "north_km": 0., "latitude_deg": 1. + x,
             "longitude_deg": 2. + x,
             "variant_scores": {name: scores(d) for name, d in
                 (("old", 2. - x), ("detection", 3. - 2*x), ("dual", 4. - 3*x))}}
            for x in (0., 1.)]
    return {"point_components": rows,
            "selected": {"old": rows[1], "detection": rows[1], "dual": rows[1]}}


def test_inventory_uses_D_old_detection_dual_and_deduplicates():
    inventory = runner.fixed_inventory(fixture())
    assert len(inventory) == 1
    assert inventory[0]["labels"] == ["D", "old", "detection", "dual"]


def test_aggregate_parity_all_variants_arms_finite_and_quadrature():
    source = fixture()["point_components"][0]
    diagnostic = {"variant_scores": copy.deepcopy(source["variant_scores"]),
                  "latitude_deg": source["latitude_deg"],
                  "longitude_deg": source["longitude_deg"],
                  "quadrature_maximum_candidate_loglik_absolute_difference": {
                      name: 1e-5 for name in runner.VARIANTS}}
    assert runner.aggregate_parity(source, diagnostic)["passed"]
    diagnostic["variant_scores"]["dual"]["D_plus_geometry"] += 2e-7
    with pytest.raises(ValueError, match="aggregate parity"):
        runner.aggregate_parity(source, diagnostic)
    diagnostic["variant_scores"]["dual"]["D_plus_geometry"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        runner.aggregate_parity(source, diagnostic)
    diagnostic["variant_scores"] = copy.deepcopy(source["variant_scores"])
    diagnostic["latitude_deg"] += 1e-5
    with pytest.raises(ValueError, match="physical coordinate"):
        runner.aggregate_parity(source, diagnostic)


def test_only_two_outcome_selected_indices_are_allowed():
    assert runner.ALLOWED_INDICES == (0, 1)
