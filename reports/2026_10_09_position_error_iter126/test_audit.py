import runpy
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import pytest

api = runpy.run_path(str(Path(__file__).with_name("audit.py")))


def fixture(monkeypatch, time=1.0, wrong_visibility=False):
    n, k = 1, 3
    p = np.tile([2.0, 0.0, 1.0], (k, 2, 1))
    v = np.tile([1.0, 0.0, 0.0], (k, 2, 1))
    terms = NS(nll=0.0, prediction_gradient=np.ones((n, k)))
    model = NS(
        observations=NS(
            times_s=np.array([time]), rf_hz=np.ones(n) * 299792.458, measured_hz=np.zeros(n)
        ),
        bank=NS(nodes_s=np.array([0.0, 1.0]), numbers=np.arange(k), position_km=p, velocity_km_s=v),
        basis=np.zeros((k, 0)),
        prior=None,
        design=np.zeros((n, 5)),
        baseline=np.zeros(n),
        clock_design=np.zeros((n, 0)),
        delta_time=np.zeros((n, k)),
        score=NS(clutter_rate=1.0, detection_budget=1.0),
        evaluate_joint=lambda *_: (0.0, None, None, terms),
        physical_corrections=lambda *_: (np.zeros(k), np.zeros(k)),
    )
    vector = np.zeros(8)
    endpoint = {"vector": vector, "clock_coefficients": [], "objective": 0.0}
    archive = {"stages": {"B7": {a: dict(endpoint) for a in ("fitted-c", "zero-c")}}}
    globals_ = api["audit_model"].__globals__
    monkeypatch.setitem(globals_, "observer", lambda *_: (np.zeros(3), np.array([1.0, 0.0, 0.0])))

    def predict(*args, **kwargs):
        assert kwargs["derivatives"] is False
        return np.full((n, k), -2 / np.sqrt(5)), np.full((n, k), not wrong_visibility), None, None

    monkeypatch.setitem(globals_, "predict_orbits", predict)
    monkeypatch.setitem(globals_, "likelihood", lambda *_: terms)
    return model, archive


def test_last_node_and_zero_visibility_parity(monkeypatch):
    model, archive = fixture(monkeypatch)
    result = api["audit_model"](model, archive)
    assert result["arms"]["fitted-c"]["visibility_changed"] == 0
    model, archive = fixture(monkeypatch, wrong_visibility=True)
    with pytest.raises(AssertionError):
        api["audit_model"](model, archive)


def test_outside_and_score_admission(monkeypatch):
    model, archive = fixture(monkeypatch, time=1.0001)
    with pytest.raises(AssertionError):
        api["audit_model"](model, archive)
    model, archive = fixture(monkeypatch)
    archive["stages"]["B7"]["fitted-c"]["objective"] = 1.0
    monkeypatch.setitem(
        api["audit_model"].__globals__, "observer", lambda *_: pytest.fail("alternative ran")
    )
    with pytest.raises(AssertionError):
        api["audit_model"](model, archive)
