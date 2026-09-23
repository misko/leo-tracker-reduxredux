"""Joint replication must reject support changes and worsening assignments."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("support_changed", [False, True])
def test_invalid_reassignment_fails_closed(monkeypatch, support_changed):
    path = (
        Path(__file__).resolve().parents[2]
        / "reports/2026_09_23_second_train_joint_replication/run.py"
    )
    spec = importlib.util.spec_from_file_location("joint_replication", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    single = SimpleNamespace(PRIORS={"reno": (0, 0, 500)}, offset_coordinate=lambda *args: (0, 0))
    joint = SimpleNamespace(
        identities=lambda rows: rows,
        reassociate=lambda *args: {"b" if support_changed else "a": "sat"},
    )
    helper = SimpleNamespace(score=lambda *args: {"penalized_objective_rmse_hz": 11.0})
    monkeypatch.setattr(
        runner,
        "load",
        lambda path, name: {"single": single, "joint": joint, "helper": helper}[name],
    )
    arm = {
        "prior": "reno",
        "east_km": 0,
        "north_km": 0,
        "taus_s": {"s": 0},
        "fixed_tracks": {"a": "sat"},
        "penalized_objective_rmse_hz": 10.0,
        "scale_s": 1,
    }
    with pytest.raises(ValueError, match="support" if support_changed else "increased"):
        runner.worker((arm, ["s"]))
