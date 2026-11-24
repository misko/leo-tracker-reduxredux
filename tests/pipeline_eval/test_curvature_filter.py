from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from curvature_filter import eligibility, independent_bound, stable_order, update_ordering
from curvature_filter_trial import score_owners


def test_unequal_times_annihilate_affine_modes_and_leave_smooth_witness():
    times = np.array([1., 3., 5., 9.])
    basis = np.column_stack((np.ones(4), times, times**2))
    certificate = independent_bound(times, basis)
    assert certificate["indices"] == (0, 1, 3)
    assert certificate["nonzero_columns"] == 1
    assert certificate["conditional_loss_floor"] == 0
    weights = certificate["weights"]
    subset = basis[list(certificate["indices"])]
    np.testing.assert_allclose(weights @ subset[:, :2], [0, 0], atol=1e-13)
    assert certificate["strongest_normalized_projection"] == pytest.approx(abs(weights@subset[:, 2]))
    for residual in (-7e6, 0., 800.):
        column = weights @ subset[:, 2]
        beta = residual/column
        assert residual-beta*column == pytest.approx(0, abs=1e-9)


def test_incomplete_or_affine_cases_also_keep_entire_bank():
    times = np.array([2., 4., 9.])
    scan = SimpleNamespace(curved=[0, 1, 2], norads=[13, 11, 21],
                           tracks=[{"times": t} for t in (times, times, times[[0, 1, 1]])],
                           rx_basis=[times[:, None]**2, times[:, None], times[:, None]])
    rows, decision = eligibility(scan)
    assert rows[1]["conditional_loss_floor"] is None
    assert rows[2] is None
    assert decision["tracks"] == {"smooth_spans_contrast": 1, "no_smooth_witness": 1, "unsupported": 1}
    assert decision["survivors"] == decision["slots"] == 9
    assert decision["disposition"] == "original_full_fallback"


def test_ordering_keeps_bank_ties_and_unseen_rows_and_checks_sign_separately():
    best = np.full((1, 5), np.inf)
    seen = np.zeros_like(best, dtype=bool)
    sign = seen.copy()
    observed = np.array([[3.]])
    update_ordering(best, sign, seen, observed, np.array([[-5, 1, 1, 3, 3]]), np.array([[True, True, True, False, False]]))
    update_ordering(best, sign, seen, observed, np.array([[3, 0, 0, 3, 3]]), np.array([[False, False, False, True, False]]))
    np.testing.assert_array_equal(seen, [[True, True, True, True, False]])
    np.testing.assert_array_equal(sign, [[False, True, True, True, False]])
    np.testing.assert_array_equal(stable_order(np.array([9, 5, 2, 4, 6]), best[0]), [4, 5, 2, 9, 6])


def test_owner_join_separates_zero_eligibility_from_heuristic_low_rank():
    selected = [("a", 100, "r"), ("b", 100, "r"), ("c", 200, "r"), ("d", 300, "r"), ("e", 999, "r")]
    score = score_owners(selected, {oid: "track" for oid in "abcd"}, {"track": {100: 2, 200: 29}})
    assert (score["archived_rows"], score["joined_rows"], score["rows_no_bank"], score["rows_top8"], score["rows_top32"]) == (5, 4, 1, 2, 3)
    assert score["track_satellite_pairs"] == {"pairs": 2, "top8": 1, "top32": 2, "best": 2, "worst": 29}
