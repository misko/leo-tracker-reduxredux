import importlib
from pathlib import Path


def test_north_to_weak_gate_is_strict_on_individual_mask_and_caps_named_regression(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
    screen = importlib.import_module("cycle_stereo_saved")

    def arms(c0, fitted_c):
        return {"c0": {"error_m": c0}, "fitted_c": {"error_m": fitted_c}}

    trial = dict(decision="complete", candidate=arms(355, 150),
                 controls=dict(individual=arms(700, 160), named=arms(105, 140)))
    assert screen.eligible(trial)
    assert not screen.eligible(dict(trial, candidate=arms(355.001, 150)))
    assert not screen.eligible(dict(trial, candidate=arms(355, 160)))
    assert not screen.eligible(dict(trial, decision="withheld"))
