"""RF changes within a channel must never share one Graph polynomial."""

import importlib
from pathlib import Path

import numpy as np


def test_rf_lanes_keep_each_original_point_once(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("evaluate_ds22_public_tracks")
    rows = []
    for lane, rf in enumerate((10.7e9, 10.94e9)):
        for i, t in enumerate(np.linspace(0, 40, 81)):
            rows.append(
                dict(
                    observation_id=f"{lane}:{i}",
                    receiver=1,
                    channel=1,
                    time_s=float(t),
                    measured_cfo_hz=float(10000 - 1000 * t),
                    actual_rf_hz=rf,
                )
            )
    tracks, count = tool.graph_rf_lanes(rows, "scan", tool.graph.TrackConfig())
    ids = [oid for t in tracks for oid in t["observation_ids"]]
    assert len(ids) == len(set(ids)) == count
    assert count >= 0.9 * len(rows)
    assert {t["rf_hz"] for t in tracks} == {10.7e9, 10.94e9}
    assert len({t["key"] for t in tracks}) == len(tracks)
    for t in tracks:
        assert len({oid.split(":")[0] for oid in t["observation_ids"]}) == 1
