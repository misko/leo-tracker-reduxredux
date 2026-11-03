"""The IQ panel cannot silently join ambiguous support or a different peak."""

import importlib
from pathlib import Path

import numpy as np
import pytest


def test_complete_track_selection_preserves_every_member_without_labels(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("qualify_track_frame_cfo")
    monkeypatch.setattr(tool, "raw_curvature", lambda track: True)
    tracks = []
    for g in range(4):
        for n in (12, 20, 16):
            key = f"{g}-{n}"
            tracks.append(
                dict(
                    key=key,
                    receiver=g // 2 + 1,
                    channel=1 + 4 * (g % 2),
                    times=np.arange(n),
                    values=np.arange(n) * 100.0,
                    observation_ids=[f"{key}-{i}" for i in range(n)],
                )
            )
    points = tool.select_points(tracks, complete_tracks=True)
    assert len(points) == 4 * (20 + 16)
    assert {p["observation_id"] for p in points} == {
        oid for t in tracks if len(t["times"]) >= 16 for oid in t["observation_ids"]
    }
    assert len(tool.select_points(tracks)) == 16
    assert len(tool.select_points(tracks, all_graph_points=True)) == 4 * (12 + 20 + 16)


def test_source_group_identity_resolves_support_without_midpoint_assumption(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("qualify_track_frame_cfo")
    candidate = dict(
        passed_fractional_margin_gate=True,
        fractional_tracking_cfo_hz=123.0,
        fractional_margin=0.8,
        candidate_rank=0,
    )
    probe = dict(
        receiver_id=0,
        channel=2,
        valid_start_counter=2500000,
        candidates=[candidate],
        visit_index=42,
        probe_index=0,
    )
    source = dict(input_manifest_sha256="sha256:" + "a" * 64, probes=[probe])
    index = tool.physical_group_index(source)
    point = dict(
        receiver=1, channel=2, time_s=1.01052, graph_cfo_hz=123.0, observation_id=next(iter(index))
    )
    _, result, difference = tool.match_probe(
        point, [probe], [0, 1], 0, 2500000, 20, identity_index=index
    )
    assert result is candidate
    assert difference == pytest.approx(-0.00052)
    with pytest.raises(ValueError, match="identity"):
        tool.match_probe(
            dict(point, observation_id="other"),
            [probe],
            [0, 1],
            0,
            2500000,
            20,
            identity_index=index,
        )
    with pytest.raises(ValueError, match="duplicate"):
        tool.physical_group_index(dict(source, probes=[probe, probe]))


def test_unique_probe_requires_time_channel_receiver_and_gated_peak(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("qualify_track_frame_cfo")
    point = dict(receiver=1, channel=2, time_s=1.0104, graph_cfo_hz=123.0)
    candidate = dict(
        passed_fractional_margin_gate=True,
        fractional_tracking_cfo_hz=123.0,
        fractional_margin=0.8,
        candidate_rank=0,
    )
    probe = dict(receiver_id=0, channel=2, valid_start_counter=2500000, candidates=[candidate])
    _, result, difference = tool.match_probe(point, [probe], [0, 1], 0, 2500000, 20)
    assert result is candidate
    assert difference == pytest.approx(-0.0004)
    for invalid in (
        [],
        [probe, probe],
        [dict(probe, channel=1)],
        [dict(probe, candidates=[dict(candidate, fractional_tracking_cfo_hz=200.0)])],
        [dict(probe, candidates=[dict(candidate, passed_fractional_margin_gate=False)])],
        [dict(probe, valid_start_counter=2490000)],
    ):
        with pytest.raises(ValueError):
            tool.match_probe(point, invalid, [0, 1], 0, 2500000, 20)
