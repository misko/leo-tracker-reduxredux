import pytest
from plot_final_diagnostic import diagnostic_rows


def test_polish_fills_only_the_single_two_stage_failure(monkeypatch) -> None:
    rows = [
        {"unit_id": "ok", "effective_accepted": True, "effective_error_m": 100.0},
        {"unit_id": "DS11-F087", "effective_accepted": False, "effective_error_m": None},
    ]
    monkeypatch.setattr("plot_final_diagnostic.validate_continuation", lambda _doc: rows)
    primary_rows = [
        {"unit_id": "ok", "accepted": True, "error_m": 100.0,
         "old_greedy_error_m": None},
        {"unit_id": "DS11-F087", "accepted": False, "error_m": None,
         "old_greedy_error_m": 300.0},
    ]
    rows[0]["primary"] = dict(primary_rows[0])
    rows[1]["primary"] = dict(primary_rows[1])
    monkeypatch.setattr("plot_final_diagnostic.validate_complete", lambda _doc: primary_rows)
    primary = {"rows": primary_rows}
    result = diagnostic_rows(
        primary,
        {},
        {"valid": True, "unit_id": "DS11-F087", "evaluator_only_error_m": 2066.0},
    )
    assert [row["error_m"] for row in result["two_stage"]] == [100.0, None]
    assert [row["error_m"] for row in result["polished"]] == [100.0, 2066.0]


def test_polish_rejects_audit_for_nonfailure(monkeypatch) -> None:
    monkeypatch.setattr(
        "plot_final_diagnostic.validate_continuation",
        lambda _doc: [{"unit_id": "ok", "effective_accepted": True,
                       "effective_error_m": 100.0,
                       "primary": {"unit_id": "ok", "accepted": True,
                                   "error_m": 100.0}}],
    )
    primary_rows = [{"unit_id": "ok", "accepted": True, "error_m": 100.0,
                     "old_greedy_error_m": None}]
    monkeypatch.setattr("plot_final_diagnostic.validate_complete", lambda _doc: primary_rows)
    with pytest.raises(ValueError, match="sole two-stage failure"):
        diagnostic_rows(
            {"rows": primary_rows},
            {},
            {"valid": True, "unit_id": "DS11-F087", "evaluator_only_error_m": 2066.0},
        )
