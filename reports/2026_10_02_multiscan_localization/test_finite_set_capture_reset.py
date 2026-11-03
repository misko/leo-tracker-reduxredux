import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest
from capture_reset_fit import capture_reset_gradient, capture_reset_model_penalty
from finite_set_capture_reset import (
    audit_parent_source_hashes,
    child_rx_only_seed,
    evaluate_reset_seed,
    fit_capture_reset_branches,
    runner_numerical_dependency_paths,
    validate_child_rough_provenance,
    validate_group_capture_rx,
    validate_parent_binding,
)
from finite_set_fit import build_likelihood_arms


def _data():
    return SimpleNamespace(
        times=np.array([0.0, 0.0, 10.0, 10.0]),
        measured=np.array([100.0, 180.0, -50.0, 30.0]),
        group=np.array([0, 0, 1, 1]),
        rf=np.full(4, 11.0e9),
        receiver=np.array([0, 0, 1, 1]),
        channel=np.zeros(4, dtype=int),
        capture_index=np.array([0, 0, 1, 1]),
        child_sessions=("first", "second"),
        child_origins_utc_ns=np.array([1_000_000_000, 101_000_000_000]),
        origin_utc_ns=1_000_000_000,
        reference_time_s=50.0,
        numbers=np.array([1001]),
    )


def _child_receipts():
    def receipt(session, position, rx):
        return {
            "unit": {"unit_id": session, "size": 1, "session_ids": [session]},
            "fit": {
                "rough": {"position_km": position},
                "rx_initial": [*position, *rx, 0.0],
            },
        }

    return {
        "first": receipt("first", [1.0, 2.0], [300.0, 4.0, 500.0, 6.0]),
        "second": receipt("second", [9.0, 8.0], [800.0, 8.0, 900.0, 10.0]),
    }


def test_group_capture_receiver_contract_rejects_cross_capture_group():
    data = _data()
    assert validate_group_capture_rx(data)["capture_count"] == 2
    changed = copy.copy(data)
    changed.capture_index = np.array([0, 1, 1, 1])
    with pytest.raises(ValueError, match="crosses capture"):
        validate_group_capture_rx(changed)


def test_child_initializer_preserves_parent_position_and_all_taus():
    data = _data()
    parent = np.array([7.0, -3.0, 10.0, 1.0, 20.0, 2.0, -0.75])
    seeded = child_rx_only_seed(data, parent, _child_receipts())
    np.testing.assert_array_equal(seeded["parameters"][:2], parent[:2])
    np.testing.assert_array_equal(seeded["parameters"][6:], parent[6:])
    assert seeded["position_and_tau_preserved"]
    np.testing.assert_array_equal(seeded["capture_jumps_hz"][0], [0.0, 0.0])


def test_finite_set_gradient_matches_capture_reset_indicator_difference():
    data = _data()
    likelihood = build_likelihood_arms(data, 1, 1)["finite_set"]
    base = np.zeros((len(data.times), 1))
    visible = np.ones_like(base, dtype=bool)
    result = likelihood.evaluate(
        base,
        visible,
        sigma_hz=200.0,
        satellite_weights=np.ones(1),
        background_mass=0.2,
        return_gradient=True,
    )
    rows = np.arange(len(data.times))
    analytic = -capture_reset_gradient(data, rows, result["prediction_gradient"][:, 0])

    def objective(delta):
        predicted = base.copy()
        predicted[data.capture_index == 1, 0] += delta
        value = likelihood.evaluate(
            predicted,
            visible,
            sigma_hz=200.0,
            satellite_weights=np.ones(1),
            background_mass=0.2,
        )
        return -value["total_log_likelihood"]

    step = 1e-3
    numerical = (objective(step) - objective(-step)) / (2 * step)
    assert analytic[1, 1] == pytest.approx(numerical, rel=2e-5, abs=2e-7)


