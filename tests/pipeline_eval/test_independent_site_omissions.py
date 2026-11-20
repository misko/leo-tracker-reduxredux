from math import sqrt

import pytest

from tools.pipeline_eval.qualification import independent_site_omissions as omissions
from tools.pipeline_eval.scoring import validate_result


def test_new_board_geometry_balances_three_unchanged_decoys():
    site = [47.5, 8.5]
    boards = omissions.make_boards(site, "test-site")
    centers = [{tuple(center) for center in board} for board in boards.values()]
    assert len(set.intersection(*centers)) == 3
    assert len(set.union(*centers)) == 7
    assert omissions.make_boards(site, "test-site") == boards
    gaps = [
        min(omissions.tile_distance(center, site) for center in board) for board in boards.values()
    ]
    assert gaps == pytest.approx([0, 1, sqrt(2), 20], abs=0.1)


@pytest.mark.parametrize("face, expected_interior", [(0.99, "withheld"), (1.0, "ok")])
def test_matched_publication_controls_keep_the_shared_numerical_endpoint(face, expected_interior):
    arm = dict(latlon=None, forced_latlon=[6, 10], rf_rms_hz=123)
    rejected = dict(
        status="withheld",
        reason="weak_held_spatial_margin",
        boundary="Measured test fixture",
        metrics=dict(edge_km=face),
        arms=dict(c0=arm, fitted_c=dict(arm)),
    )
    measured, interior, ungated = [
        omissions.identifiable_arms(r) for r in omissions.alternatives(rejected)
    ]
    assert [r["status"] for r in (measured, interior, ungated)] == [
        "withheld",
        expected_interior,
        "ok",
    ]
    assert ungated["arms"]["c0"]["latlon"] == [6, 10]
    for row in (measured, interior, ungated):
        validate_result(row)
        assert row["arms"]["c0"]["forced_latlon"] == [6, 10]
        assert row["arms"]["c0"]["rf_rms_hz"] == 123
        assert row["arms"]["fitted_c"]["status"] == "unavailable"
