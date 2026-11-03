"""Post-fit association ranks feasible candidates and requires curved support."""

import importlib
from pathlib import Path

import numpy as np
import pytest


def setup(monkeypatch, curved=True):
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
    return study, fit


@pytest.mark.parametrize("curved", [True, False])
def test_association_selects_after_noise_gates_and_checks_curved_support(monkeypatch, curved):
    study, fit = setup(monkeypatch, curved)
    result = study.associate(fit)
    row = result["rows"][0]
    assert row["candidate_norad"] == 200
    assert row["candidates_passing_all_frequency_gates"] == 1
    assert row["frequency_compatible_before_calibration_support"]
    assert row["compatible"] is curved
    assert result["compatible_points"] == (40 if curved else 0)
    assert row["qualified_curved_hardware_support"] == int(curved)


def test_fixed_family_label_cannot_bypass_residual_gates(monkeypatch):
    study, fit = setup(monkeypatch)
    result = study.associate(fit, fixed_labels={"target": 100})
    assert result["rows"][0]["candidate_norad"] == 100
    assert not result["rows"][0]["frequency_compatible_before_calibration_support"]
    assert result["compatible_points"] == 0


def test_vetted_fixed_label_retains_its_original_physical_checks(monkeypatch):
    study, fit = setup(monkeypatch)
    original = study.associate(fit)
    fixed = study.associate(fit, fixed_labels={"target": 200})
    assert fixed == original


def test_fixed_family_can_preserve_a_valid_label_against_a_better_single_fragment(monkeypatch):
    study, fit = setup(monkeypatch)
    module = importlib.import_module("search_track_evidence_position")
    y = study.tracks[0]["values"]
    noise = np.random.default_rng(1).normal(0, 100, len(y))
    f = np.stack([y - 0.5 * noise, y - 1.2 * noise])
    monkeypatch.setattr(module, "phase_frequency_grid", lambda *a, **k: (f, np.full_like(f, 45)))
    independent = study.associate(fit)
    assert independent["rows"][0]["candidate_norad"] == 100
    fixed = study.associate(fit, fixed_labels={"target": 200})
    assert fixed["rows"][0]["candidate_norad"] == 200
    assert fixed["rows"][0]["compatible"]
    assert fixed["rows"][0]["candidates_passing_all_frequency_gates"] == 2


@pytest.mark.parametrize("binding", [{"unknown": 200}, {"target": 999}])
def test_fixed_label_must_bind_both_original_fragment_and_candidate(monkeypatch, binding):
    study, fit = setup(monkeypatch)
    with pytest.raises(ValueError, match="unknown"):
        study.associate(fit, fixed_labels=binding)
