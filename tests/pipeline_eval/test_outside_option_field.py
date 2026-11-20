from collections import Counter

import numpy as np
import pytest

from tools.pipeline_eval.qualification import outside_option_field_trial as trial
from tools.pipeline_eval.qualification.independent_site_omissions import tile_distance
from tools.pipeline_eval.variants import outside_option_field as solver


def test_exterior_excludes_other_regions_and_keeps_matched_coarse_budget():
    center = [40.0, -88.0]
    tiles = solver.base.offset(center, np.array([[0, 0], [27, 0], [85, -30], [-60, -30]]))
    test = solver.base.offset(center, np.array([[0, 0], [27, 0], [0, 22], [0, 50]]))
    gaps = solver.tile_gaps(test, tiles)
    np.testing.assert_allclose(gaps, [min(tile_distance(x, p) for x in tiles) for p in test])
    assert tuple(gaps[:2]) == (0.0, 0.0)
    assert gaps[2] == pytest.approx(9.5)
    points, _, edge = solver.halo_coarse(center, tiles)
    assert len(points) == solver.COARSE_POINTS
    assert np.all((edge > 0) & (edge <= solver.HALO_WIDTH_KM + 1e-6))
    assert np.all(solver.tile_gaps(points, tiles) > 0)


@pytest.mark.parametrize(
    "exterior_train,exterior_held,reason",
    [
        (2000, 10000, None),
        (100, 10000, "training_prefers_exterior"),
        (2000, 1100, "held_exterior_not_ruled_out"),
    ],
)
def test_publication_requires_training_winner_and_held_margin(
    exterior_train, exterior_held, reason
):
    inside = dict(early=1000, held=1000, point=np.array([40, -88]), ids=[1, 2, 3], edge_km=3)
    outside = dict(
        early=exterior_train,
        held=exterior_held,
        point=np.array([40, -87.8]),
        ids=[1, 2, 3],
        outside_gap_km=5,
    )
    stock = dict(metrics=dict(held_ids=[1, 2, 3], separated_pass_windows=True))
    result = solver.summarize_challenge([inside], [outside], stock, [49] * 4)
    assert result["reason"] == reason
    assert result["arms"]["c0"]["latlon"] == ([40, -88] if reason is None else None)
    assert result["metrics"]["unconstrained_branch"] == (
        "outside" if exterior_train < 1000 else "inside"
    )


def test_frozen_enrollment_balances_two_near_and_wide_challenges():
    roster, receipt = trial.enroll("test-observation", trial.geometry.ANCHOR)
    assert receipt["consumed"] >= len(roster)
    assert Counter(r[2] for r in roster) == {"containing": 2, "near": 2, "wide": 2}
    assert all(12.5 <= r[-1] <= 22 for r in roster if r[2] == "wide")
