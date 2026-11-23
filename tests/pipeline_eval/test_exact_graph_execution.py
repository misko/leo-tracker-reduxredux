from importlib import import_module
from pathlib import Path

import numpy as np

from leo.analysis import graph_tracklets, polynomial_tracklets
from leo.analysis.localization_v3 import tracks


def test_combined_execution_reuses_best_piece_and_keeps_original_graph_rows(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    scope = import_module("exact_graph_execution").graph_execution
    original_edges, original_graph = graph_tracklets._graph, tracks.graph_tracks
    fit, best = tracks.fit_lane, polynomial_tracklets._best_piece
    cfg = polynomial_tracklets.TrackConfig()
    time = np.linspace(0, 30, 32)
    cfo = 18.0 * time + 11.0 * time ** 2
    expected = original_edges(time, cfo, cfg)

    def lane(t, y, config):
        ix = np.arange(12)
        for _ in range(2):
            polynomial_tracklets._best_piece(t, y, ix, y[ix], config)
        return fit(t, y, config)

    monkeypatch.setattr(tracks, "fit_lane", lane)
    rows = [dict(actual_rf_hz=1e10, receiver=1, channel=1, observation_id=str(k), time_s=t, measured_cfo_hz=y)
            for k, (t, y) in enumerate(zip(time, cfo, strict=True))]
    audit = {}
    with scope(enabled=True, audit=audit):
        actual = graph_tracklets._graph(time, cfo, cfg)
        tracks.graph_tracks(rows, cfg)
    for before, after in zip(expected[:4], actual[:4], strict=True):
        assert before.dtype == after.dtype and before.tobytes() == after.tobytes()
    assert audit["graph"]["calls"] == 1 and audit["graph"]["edge_lanes"] == 2
    assert audit["cache"]["best_hits"] >= 1
    assert graph_tracklets._graph is original_edges and tracks.graph_tracks is original_graph
    assert tracks.fit_lane is lane and polynomial_tracklets._best_piece is best


def test_disabled_scope_without_audit_never_changes_installed_functions(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    scope = import_module("exact_graph_execution").graph_execution
    before = graph_tracklets._graph, tracks.graph_tracks, tracks.fit_lane
    with scope():
        assert (graph_tracklets._graph, tracks.graph_tracks, tracks.fit_lane) == before
