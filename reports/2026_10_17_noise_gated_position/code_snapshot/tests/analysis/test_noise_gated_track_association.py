"""Post-fit association ranks feasible candidates and requires curved support."""

import importlib
from pathlib import Path

import numpy as np
import pytest


@pytest.mark.parametrize("curved", [True, False])
def test_association_selects_after_noise_gates_and_checks_curved_support(monkeypatch, curved):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    module = importlib.import_module("search_track_evidence_position")
    t = np.arange(40, dtype=float)
    y = 50000 - 1500 * t + 3 * t**2
    white = np.random.default_rng(1).normal(0, 120, len(t))
    f = np.stack([y - np.linspace(-150, 150, len(t)), y - white])
    monkeypatch.setattr(module, "phase_frequency_grid", lambda *a, **k: (f, np.full_like(f, 45)))
    study = object.__new__(module.EvidenceExperiment)
    study.tracks = [dict(key="target", receiver=1, channel=1, rf_hz=11.5e9, times=t, values=y)]
    study.curved_keys = frozenset(["target"] if curved else [])
    study.sky = dict(norad=np.array([100, 200]))
    fit = dict(latitude_deg=37.5, longitude_deg=-122, beta=np.zeros(8), phases_s=np.zeros(2))
    result = study.associate(fit)
    row = result["rows"][0]
    assert row["candidate_norad"] == 200
    assert row["candidates_passing_all_frequency_gates"] == 1
    assert row["frequency_compatible_before_calibration_support"]
    assert row["compatible"] is curved
    assert result["compatible_points"] == (len(t) if curved else 0)
    assert row["qualified_curved_hardware_support"] == int(curved)
