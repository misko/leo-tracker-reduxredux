"""Synthetic driver controls; no corpus input or optimizer invocation."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("audit108", HERE / "audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_real_rho0_parity_reordered_segments(monkeypatch):
    from leo.analysis.hard60_score import likelihood
    from leo.application.hard60_runner import HARD60_SCORE

    y = np.array([0.0, 10.0, 20.0, 30.0])
    prediction = y[:, None] + np.array([5.0, 100.0, 500.0])[None, :]
    visible = np.ones_like(prediction, bool)
    terms = likelihood(y, prediction, visible, HARD60_SCORE)
    obs = SimpleNamespace(
        times_s=np.array([0.0, 0.1, 1.0, 1.1]),
        receiver=np.array([0, 1, 0, 1]),
        channel=np.ones(4),
        rf_hz=np.full(4, 1e10),
        measured_hz=y,
    )
    model = SimpleNamespace(
        observations=obs,
        score=HARD60_SCORE,
        basis=np.zeros((3, 1)),
        precision=np.zeros((2, 2)),
        bank=SimpleNamespace(numbers=np.array([1, 2, 3])),
        evaluate_joint=lambda *_: (terms.nll, None, None, terms),
    )
    monkeypatch.setattr(audit, "predictions", lambda *_: (prediction, visible))
    layout = audit.prepare_segments(((0, 2), (1, 3)), obs)
    row = audit.audit_arm(model, np.zeros(9), np.zeros(2), terms.nll, layout)
    assert abs(row["rho0_whole_score_delta"]) < 1e-12
    assert row["rho0_prediction_gradient_max_abs"] == 0
    assert row["ambiguity"]["populations"]["linked"]["rows"] == 4
    with pytest.raises(AssertionError):
        audit.audit_arm(model, np.zeros(9), np.zeros(2), terms.nll + 1, layout)


def test_switches_do_not_label_errors():
    terms = SimpleNamespace(
        clutter_probability=np.array([0.01, 0.01, 0.9]),
        responsibilities=np.array([[0.95, 0.04], [0.04, 0.95], [0.05, 0.05]]),
    )
    result = audit.ambiguity(terms, dict(segments=((0, 1, 2),)), np.array([10, 20]))
    assert result["switches"] == dict(
        links=2,
        changed=2,
        satellite_to_satellite=1,
        involving_clutter=1,
        confident_satellite_switches=1,
        weak_or_clutter_switches=1,
    )


def test_driver_matched_layout_failure_and_resume(monkeypatch, tmp_path):
    member = dict(inventory_label="synthetic", dataset="DS16")
    fit = dict(
        converged=True, stage="B7", vector=[0.0] * 9, clock_coefficients=[0.0, 0.0], objective=1.0
    )
    archive = dict(status="complete", member=member, stages=dict(B7={a: fit for a in audit.ARMS}))
    source = tmp_path / "archive.json"
    source.write_text(json.dumps(archive))
    binding = dict(member=member, b7_source=str(source), loader_binding=dict(kind="synthetic"))
    obs = SimpleNamespace(
        times_s=np.array([0.0, 1.0]),
        receiver=np.zeros(2),
        channel=np.ones(2),
        rf_hz=np.full(2, 1e10),
    )
    monkeypatch.setattr(audit, "HERE", tmp_path)
    monkeypatch.setattr(
        audit, "reconstruct", lambda *_: (SimpleNamespace(observations=obs), ((0, 1),))
    )
    layouts = []

    def arm(*args):
        layouts.append(args[-1])
        return dict(objective_delta=0.0)

    monkeypatch.setattr(audit, "audit_arm", arm)
    audit.evaluate(binding, "digest")
    assert len(layouts) == 2 and layouts[0] is layouts[1]
    result = json.loads((tmp_path / "results/synthetic.json").read_text())
    assert result["status"] == "complete"
    audit.evaluate(binding, "digest")
    assert len(layouts) == 2
    with pytest.raises(AssertionError):
        audit.evaluate(binding, "stale")


def test_reconstruction_failure_preserved(monkeypatch, tmp_path):
    member = dict(inventory_label="synthetic")
    source = tmp_path / "archive.json"
    source.write_text(json.dumps(dict(status="complete", member=member)))
    binding = dict(member=member, b7_source=str(source), loader_binding=dict(kind="synthetic"))
    monkeypatch.setattr(audit, "HERE", tmp_path)

    def fail(*_):
        raise ValueError("synthetic invalid input")

    monkeypatch.setattr(audit, "reconstruct", fail)
    audit.evaluate(binding, "digest")
    assert json.loads((tmp_path / "results/synthetic.json").read_text())["status"] == "failed"


def test_nonzero_all_priors_required_for_whole_score(monkeypatch):
    from leo.analysis.hard60_score import likelihood
    from leo.application.hard60_runner import HARD60_SCORE

    y = np.array([10.0, 30.0])
    prediction = np.array([[0.0, 50.0, 100.0], [20.0, 40.0, 120.0]])
    visible = np.ones_like(prediction, bool)
    terms = likelihood(y, prediction, visible, HARD60_SCORE)
    vector, clock = np.zeros(9), np.array([1.0, 2.0])
    vector[7:] = [0.3, 0.2]
    basis = np.array([[-1.0], [0.0], [1.0]])
    prior = 0.5 * (0.3 / HARD60_SCORE.common_sigma_s) ** 2
    prior += 0.5 * np.sum((basis[:, 0] * 0.2 / HARD60_SCORE.relative_sigma_s) ** 2)
    prior += 0.5 * clock @ clock
    model = SimpleNamespace(
        observations=SimpleNamespace(measured_hz=y),
        score=HARD60_SCORE,
        basis=basis,
        precision=np.eye(2),
        bank=SimpleNamespace(numbers=np.arange(3) + 1),
        evaluate_joint=lambda *_: (terms.nll + prior, None, None, terms),
    )
    monkeypatch.setattr(audit, "predictions", lambda *_: (prediction, visible))
    layout = dict(
        permutation=np.arange(2),
        inverse_permutation=np.arange(2),
        reset=np.array([True, False]),
        segments=((0, 1),),
    )
    result = audit.audit_arm(model, vector, clock, terms.nll + prior, layout)
    assert abs(result["rho0_whole_score_delta"]) < 1e-12
    model.evaluate_joint = lambda *_: (terms.nll, None, None, terms)
    with pytest.raises(AssertionError):
        audit.audit_arm(model, vector, clock, terms.nll, layout)


def test_prediction_composition_keeps_all_components(monkeypatch):
    orbit = np.arange(12, dtype=float).reshape(4, 3)
    visible = np.ones((4, 3), bool)
    monkeypatch.setattr(audit, "predict_orbits", lambda *_: (orbit.copy(), visible, None, None))
    model = SimpleNamespace(
        basis=np.zeros((3, 1)),
        bank=None,
        observations=None,
        prior=None,
        design=np.ones((4, 5)),
        baseline=np.arange(4),
        clock_design=np.ones((4, 2)) * 2,
        delta_time=np.ones((4, 3)) * 0.5,
        physical_corrections=lambda _: (np.array([1.0, 2.0, 3.0]), np.array([0.1, 0.2, 0.3])),
    )
    vector, clock = np.arange(9, dtype=float), np.array([1.0, 2.0])
    prediction, mask = audit.predictions(model, vector, clock)
    expected = orbit + (np.sum(vector[2:7]) + np.arange(4) + 6)[:, None]
    expected += np.array([1.0, 2.0, 3.0])[None, :] + 50 * np.array([0.1, 0.2, 0.3])[None, :]
    np.testing.assert_array_equal(prediction, expected)
    assert mask is visible
