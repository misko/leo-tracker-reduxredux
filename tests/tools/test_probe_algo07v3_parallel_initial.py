"""Guard the external concurrency experiment's extraction and ordering."""

import inspect
from types import SimpleNamespace

import algo07v3_initial_oracle as initial_search
import pytest
from probe_algo07v3_parallel_initial import ARMS, transformed_function


def test_extracted_arm_runs_original_body_and_returns_complete_result(monkeypatch):
    calls = []
    problem = SimpleNamespace(
        rows=["row"],
        alias=["alias"],
        reference=[1],
        state=lambda x: {"state": x},
        calculate=lambda x: {"conditional_residual_hz": [2]},
    )
    monkeypatch.setattr(
        initial_search,
        "refreshed",
        lambda *a, **kw: (calls.append((a, kw)) or problem, {"parameters": [3]}, ["history"]),
    )
    monkeypatch.setattr(initial_search, "actual_metrics", lambda *a: {"metric": 4})
    monkeypatch.setattr(initial_search, "extend_associations", lambda *a: {"extended": 5})
    candidate, arm, source, modified = transformed_function(initial_search, lambda *a: None)
    assert source == inspect.getsource(initial_search.initial_search)
    assert "pair = _pair(scan, sigma, node, rounds, iterations)" in modified
    assert callable(candidate)
    for name in ARMS:
        result = arm("scan", 150, "node", name, 5, 48)
        assert calls[-1] == (("scan", 150, "node", name), {"rounds": 5, "iterations": 48})
        assert result == dict(
            fit={"parameters": [3]},
            phase_rounds=["history"],
            state={"state": [3]},
            reference=[1],
            metrics={"metric": 4},
            all_graph_associations={"extended": 5},
            profile_gradient=None,
            conditional_residual_hz=[2],
        )


def test_unexpected_source_refused():
    with pytest.raises(ValueError, match="ordered initial"):
        transformed_function(SimpleNamespace(initial_search=transformed_function), None)
