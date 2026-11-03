from __future__ import annotations

from types import SimpleNamespace

import finite_set_reset_multistart as model
import numpy as np
import pytest


def synthetic_data(candidate_count=2):
    return SimpleNamespace(
        times=np.arange(4.0),
        measured=np.zeros(4),
        group=np.arange(4),
        receiver=np.array([0, 1, 0, 1]),
        rf=np.full(4, 11.2e9),
        numbers=np.arange(candidate_count),
        capture_index=np.array([0, 0, 1, 1]),
        child_sessions=("capture-a", "capture-b"),
        child_origins_utc_ns=np.array([1_000_000_000, 5_000_000_000], dtype=np.int64),
        origin_utc_ns=1_000_000_000,
        reference_time_s=2.0,
    )


def child_receipts():
    return {
        "capture-a": {
            "unit": {"size": 1, "session_ids": ["capture-a"]},
            "fit": {
                "rough": {"position_km": [-10.0, 20.0]},
                "rx_initial": [-10.0, 20.0, 100.0, 2.0, 200.0, 4.0],
            },
        },
        "capture-b": {
            "unit": {"size": 1, "session_ids": ["capture-b"]},
            "fit": {
                "rough": {"position_km": [-6.0, 24.0]},
                "rx_initial": [-6.0, 24.0, 300.0, 6.0, 500.0, 8.0],
            },
        },
    }


def parent_trial(data, objective=100.0):
    parameters = np.zeros(6 + len(data.numbers))
    parameters[:2] = [-80.0, -90.0]
    satellites = np.arange(len(data.numbers))
    return {
        "satellite_indices": satellites,
        "catalog_numbers": np.arange(len(satellites)) + 100,
        "satellite_count": len(satellites),
        "parameters": parameters,
        "objective": objective,
        "selection_score": objective + 1.0,
        "success": True,
        "status": "converged",
    }


def test_full_child_seed_uses_median_position_rx_jumps_and_zero_taus():
    data = synthetic_data(candidate_count=3)
    seed = model.full_child_seed(data, child_receipts())
    np.testing.assert_allclose(seed["parameters"][:2], [-8.0, 22.0])
    np.testing.assert_array_equal(seed["parameters"][6:], np.zeros(3))
    np.testing.assert_array_equal(seed["capture_jumps_hz"][0], np.zeros(2))
    assert seed["position_source"] == "sealed_child_rough_coordinate_median"
    assert seed["tau_source"] == "zero_fresh_union_bank"


def test_two_independent_refinements_and_lowest_objective_are_selected(monkeypatch):
    data = synthetic_data()
    source = parent_trial(data)
    parent = {"full_bank": source["satellite_indices"], "trials": [source]}
    calls = []

    monkeypatch.setattr(
        model,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": object()},
    )

    def fake_geometry(data):
        return {"capture_count": 2, "group_count": 4}

    def fake_rx(data, parameters, receipts):
        del data, receipts
        changed = np.asarray(parameters).copy()
        changed[2] = 1.0
        return {
            "parameters": changed,
            "capture_jumps_hz": np.array([[0.0, 0.0], [1.0, 1.0]]),
        }

    def fake_fresh(data, receipts):
        del receipts
        parameters = np.zeros(6 + len(data.numbers))
        parameters[:2] = [10.0, 20.0]
        return {
            "parameters": parameters,
            "capture_jumps_hz": np.array([[0.0, 0.0], [2.0, 2.0]]),
            "policy": "fresh",
        }

    def fake_evaluate(data, parameters, jumps, satellites, likelihood):
        del data, satellites, likelihood
        if np.allclose(parameters[:2], [-80.0, -90.0]) and np.allclose(jumps, 0):
            objective = 100.0
        elif np.allclose(parameters[:2], [-80.0, -90.0]):
            objective = 90.0
        else:
            objective = 80.0
        return {"objective": objective, "group_count": 4, "capture_jumps_hz": jumps}

    def fake_refiner(data, parameters, jumps, satellites, support, likelihood, **options):
        del data, support, likelihood
        calls.append((np.asarray(parameters).copy(), np.asarray(jumps).copy(), options))
        initial = 90.0 if np.allclose(parameters[:2], [-80.0, -90.0]) else 80.0
        objective = 85.0 if initial == 90.0 else 70.0
        penalty = model.capture_reset_model_penalty(4, len(satellites), 2)
        return {
            "parameters": np.asarray(parameters).copy(),
            "capture_jumps_hz": np.asarray(jumps).copy(),
            "satellite_indices": np.asarray(satellites).copy(),
            "satellite_count": len(satellites),
            "objective": objective,
            "initial_objective": initial,
            "selection_score": objective + penalty["total_penalty"],
            "model_penalty": penalty,
            "success": True,
            "status": "converged",
        }

    monkeypatch.setattr(model, "validate_group_capture_rx", fake_geometry)
    result = model.fit_reset_multistart_branches(
        data,
        parent,
        child_receipts(),
        refiner=fake_refiner,
        seed_evaluator=fake_evaluate,
        rx_initializer=fake_rx,
        fresh_initializer=fake_fresh,
    )
    assert len(calls) == 2
    assert all(call[2]["budget_s"] == 15.0 for call in calls)
    assert result["attempts"][0]["baseline_seed_selected"] == "parent_rx_child"
    assert result["trials"][0]["selected_multistart_branch"] == "fresh_child_refinement"
    assert result["trials"][0]["objective"] == 70.0
    assert result["selection"]["selection_resolved"] is True


