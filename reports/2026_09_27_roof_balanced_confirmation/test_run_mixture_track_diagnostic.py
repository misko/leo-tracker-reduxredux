import copy

import pytest

import run_mixture_track_diagnostic as runner


def score(d, geometry):
    return {"D": d, "D_plus_detection": geometry + 1,
            "D_plus_geometry": geometry, "D_plus_reversed_geometry": geometry + 2}


def test_fixed_inventory_is_D_mean_mixture_and_deduplicates_coordinates():
    rows = [
        {"east_km": 0., "north_km": 0., "latitude_deg": 1., "longitude_deg": 2.,
         "variant_scores": {"old": score(2, 2), "mean": score(2, 2), "mixture": score(2, 2)}},
        {"east_km": 1., "north_km": 0., "latitude_deg": 1.1, "longitude_deg": 2.1,
         "variant_scores": {"old": score(1, 3), "mean": score(1, 1), "mixture": score(1, 1)}},
    ]
    branch = {"point_components": rows,
              "selected": {"old": rows[0], "mean": rows[1], "mixture": rows[1]}}
    actual = runner.fixed_inventory(branch)
    assert len(actual) == 1
    assert actual[0]["labels"] == ["D", "mean", "mixture"]


def test_aggregate_parity_all_variants_and_arms():
    expected = {"variant_scores": {name: score(1, 2) for name in runner.VARIANTS}}
    actual = copy.deepcopy(expected)
    assert runner.aggregate_parity(expected, actual)["passed"]
    actual["variant_scores"]["mixture"]["D_plus_geometry"] += 2e-7
    with pytest.raises(ValueError, match="aggregate parity"):
        runner.aggregate_parity(expected, actual)


def test_pose_reference_requires_one_finite_authority():
    manifest = {"sessions": [{"pose": {"session_id": "s", "pose_authority_digest": "x",
        "pose_authority": {"latitude_deg": 1., "longitude_deg": 2.}}}]}
    assert runner.pose_reference(manifest, "s") == (1., 2., "x")
    with pytest.raises(ValueError, match="one pose"):
        runner.pose_reference(manifest, "missing")
