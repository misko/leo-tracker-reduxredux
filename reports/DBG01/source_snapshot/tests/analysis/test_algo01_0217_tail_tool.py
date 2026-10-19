"""Protect observation identities and graph-threshold diagnostics in DBG01."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


def tool():
    root = Path(__file__).resolve().parents[2] / "tools"
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("dbg01_tail", root / "debug_algo01_0217_rx1_ch1_tail.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_partial_acceptance_does_not_accept_rejected_prefix():
    m = tool()
    tracks = [dict(key="partial", observation_ids=["a", "b"]),
              dict(key="full", observation_ids=["c"])]
    associations = [dict(component="partial", compatible=True, observation_ids=["b"]),
                    dict(component="full", compatible=True),
                    dict(component="rejected", compatible=False)]
    assert m.accepted_ids(associations, tracks) == {"b", "c"}


def test_secondary_peak_time_includes_within_visit_offset_and_tie_rank():
    m = tool()
    candidates = [dict(candidate_rank=k, fractional_margin=.5, fractional_tracking_cfo_hz=k * 1000,
                       passed_fractional_margin_gate=True) for k in (2, 0)]
    document = dict(sample_rate_hz=1000, probe_ms=20,
                    timing=dict(session_start_device_sample_counter=100),
                    probes=[dict(receiver_id=0, channel=1, valid_start_counter=1100,
                                 probe_start_ms=250, candidates=candidates)])
    rows = m.candidate_rows(document, lo=0, hi=2)
    assert [r["time_s"] for r in rows] == pytest.approx([1.26, 1.26])
    assert [r["rank"] for r in rows if r["winner"]] == [0]


def test_exhaustive_score_agrees_with_graph_for_straight_path():
    m = tool()
    t = np.arange(8.)
    y = t * 100
    cfg = m.TrackConfig()
    exact = m.exhaustive_paths(t, y, cfg)["8"]["score"]
    graph = m.graph._graph(t, y, cfg)
    path, _, _, score = m.graph._best_path(t, y, graph, np.ones(8, bool),
                                         np.ones(len(graph[0]), bool), cfg)
    assert len(path) == 8
    assert score == pytest.approx(exact)


def test_short_cadence_has_no_graph_edges():
    m = tool()
    cfg = m.TrackConfig()
    graph = m.graph._graph(np.array([0., .12]), np.array([0., 20.]), cfg)
    assert len(graph[0]) == 0
