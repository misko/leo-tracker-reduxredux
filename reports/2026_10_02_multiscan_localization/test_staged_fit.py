from types import SimpleNamespace

import numpy as np
import pytest
from staged_fit import candidate_ladder, fit_receiver_lines, frozen_row_weights, select_trials


def test_duplicate_alternatives_share_one_weight_unit():
    data = SimpleNamespace(
        group=np.array([0, 0, 0]),
        times=np.ones(3),
        rf=np.ones(3),
        receiver=np.zeros(3),
        channel=np.ones(3),
        measured=np.array([10, 10, 20]),
    )
    np.testing.assert_array_equal(frozen_row_weights(data), [0.5, 0.5, 1])


def test_sparse_candidates_rank_by_support_without_truth():
    rows = [
        {"accepted": True, "source_groups": 20 + index, "span_s": 30, "satellite_index": index}
        for index in range(10)
    ]
    ladder = candidate_ladder(rows)
    assert [len(candidates) for candidates, _ in ladder] == [4, 8, 10]
    np.testing.assert_array_equal(ladder[0][0], [9, 8, 7, 6])


def test_no_supported_candidate_does_not_invent_a_satellite():
    with pytest.raises(ValueError, match="No satellite"):
        candidate_ladder([])


def test_timeout_does_not_disqualify_better_feasible_score():
    converged = {"success": True, "selection_score": 44.0}
    timed_out = {"success": False, "selection_score": 41.0}
    result = select_trials([converged, timed_out])
    assert result["score_leader"] is timed_out
    assert result["converged_leader"] is converged
    assert not result["selection_resolved"]
    assert not result["success"]


def test_all_converged_required_for_resolved_selection():
    trial = {"success": True, "selection_score": 41.0}
    assert select_trials([trial])["selection_resolved"]
    with pytest.raises(ValueError, match="No finite"):
        select_trials([{"success": False, "selection_score": np.inf}])


@pytest.mark.parametrize("slope_bound", [10.0, 50.0])
def test_receiver_lines_recover_independent_drift_across_alias(slope_bound):
    times = np.tile(np.linspace(0, 300, 101), 2)
    receivers = np.repeat([0, 1], 101)
    offsets = np.where(receivers == 0, 112000.0, -30000.0)
    slopes = np.where(receivers == 0, 8.0, -7.0)
    measured = offsets + slopes * (times - 150)
    measured = (measured + 227272.72727272727 / 2) % 227272.72727272727 - 227272.72727272727 / 2
    data = SimpleNamespace(
        times=times,
        measured=measured,
        numbers=np.array([123]),
        predict=lambda parameters, rows, satellites: (
            np.zeros(len(rows)),
            np.ones(len(rows), dtype=bool),
        ),
    )
    rough = {
        "position_km": [12.0, -5.0],
        "assignments": [
            {
                "accepted": True,
                "receiver": receiver,
                "rows": np.flatnonzero(receivers == receiver),
                "satellite_index": 0,
            }
            for receiver in (0, 1)
        ],
    }
    fitted = fit_receiver_lines(data, rough, slope_bound=slope_bound)
    np.testing.assert_allclose(fitted[:6], [12, -5, 112000, 8, -30000, -7], atol=0.01)
