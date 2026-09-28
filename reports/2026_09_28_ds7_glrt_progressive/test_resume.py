from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("ds7_progressive_resume", HERE / "resume.py")
assert SPEC is not None and SPEC.loader is not None
resume = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = resume
SPEC.loader.exec_module(resume)


def _context(visit: int) -> dict[str, object]:
    return {
        "session_id": "s",
        "visit_index": visit,
        "rate_hz": 2_500_000,
        "target_index": visit,
        "target": {"channel": 1, "edge": "lower", "rf_center_hz": 1, "if_center_hz": 1},
    }


def _row(entry) -> dict[str, object]:
    repeat, _ordinal, context, method = entry
    return {
        "context": context,
        "method": method,
        "repeat": repeat,
        "status": "ok",
        "result": {"probes": []},
        "diagnostics": {"route": "synthetic"},
        "timing": {"cpu_s": 0.1, "wall_s": 0.2},
    }


def _fixture(tmp_path: Path, prefix_count: int = 13):
    contexts = [_context(10), _context(11)]
    expected = list(resume._expected_entries(contexts))
    rows = [_row(entry) for entry in expected[:prefix_count]]
    source = tmp_path / "source.py"
    source.write_text("sealed = True\n")
    plan = tmp_path / "plan.json"
    plan.write_text('{"plan": true}\n')
    inputs = tmp_path / "inputs.json"
    inputs.write_text('{"inputs": true}\n')
    prior = tmp_path / "prior"
    prior.mkdir()
    receipt = {
        "schema": "ds7-glrt-run/v1",
        "complete": False,
        "sources_unchanged": False,
        "methods": list(resume.METHODS),
        "repetitions": 2,
        "planned_calls": len(expected),
        "plan_sha256": resume.sha(plan),
        "input_manifest_sha256": resume.sha(inputs),
        "source_hashes": {str(source): resume.sha(source)},
        "failed_calls": 0,
    }
    (prior / "run.json").write_text(json.dumps(receipt))
    (prior / "rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return prior, inputs, plan, contexts, expected, rows


def test_rotated_schedule_prefix_validates_and_returns_only_missing_calls(tmp_path) -> None:
    prior, inputs, plan, contexts, expected, rows = _fixture(tmp_path)

    _receipt, validated, missing = resume._validate_predecessor(
        prior,
        inputs,
        plan,
        contexts,
    )

    assert validated == rows
    assert missing == expected[len(rows) :]
    keys = {(repeat, ordinal, method) for repeat, ordinal, _context, method in expected}
    assert len(keys) == len(expected)


@pytest.mark.parametrize("mutation", ("order", "context", "failed", "duplicate"))
def test_partial_validation_rejects_nonprefix_or_unsuccessful_rows(tmp_path, mutation) -> None:
    prior, inputs, plan, contexts, _expected, rows = _fixture(tmp_path)
    if mutation == "order":
        rows[3]["method"], rows[4]["method"] = rows[4]["method"], rows[3]["method"]
    elif mutation == "context":
        rows[2]["context"] = _context(99)
    elif mutation == "failed":
        rows[5]["status"] = "failed"
    else:
        rows.insert(4, dict(rows[3]))
    (prior / "rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))

    with pytest.raises(ValueError):
        resume._validate_predecessor(prior, inputs, plan, contexts)


def test_actual_sigterm_predecessor_is_exact_526_row_prefix() -> None:
    prior = HERE / "run-02"
    inputs = resume.BASE / "inputs.json"
    plan = resume.BASE / "plan.json"
    contexts = json.loads(inputs.read_text())["rows"]

    receipt, rows, missing = resume._validate_predecessor(
        prior,
        inputs,
        plan,
        contexts,
    )

    assert receipt["complete"] is False
    assert len(rows) == 526
    assert len(missing) == 34
    repeat, _ordinal, context, method = missing[0]
    assert (repeat, context["visit_index"], context["rate_hz"], method) == (
        1,
        1106,
        10_000_000,
        "optimized",
    )
    assert resume.sha(prior / "rows.jsonl") == (
        "104fc2d0e47c2dd993d3d8a30a0f66d8e2e840bb71cc5260acfad9f1b8a7d240"
    )


def test_termination_escape_is_not_an_exception_subclass() -> None:
    assert issubclass(resume.ReplayDeadline, BaseException)
    assert not issubclass(resume.ReplayDeadline, Exception)
    with pytest.raises(resume.ReplayDeadline, match="SIGTERM"):
        resume.terminate(15, None)