def test_incomplete_unselected_branch_makes_selection_unresolved(monkeypatch):
    data = synthetic_data(candidate_count=1)
    source = parent_trial(data)
    parent = {"full_bank": source["satellite_indices"], "trials": [source]}
    monkeypatch.setattr(
        model,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": object()},
    )
    monkeypatch.setattr(
        model,
        "validate_group_capture_rx",
        lambda data: {"capture_count": 2, "group_count": 4},
    )

    def initializer(data, receipts):
        del receipts
        parameters = np.zeros(6 + len(data.numbers))
        return {
            "parameters": parameters,
            "capture_jumps_hz": np.zeros((2, 2)),
            "policy": "fresh",
        }

    def rx_initializer(data, parameters, receipts):
        del data, receipts
        return {
            "parameters": np.asarray(parameters).copy(),
            "capture_jumps_hz": np.ones((2, 2)) * np.array([[0.0], [1.0]]),
        }

    def evaluate(data, parameters, jumps, satellites, likelihood):
        del data, parameters, satellites, likelihood
        objective = 100.0 if np.allclose(jumps, 0) else 90.0
        return {"objective": objective, "group_count": 4, "capture_jumps_hz": jumps}

    count = 0

    def refiner(data, parameters, jumps, satellites, support, likelihood, **options):
        nonlocal count
        del data, support, likelihood, options
        count += 1
        initial = 90.0 if count == 1 else 100.0
        objective = 80.0 if count == 1 else 85.0
        penalty = model.capture_reset_model_penalty(4, len(satellites), 2)
        return {
            "parameters": np.asarray(parameters).copy(),
            "capture_jumps_hz": np.asarray(jumps).copy(),
            "satellite_indices": np.asarray(satellites).copy(),
            "satellite_count": len(satellites),
            "objective": objective,
            "initial_objective": initial,
            "selection_score": objective + penalty["total_penalty"],
            "model_penalty": penalty,
            "success": count == 1,
            "status": "converged" if count == 1 else "nonconverged",
        }

    result = model.fit_reset_multistart_branches(
        data,
        parent,
        child_receipts(),
        refiner=refiner,
        seed_evaluator=evaluate,
        rx_initializer=rx_initializer,
        fresh_initializer=initializer,
    )
    assert result["trials"][0]["success"] is True
    assert result["all_refinement_branches_complete"] is False
    assert result["selection"]["selection_resolved"] is False


def test_nested_objective_mismatch_is_blocking(monkeypatch):
    data = synthetic_data(candidate_count=1)
    source = parent_trial(data)
    parent = {"full_bank": source["satellite_indices"], "trials": [source]}
    monkeypatch.setattr(
        model,
        "build_likelihood_arms",
        lambda *args, **kwargs: {"finite_set": object()},
    )
    monkeypatch.setattr(
        model,
        "validate_group_capture_rx",
        lambda data: {"capture_count": 2, "group_count": 4},
    )
    with pytest.raises(ValueError, match="does not reproduce continuous parent"):
        model.fit_reset_multistart_branches(
            data,
            parent,
            child_receipts(),
            seed_evaluator=lambda *args: {
                "objective": 101.0,
                "group_count": 4,
                "capture_jumps_hz": np.zeros((2, 2)),
            },
        )


def test_scope_and_dependency_contract_are_bounded():
    assert model.SUPPORTED_UNITS == ("DS10-D08", "DS11-D08")
    names = {path.name for path in model.runner_numerical_dependency_paths()}
    assert {"capture_reset_fit.py", "capture_reset_gn.py", "coherent_fit.py"} <= names
    assert model.NEW_DEPENDENCIES == (
        "finite_set_capture_reset.py",
        "finite_set_fit.py",
        "finite_set_likelihood.py",
        "prediction_plan.py",
        "prediction_jacobian.py",
        "joint_inputs.py",
        "staged_fit.py",
        "rough_smoke.py",
        "alias_family_joint.py",
    )
