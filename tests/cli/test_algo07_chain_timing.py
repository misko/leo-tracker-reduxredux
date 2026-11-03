"""Cumulative stage timings must never be summed as independent work."""

import copy
from types import SimpleNamespace

import pytest

from leo.cli.algo07_chain_timing import collect, summarize


def chain():
    result = dict(schema_version=1, state="complete", model_version="ALGO02", elapsed_seconds=10.,
                  stages=[dict(stage="prepare", seconds=2.), dict(stage="fit", seconds=7.)])
    for v in range(2, 7):
        prior = result.get("total_seconds", result.get("elapsed_seconds"))
        result = dict(schema_version=v, state="complete", model_version=f"ALGO{v+1:02d}",
                      decision="fallback", total_seconds=prior+v, session_id="session",
                      **{"baseline" if v == 2 else "incumbent": result,
                         "baseline_seconds" if v == 2 else "incumbent_seconds": prior,
                         "numerical_seconds" if v == 3 else "recovery_seconds": float(v)})
    return result


def test_exclusive_sum_avoids_counting_incumbents_repeatedly():
    result = summarize(chain())
    assert [r["worker_seconds"] for r in result["stages"]] == [10, 2, 3, 4, 5, 6]
    assert result["position_worker_seconds"] == 30
    assert result["end_to_end_seconds"] is None
    assert "native GLRT" in result["excluded"]


@pytest.mark.parametrize("field,value", [("total_seconds", 50), ("incumbent_seconds", 0),
    ("recovery_seconds", -1), ("recovery_seconds", float("nan")),
    ("recovery_seconds", True), ("state", "failed"), ("schema_version", 5)])
def test_inconsistent_or_incomplete_chain_rejected(field, value):
    doc = chain()
    doc[field] = value
    with pytest.raises(ValueError):
        summarize(doc)


def test_collect_uses_public_ports_and_checks_identity():
    doc = chain()
    job = dict(job_id="job", state="complete", run_id="run")
    store = SimpleNamespace(status=lambda key: copy.deepcopy(job),
                            terminal=lambda job: (doc, {"sha256": "pin"}))
    report = dict(run_id="run", session_id="session", recording_name="recording", window_count=100)
    native = SimpleNamespace(detail=lambda run, include_points: copy.deepcopy(report))
    result = collect(SimpleNamespace(job="job"), store=store, native_store=native)
    assert result["terminal_sha256"] == "pin" and result["window_count"] == 100
    report["session_id"] = "another"
    with pytest.raises(ValueError, match="identities differ"):
        collect(SimpleNamespace(job="job"), store=store, native_store=native)
