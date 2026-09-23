"""Replication wrapper must preserve declared arms and reject parity drift."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    path = (
        Path(__file__).resolve().parents[2]
        / "reports/2026_09_23_second_train_epoch_replication/run.py"
    )
    spec = importlib.util.spec_from_file_location("replication", path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_worker_keeps_failed_scale_and_all_arms(monkeypatch):
    runner = load()
    monkeypatch.setattr(runner, "replay_scans", lambda *args: [])
    calls = []

    def fit(single, tracks, prior, search, scale):
        calls.append(scale)
        if scale == 1.0:
            raise ValueError("intentional solver failure")
        return {"prior": prior, "scale_s": scale}

    helper = SimpleNamespace(
        prepare=lambda *args: ([], []),
        score=lambda *args: {"training_capped800_rmse_hz": 3.0},
        fit_arm=fit,
    )
    monkeypatch.setattr(runner, "module", lambda *args: helper)
    baseline = {
        "prior": "reno",
        "search": {
            "selected": {"scans": [], "latitude_deg": 0, "longitude_deg": 0, "objective_rmse_hz": 3}
        },
    }
    result = runner.worker(("global", baseline, ["one"]))
    assert calls == [0.2, 1.0, 5.0]
    assert len(result) == 3 and "failure" in result[1]
    assert all(row["view_scan_count"] == 1 for row in result)


def test_worker_rejects_changed_objective(monkeypatch):
    runner = load()
    monkeypatch.setattr(runner, "replay_scans", lambda *args: [])
    helper = SimpleNamespace(
        prepare=lambda *args: ([], []), score=lambda *args: {"training_capped800_rmse_hz": 4.0}
    )
    monkeypatch.setattr(runner, "module", lambda *args: helper)
    baseline = {
        "prior": "reno",
        "search": {
            "selected": {"scans": [], "latitude_deg": 0, "longitude_deg": 0, "objective_rmse_hz": 3}
        },
    }
    with pytest.raises(ValueError, match="parity"):
        runner.worker(("scan", baseline, ["one"]))
