"""Receipt-level tests for completed optimization summaries."""

import importlib.util
import json
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "summarize_variants_under_test", HERE / "summarize_variants.py"
)
summary = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(summary)


def receiver(label: str, timing: float = 1.0) -> dict:
    return {
        "result": {"label": label, "total_cpu_ms": timing},
        "screens": {"label": label, "total_wall_ms": timing},
    }


def write_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
               candidate_receivers: list[list[dict]], reference_receivers: list[dict]) -> Path:
    optimize = tmp_path / "optimize"
    candidate = optimize / "work" / "candidate" / "arm-all"
    reference = tmp_path / "target_run_01"
    candidate.mkdir(parents=True)
    reference.mkdir()
    monkeypatch.setattr(summary, "HERE", optimize)
    (candidate / "completion.json").write_text(
        json.dumps({"complete": True, "passed": True, "cases": 1})
    )
    (candidate / "assessments.json").write_text(json.dumps([{
        "case_id": "case-1", "passed": True,
        "reference_cost": {"total_cpu_ms": 10.0},
        "candidate_cost": {"total_cpu_ms": 8.0},
    }]))
    (candidate / "case-1.json").write_text(json.dumps({
        "rate_hz": 2500000,
        "repetitions": [{"receivers": value} for value in candidate_receivers],
    }))
    (reference / "case-1-D.json").write_text(json.dumps({
        "repetitions": [{"receivers": reference_receivers}],
    }))
    return candidate


def test_exact_science_count_includes_every_repetition_and_receiver(tmp_path, monkeypatch):
    expected = [receiver("rx0"), receiver("rx1")]
    candidate = write_case(tmp_path, monkeypatch, [expected, expected], expected)

    result = summary.summarize(candidate)

    assert result["exact_science"] == {"checked": 4, "matched": 4, "passed": True}
    assert result["groups"]["2500000_real"]["cases"] == 1


def test_science_mismatch_is_counted_and_fails_parity(tmp_path, monkeypatch):
    expected = [receiver("rx0"), receiver("rx1")]
    candidate = write_case(tmp_path, monkeypatch,
                           [expected, [receiver("rx0"), receiver("changed")]], expected)

    result = summary.summarize(candidate)

    assert result["exact_science"] == {"checked": 4, "matched": 3, "passed": False}


def test_missing_completion_is_rejected(tmp_path, monkeypatch):
    optimize = tmp_path / "optimize"
    candidate = optimize / "work" / "candidate" / "arm-all"
    candidate.mkdir(parents=True)
    monkeypatch.setattr(summary, "HERE", optimize)

    with pytest.raises(FileNotFoundError):
        summary.summarize(candidate)


def test_completion_case_count_must_match_assessments(tmp_path, monkeypatch):
    expected = [receiver("rx0"), receiver("rx1")]
    candidate = write_case(tmp_path, monkeypatch, [expected], expected)
    (candidate / "completion.json").write_text(
        json.dumps({"complete": True, "passed": True, "cases": 2})
    )

    with pytest.raises(ValueError, match="assessment count"):
        summary.summarize(candidate)
