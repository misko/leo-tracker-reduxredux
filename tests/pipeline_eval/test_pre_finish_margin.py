from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3.pre_finish_margin import UnsupportedStage, inspect_association, ranked
from reports.ALGO08.v3.pre_finish_margin_score import census, compare


def test_rank_keeps_original_first_index_for_exact_cost_tie():
    costs = np.array([1., 1., 0., 8.])
    passing = np.array([True, True, True, False])
    visible = np.array([True, True, False, True])
    assert list(ranked(costs, passing, visible)) == [0, 1]
    with pytest.raises(UnsupportedStage, match="finite"):
        ranked(costs + np.inf, passing, visible)


def test_compact_winner_does_not_certify_the_second_candidate():
    passing = np.array([True, True, True])
    scan = SimpleNamespace(
        norads=np.array([300, 200, 100]), curved=[0], index=[np.array([0, 1])],
        tracks=[dict(key="curve", observation_ids=["0", "1"], rf_hz=11.5e9)],
        curve=lambda *_: dict(cost=np.array([4., 1., 2.]), passing=passing, alias=np.array([0, 1, -1])),
    )
    compact = dict(cost=np.array([np.inf, 1., np.inf]), passing=np.array([False, True, False]))
    result = (1., [dict(candidate_index=1, compatible=True, cost=1., component="curve")],
              {0: dict(y=np.ones(2), terms=compact, j=1)}, (np.zeros((3,2)), np.ones((3,2)), None))
    (row,), prices = inspect_association(scan, result, "receiver_smooth")
    assert row["gap"] == 1.
    assert row["sealed_gated_ranks"] == [(200, 1., 1.), (100, 2., -1.), (300, 4., 0.)]
    assert row["second_retained_by_original"] is False
    assert prices["profile_cpu_s"] >= 0.


def test_later_owner_join_preserves_ranks_and_marks_membership_mismatch():
    curve = dict(curve="A", observation_ids=["a", "b"], sealed_gated_ranks=[[23, 1., 0.], [99, 2.1, 1.]],
                 gap=1.1, points=2, feasible=2, exact_ties=1, second_retained_by_original=True)
    assert census([curve])["flagged_points"] == 2
    kept = compare([curve], {"A": {"ids": ["a", "b"]}}, [dict(curve="A", old=99, new=23)])[0]
    assert kept["pair_in_top_two"] and kept["id_match"] == "exact_order" and kept["old_rank"] == 2
    reordered = compare([curve], {"A": {"ids": ["b", "a"]}}, [dict(curve="A", old=99, new=23)])[0]
    assert reordered["id_match"] == "overlap_only"
