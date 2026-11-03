from __future__ import annotations

import json

import pytest
from evaluate_soft import continuation_records, reported_status, sealed_records
from soft_experiment import planned_cells


def protocol():
    return {"sessions": ["one", "two"], "models": {"direct": {}, "fisher": {}},
            "tolerances": {"aggressive": {}, "medium": {}, "loose": {}}}


def test_fixed_experiment_contains_all_cells_and_budget_controls():
    assert len(planned_cells(protocol())) == 12
    assert len(planned_cells(protocol(), "direct")) == 6
    with pytest.raises(ValueError, match="unknown solver"):
        planned_cells(protocol(), "replacement")


def test_evaluator_refuses_incomplete_batch_before_reference_access(tmp_path):
    (tmp_path / "protocol-soft.json").write_text(json.dumps(protocol()))
    with pytest.raises(ValueError, match="every planned cell"):
        sealed_records(tmp_path, protocol())


def test_failures_retained_and_ambiguous_cells_rejected(tmp_path):
    (tmp_path / "protocol-soft.json").write_text(json.dumps(protocol()))
    for session, method, tolerance in planned_cells(protocol()):
        directory = tmp_path / "runs-soft" / session / f"{method}-{tolerance}"
        directory.mkdir(parents=True)
        (directory / "failure.json").write_text("{}")
    records, hashes = sealed_records(tmp_path, protocol())
    assert records == {}
    assert len(hashes) == 13
    (directory / "fit.json").write_text("{}")
    with pytest.raises(ValueError, match="exactly one"):
        sealed_records(tmp_path, protocol())


def test_continuation_must_finish_before_any_new_reference_evaluation(tmp_path):
    (tmp_path / "protocol-continuation.json").write_text(json.dumps(
        {"sessions": ["one", "two"], "stages": ["medium", "aggressive"]}))
    with pytest.raises(ValueError, match="all continuation cells"):
        continuation_records(tmp_path)


def test_retained_nonterminal_state_does_not_inherit_terminal_status():
    fitted = {"status": "projected_stationary_visibility_branch", "success": False}
    assert reported_status(fitted) == "best_finite_nonterminal_stationarity_unverified"
    fitted["success"] = True
    assert reported_status(fitted) == fitted["status"]
