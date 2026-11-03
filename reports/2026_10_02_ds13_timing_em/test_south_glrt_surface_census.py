import numpy as np
import pytest
from south_glrt_surface_census import census_rows, local_peak, summarize


def test_local_peak_recovers_quadratic_vertex_and_flags_boundary():
    grid = np.arange(-250., 251., 25.)
    offset, edge, interpolated = local_peak(-(grid - 38.) ** 2)
    assert offset == pytest.approx(38.)
    assert not edge and interpolated
    assert local_peak(grid) == (250., True, False)


def test_census_preserves_both_signs_and_zero_without_satellite_filter():
    rows = [{"row": str(index), "stable_confident_match": stable,
             "path_attributed_data_gain": gain}
            for index, (stable, gain) in enumerate(
                [("True", -1), ("True", 0), ("True", 1), ("False", 100)])]
    assert census_rows(rows[::-1]) == rows[:3]


def test_aggregation_excludes_failed_parity_scores_but_preserves_coverage():
    base = {"session": "A", "truth_satellite": "42", "receiver": "0",
            "control_score_change": 0., "score_parity_error": 0.}
    rows = [dict(base, status=status, path_attributed_data_gain=proxy, exact_score_change=score)
            for status, proxy, score in [("available", 1, .1), ("available", -1, -.2),
                                         ("parity_failed", 1, 100), ("budget_skipped", -1, 0)]]
    total = next(row for row in summarize(rows) if row["satellite"] == "all")
    assert total["eligible_count"] == 4
    assert total["available_count"] == 2
    assert total["score_proxy_sign_agreement_count"] == 2
    assert total["sum_exact_score_change"] == -.1
