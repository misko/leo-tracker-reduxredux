"""The IQ panel cannot silently join ambiguous support or a different peak."""

import importlib
from pathlib import Path

import pytest


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
