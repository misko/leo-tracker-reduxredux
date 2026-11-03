"""The grouped/c/RF arms preserve one explicit point population."""

import hashlib
import importlib
import json
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.track_catalogue_geometry import frequency_grid
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km


@pytest.mark.parametrize("clutter", [False, True])
def test_same_points_all_four_arms_and_no_fake_position_estimate(tmp_path, monkeypatch, clutter):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("associate_merged_track_catalogue")
    t = np.arange(21.0)
    site = geodetic_to_ecef_km(37.5, -122.0, 0.0)
    up = ecef_to_enu_matrix(37.5, -122.0)[2]
    position = np.broadcast_to(site + 550 * up, (2, len(t), 3)).copy()
    velocity = np.stack([np.broadcast_to(up, (len(t), 3)), np.broadcast_to(2 * up, (len(t), 3))])
    sky = dict(time_s=t, position_km=position, velocity_km_s=velocity, norad=np.array([123, 456]))
    frequency, _ = frequency_grid(sky, t, 37.5, -122.0)
    recording, inputs = tmp_path / "recording", tmp_path / "inputs"
    recording.mkdir()
    inputs.mkdir()
    tracks = [
        dict(
            key=f"rx{rx}",
            receiver=rx,
            channel=1,
            rf_hz=11.5e9,
            times=t.tolist(),
            values=(frequency[0] + 50000 * clutter).tolist(),
        )
        for rx in (1, 2)
    ]
    (recording / "tracks.json").write_text(json.dumps(tracks))
    (recording / "merged.json").write_text(
        json.dumps(
            dict(
                calibration=dict(beta=[0.0] * 8),
                result=dict(ownership={"rx1": "shared", "rx2": "shared"}),
            )
        )
    )
    np.savez(inputs / "bank.npz", **sky)
    (inputs / "receipt.json").write_text(
        json.dumps(
            dict(
                source_id="test",
                bank_sha256=hashlib.sha256((inputs / "bank.npz").read_bytes()).hexdigest(),
                tracks_sha256=hashlib.sha256((recording / "tracks.json").read_bytes()).hexdigest(),
            )
        )
    )
    monkeypatch.setattr(tool.matching, "solve", lambda stats, initial, budget: (initial, [0] * 4))
    output = tmp_path / "output"
    tool.associate(recording, inputs, output, 37.5, -122.0)
    rows = json.loads((output / "summary.json").read_text())
    assert len(rows) == 4
    assert {r["graph_points"] for r in rows} == {42}
    assert {r["components"] for r in rows if r["grouped"]} == {1}
    assert {r["components"] for r in rows if not r["grouped"]} == {2}
    assert all(
        r["compatible_points"] == (0 if clutter else 42) and r["position_error_km"] is None
        for r in rows
    )
