import importlib
from pathlib import Path


def test_support_assignment_counts_complete_fixes_and_preserves_panel_order(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    summarize = importlib.import_module("history_retry_roster").summarize
    rows = [dict(case=case, policy=policy, decision=decision) for case, policy, decision in (
        ("DS30-0160", "history_support", "complete"), ("x", None, "solver_failed"),
        ("z", "history_support", "complete"), ("a", "history_support", "complete"))]
    result = summarize(rows)
    assert result["next_case"] == "z"
    assert result["panels"][4] == dict(assigned=4, decisions={"complete": 3, "solver_failed": 1},
                                       complete_policies={"history_support": 3})
    assert summarize(rows[:2])["next_case"] is None