def test_zero_reset_objective_and_same_bank_initializer_routing(monkeypatch):
    import finite_set_capture_reset as module

    class PredictionPlan:
        def __init__(self, data, satellites):
            self.data = data
            self.satellites = np.asarray(satellites, dtype=int)

        def predict(self, parameters):
            receiver = np.asarray(self.data.receiver)
            values = parameters[2 + 2 * receiver] + parameters[3 + 2 * receiver] * (
                self.data.times - self.data.reference_time_s
            )
            predicted = np.repeat(values[:, None], len(self.satellites), axis=1)
            return predicted.ravel(), np.ones(predicted.size, dtype=bool), None

    monkeypatch.setattr(module, "SharedPredictionPlan", PredictionPlan)
    data = _data()
    parent_parameters = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.25])
    likelihood = build_likelihood_arms(data, 1, 1)["finite_set"]
    nested = evaluate_reset_seed(
        data,
        parent_parameters,
        np.zeros((2, 2)),
        np.array([0]),
        likelihood,
    )
    source_trial = {
        "parameters": parent_parameters,
        "satellite_indices": [0],
        "catalog_numbers": [1001],
        "objective": nested["objective"],
        "success": True,
        "seed": {"track_support": [10.0]},
    }
    calls = []

    def refiner(data_arg, parameters, jumps, satellites, support, prepared, **options):
        selected = evaluate_reset_seed(data_arg, parameters, jumps, satellites, prepared)
        calls.append((parameters.copy(), jumps.copy(), options))
        penalty = capture_reset_model_penalty(selected["group_count"], 1, 2)
        return {
            "parameters": parameters.copy(),
            "capture_jumps_hz": jumps.copy(),
            "success": True,
            "status": "converged",
            "convergence_reason": "test",
            "satellite_indices": satellites.copy(),
            "catalog_numbers": np.array([1001]),
            "objective": selected["objective"],
            "initial_objective": selected["objective"],
            "selection_score": selected["objective"] + penalty["total_penalty"],
            "model_penalty": penalty,
        }

    fitted = fit_capture_reset_branches(
        data,
        {"full_bank": [0], "trials": [source_trial]},
        _child_receipts(),
        refiner=refiner,
    )
    assert len(calls) == 1
    assert calls[0][2]["sigma_hz"] == 200.0
    assert calls[0][2]["tau_sigma_s"] == 1.0
    assert calls[0][2]["tau_bound_s"] == 3.0
    assert calls[0][2]["slope_bound_hz_s"] == 50.0
    assert fitted["parent_bank_order_preserved"]
    assert fitted["trials"][0]["objective"] <= nested["objective"] + 1e-6
    attempt = fitted["attempts"][0]
    expected_seed = (
        "child_rx_only"
        if attempt["child_rx_only"]["objective"] < attempt["nested_zero_reset"]["objective"]
        else "nested_zero_reset"
    )
    assert attempt["selected_initializer"] == expected_seed


def test_worse_reset_candidate_retains_continuous_point_with_honest_status(monkeypatch):
    import finite_set_capture_reset as module

    class PredictionPlan:
        def __init__(self, data, satellites):
            self.data = data
            self.satellites = satellites

        def predict(self, parameters):
            predicted = np.zeros((len(self.data.times), len(self.satellites)))
            return predicted.ravel(), np.ones(predicted.size, dtype=bool), None

    monkeypatch.setattr(module, "SharedPredictionPlan", PredictionPlan)
    data = _data()
    parameters = np.zeros(7)
    likelihood = build_likelihood_arms(data, 1, 1)["finite_set"]
    nested = evaluate_reset_seed(data, parameters, np.zeros((2, 2)), [0], likelihood)
    source = {
        "parameters": parameters,
        "satellite_indices": [0],
        "catalog_numbers": [1001],
        "objective": nested["objective"],
        "success": True,
        "seed": {"track_support": [1.0]},
    }

    def refiner(*args, **kwargs):
        return {
            "initial_objective": min(
                evaluate_reset_seed(data, parameters, np.zeros((2, 2)), [0], args[5])["objective"],
                nested["objective"],
            ),
            "objective": nested["objective"] + 1.0,
        }

    fitted = fit_capture_reset_branches(
        data,
        {"full_bank": [0], "trials": [source]},
        _child_receipts(),
        refiner=refiner,
    )
    trial = fitted["trials"][0]
    assert not trial["success"]
    assert trial["continuous_incumbent_retained"]
    assert trial["convergence_not_inherited_from_continuous_model"]
    expected = capture_reset_model_penalty(2, 1, 2)["total_penalty"]
    assert trial["selection_score"] == pytest.approx(nested["objective"] + expected)


def test_reset_penalty_adds_two_parameters_per_later_capture():
    pair = capture_reset_model_penalty(100, 8, 2)
    quad = capture_reset_model_penalty(100, 8, 4)
    assert pair["extra_parameter_count"] == 2
    assert quad["extra_parameter_count"] == 6
    assert quad["total_penalty"] - pair["total_penalty"] == pytest.approx(2 * np.log(100))


