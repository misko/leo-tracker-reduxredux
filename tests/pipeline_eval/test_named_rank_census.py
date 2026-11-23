import importlib
from pathlib import Path

import pytest


def test_withheld_winner_is_timed_but_excluded_from_fix_rate(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    census = importlib.import_module("named_rank_census")
    def row(case, decision, rank, cost):
        return dict(case=case, decision=decision, winner=rank, initial_screen_cpu_s=cost, process_cpu_s=20.,
                    score_advantage_over_first=1.5 if rank == 2 else 0.)
    result = census.summarize([row("a", "withheld", 0, 2.), row("b", "complete", 2, 1.),
                               row("c", "solver_failed", None, None)])
    assert result["fixed_winners"] == {2: 1}
    assert result["earliest_nonzero"] == "b"
    assert result["timed_process_cpu_s"] == 40.
    assert result["total_recorded_screen_cpu_s"] == pytest.approx(3.)
