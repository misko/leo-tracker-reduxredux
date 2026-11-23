from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from causal_cold_audit import owner_delta, summarize


def trace(completed, routing):
    return dict(prefix=[dict(branch=b, score=b, cpu_ns=100_000_000, evaluations=5) for b in (1, 2, 3)],
                completed=[dict(branch=b, score=4-b, cpu_ns=200_000_000, first_evaluations=7,
                                second_evaluations=4) for b in completed], branch=max(completed), routing=routing)


def test_count_first_prefixes_once_and_include_unfinished_challengers():
    result = summarize(trace([1], "winner_raced"), dict(cpu_s=1))
    assert result["first_objective_requests"] == 17
    assert result["total_objective_requests"] == 21
    assert result["setup_rank_and_other_cpu_s"] == pytest.approx(.5)
    assert result["final_score_spread"] is None


def test_refreshed_ranking_can_reverse_original_prefix_choice():
    result = summarize(trace([1, 2, 3], "ambiguous_gap"), dict(cpu_s=1))
    assert result["total_objective_requests"] == 33
    assert result["winner_reversed"]
    assert result["final_penalty_for_selecting_prefix_leader"] == 2
    with pytest.raises(ValueError, match="disjoint CPU accounting"):
        summarize(trace([1], "full_restart_on_invalid"), dict(cpu_s=1))


def test_owner_accounting_counts_changed_satellite_and_role_on_shared_rows():
    a = [("a", 100, "curved"), ("b", 101, "curved")]
    b = [("a", 102, "predictive"), ("c", 103, "curved")]
    assert owner_delta(a, b) == dict(total=2, shared=1, lost=1, new=1, norad_changes=1, role_changes=1)
