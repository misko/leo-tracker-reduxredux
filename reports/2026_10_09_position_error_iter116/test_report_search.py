import json
import runpy
from pathlib import Path

import pytest

MODULE = runpy.run_path(str(Path(__file__).with_name("report_search.py")))


def evaluated(east, score, depth=0):
    return {"event": "evaluated", "east": east, "north": 0, "depth": depth, "score": score}


def test_rank_changes_on_identical_initial_domain():
    native = MODULE["summarize"]([evaluated(0, 1), evaluated(40, 2)])
    fixed = MODULE["summarize"]([evaluated(0, 3), evaluated(40, 1)])
    result = MODULE["compare_initial"](native, fixed)
    assert result["initial_domains_equal"]
    assert not result["initial_rank_comparison_complete"]
    assert [r["rank_delta"] for r in result["initial_rank_changes"]] == [1, -1]


def test_partial_domain_and_deferred_counts_are_not_imputed():
    partial = MODULE["summarize"]([evaluated(0, 1)])
    assert not partial["trace_sealed"] and partial["deferred_cell_count"] is None
    other = MODULE["summarize"]([evaluated(0, 2), evaluated(40, 3)])
    assert not MODULE["compare_initial"](partial, other)["initial_domains_equal"]


def test_sealed_trace_failures_and_depths():
    events = [
        evaluated(0, 1),
        evaluated(20, 2, 1),
        {"event": "fit-status", "status": "complete", "converged": False},
        {"event": "fit-status", "status": "failed"},
        {"event": "deferred", "cells": [{"depth": 2}, {"depth": 2}]},
        {"event": "ranks", "rows": [{}, {}]},
    ]
    result = MODULE["summarize"](events)
    assert result["trace_sealed"] and result["deferred_by_depth"] == {2: 2}
    assert result["unqualified_point_count"] == result["failed_point_count"] == 1
    with pytest.raises(AssertionError, match="Duplicate"):
        MODULE["summarize"]([evaluated(0, 1), evaluated(0, 2)])


def test_empty_live_snapshot_and_foreign_terminal_rejected(tmp_path):
    result = MODULE["build"](tmp_path, "frozen")
    assert not result["study_terminal"] and result["known_finished_elapsed_s"] == 0
    assert len(result["traces"]) == 4
    (tmp_path / "result.json").write_text(
        json.dumps(
            {
                "protocol_sha256": "different",
                "status": "complete",
                "complete": True,
            }
        )
    )
    with pytest.raises(AssertionError, match="Foreign"):
        MODULE["build"](tmp_path, "frozen")
