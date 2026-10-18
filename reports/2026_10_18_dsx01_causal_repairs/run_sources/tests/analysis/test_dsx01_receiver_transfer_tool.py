"""Postfit linear transfer must not recalibrate the accepted site or radio."""

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def test_transfer_uses_frozen_wide_drift_and_never_calls_calibration(tmp_path, monkeypatch):
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        tool = importlib.import_module("transfer_dsx01_receiver_pool")
    finally:
        sys.path.remove(path)
    raw = tmp_path / "reports/2026_10_18_dsx01_retention_localization/per_scan.csv"
    raw.parent.mkdir(parents=True)
    raw.write_text("case,raw_points\nDSX01-S01,5\n")
    source = tmp_path / "result/pooled/shared_phase/mean_10_endpoints.json"
    source.parent.mkdir(parents=True)
    state = dict(beta=[0, 0, 0, 0, 1500, 1500, 0, 0], phases=[0], extra={}, smooth=[[0] * 11] * 2)
    fit = dict(latitude_deg=37.9, longitude_deg=-122.5, states={"DSX01-S01": state})
    source.write_text(json.dumps({"c0": fit, "fitted_c": fit}))
    frozen = source.read_bytes()
    calls = []
    scan = SimpleNamespace(center=(37.9, -122.5), scale=88.0, geometry={})

    def forbidden(*args, **kwargs):
        raise AssertionError("linear transfer must never update calibration")

    scan.update, scan.at_point = forbidden, forbidden

    def association(state, base, point, method, *, all_tracks):
        assert all_tracks and state["beta"][4] == 1500
        np.testing.assert_allclose(point, [0, 0])
        calls.append(method)
        return (
            0,
            [
                dict(points=2, parts=1, compatible=True, residual_hz=[2, -2]),
                dict(points=3, parts=1, compatible=False, residual_hz=[9] * 3),
            ],
            None,
            None,
        )

    scan.association = association
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    monkeypatch.setattr(tool, "OUTPUT", tmp_path / "result")
    monkeypatch.setattr(tool, "Scan", lambda case: scan)
    monkeypatch.setattr(tool, "phase_linear_frequency", lambda *args: None)
    output = tool.run("DSX01-S01", ("shared_phase",))
    records = json.loads((output / "shared_phase.json").read_text())
    assert len(calls) == 2 and source.read_bytes() == frozen
    for r in records.values():
        assert r["associated_points"] == 2 and r["percent_associated"] == 40
        assert r["position_and_nuisance_frozen"]