def test_child_cached_rough_provenance_mismatch_is_rejected(tmp_path, monkeypatch):
    root = tmp_path
    monkeypatch.setattr("finite_set_capture_reset.ROOT", root)
    (root / "runs" / "rough-v1" / "S01").mkdir(parents=True)
    (root / "scans" / "session").mkdir(parents=True)
    (root / "selection.json").write_text("selection")
    (root / "track_seed.py").write_text("solver")
    bundle = root / "scans" / "session" / "bundle.json"
    bundle.write_text("bundle")
    single = {"unit_id": "S01", "size": 1, "session_ids": ["session"]}
    rough = {"position_km": [1.0, 2.0], "success": True}
    cached = {
        "stage": "rough",
        "unit": single,
        "dataset": "DS10",
        "inputs": {"session": "wrong"},
        "selection_sha256": "wrong",
        "source_hashes": {"track_seed.py": "wrong"},
        "fit": rough,
    }
    cached_path = root / "runs" / "rough-v1" / "S01" / "fit.json"
    cached_path.write_text(json.dumps(cached))
    import finite_set_capture_reset as module

    receipt = {
        "run_id": "coherent-v1",
        "stage": "coherent",
        "unit": single,
        "dataset": "DS10",
        "selection_sha256": module.digest(root / "selection.json"),
        "inputs": {"session": module.digest(bundle)},
        "source_hashes": {"track_seed.py": module.digest(root / "track_seed.py")},
        "cached_rough_fit_sha256": module.digest(cached_path),
        "fit": {"rough": rough, "rx_initial": [1, 2, 3, 4, 5, 6]},
    }
    with pytest.raises(ValueError, match="cached child rough fit"):
        validate_child_rough_provenance(receipt, tmp_path / "child.json", single, "DS10")


def test_parent_binding_detects_geometry_and_inherited_hash_changes(tmp_path, monkeypatch):
    import finite_set_capture_reset as module

    monkeypatch.setattr(module, "ROOT", tmp_path)
    selection = tmp_path / "selection.json"
    input_path = tmp_path / "input.json"
    selection.write_text("selection")
    input_path.write_text("input")
    unit = {"unit_id": "DS10-D01", "size": 2, "session_ids": ["a", "b"]}
    data = SimpleNamespace(
        child_sessions=("a", "b"),
        times=np.arange(3.0),
        geometry_receipt={"fitted_array_sha256": {"capture_index": "abc"}},
    )
    source_hashes = {str(input_path.resolve()): module.digest(input_path)}
    parent = {
        "schema": "finite-set-grouped-cohort/v1",
        "run_id": "finite-set-grouped-cohort-v1",
        "unit": unit,
        "dataset": "DS10",
        "reference_read_before_seal": False,
        "evaluation_written": False,
        "sealed_utc": "2026-10-02T00:00:00+00:00",
        "selection_sha256": module.digest(selection),
        "source_hashes": source_hashes,
        "grouped_row_count": 3,
        "fit": {"capture_count": 2, "grouped_geometry": data.geometry_receipt},
    }
    validate_parent_binding(parent, unit, "DS10", data, [input_path])

    changed = copy.deepcopy(parent)
    changed["fit"]["grouped_geometry"] = {"different": True}
    with pytest.raises(ValueError, match="grouped geometry differs"):
        validate_parent_binding(changed, unit, "DS10", data, [input_path])

    input_path.write_text("changed")
    with pytest.raises(RuntimeError, match="parent numerical provenance changed"):
        validate_parent_binding(parent, unit, "DS10", data, [input_path])


def test_parent_source_audit_allows_only_unused_runner_drift(tmp_path, monkeypatch):
    allowed = tmp_path / "finite_set_grouped_cohort.py"
    blocked = tmp_path / "finite_set_likelihood.py"
    allowed.write_text("old")
    blocked.write_text("stable")
    import finite_set_capture_reset as module

    monkeypatch.setattr(module, "ROOT", tmp_path)
    hashes = {str(allowed): module.digest(allowed), str(blocked): module.digest(blocked)}
    allowed.write_text("new")
    rows = audit_parent_source_hashes(hashes)
    assert rows[0]["allowed_orchestration_drift"]
    assert rows[0]["drift_exception"] == "legacy_parent_orchestration_not_reused"
    assert rows[0]["expected_sha256"] == hashes[str(allowed)]
    assert rows[0]["current_sha256"] == module.digest(allowed)
    assert not rows[0]["reused_by_new_numerical_fit"]

    blocked.write_text("changed")
    with pytest.raises(RuntimeError, match="parent numerical provenance changed"):
        audit_parent_source_hashes(hashes)

    duplicate_name = tmp_path / "other" / "finite_set_grouped_cohort.py"
    duplicate_name.parent.mkdir()
    duplicate_name.write_text("old")
    duplicate_hashes = {str(duplicate_name): module.digest(duplicate_name)}
    duplicate_name.write_text("new")
    with pytest.raises(RuntimeError, match="parent numerical provenance changed"):
        audit_parent_source_hashes(duplicate_hashes)


def test_runner_dependency_list_binds_coherent_fit_and_reset_imports():
    paths = runner_numerical_dependency_paths()
    assert tuple(path.name for path in paths) == (
        "capture_reset_fit.py",
        "capture_reset_gn.py",
        "coherent_fit.py",
    )
    assert all(path.is_file() for path in paths)
