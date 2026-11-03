from types import SimpleNamespace

import finite_set_satellite_bias as model
import numpy as np
import pytest
from finite_set_likelihood import DEFAULT_ALIAS_HZ


class DenseJacobian:
    def __init__(self, matrix):
        self.matrix = np.asarray(matrix, dtype=float)

    def transpose_multiply(self, weights):
        return self.matrix.T @ np.asarray(weights, dtype=float)


class LinearPlan:
    def __init__(self, matrix, data, satellites, visible=None):
        self.matrix = np.asarray(matrix, dtype=float)
        self.data = data
        self.satellites = np.asarray(satellites, dtype=int)
        shape = (len(data.times), len(satellites))
        self.visible = np.ones(shape, dtype=bool) if visible is None else np.asarray(visible)

    def predict(self, parameters):
        predicted = self.matrix @ np.asarray(parameters, dtype=float)
        return predicted, self.visible.ravel(), DenseJacobian(self.matrix)


class QuadraticLikelihood:
    def __init__(self, target, masses):
        self.target = np.asarray(target, dtype=float)
        self.frozen_masses = masses
        self.last_result = None

    def evaluate(self, predicted, visible, **options):
        residual = np.asarray(predicted) - self.target
        self.last_result = {
            "total_log_likelihood": -0.5 * float(np.sum(residual**2)),
            "prediction_gradient": -residual,
            "group_values": np.arange(len(predicted)),
            "satellite_support": np.ones(predicted.shape[1]),
            "null_support": 0.0,
            "conditioned_nonempty": True,
            "density_convention": "synthetic",
            "expected_clutter_count": np.zeros(len(predicted)),
            "raw_peak_count": np.ones(len(predicted), dtype=int),
            "unique_peak_count": np.ones(len(predicted), dtype=int),
        }
        return self.last_result


class CircularLikelihood(QuadraticLikelihood):
    def evaluate(self, predicted, visible, **options):
        residual = (np.asarray(predicted) - self.target + DEFAULT_ALIAS_HZ / 2) % (
            DEFAULT_ALIAS_HZ
        ) - DEFAULT_ALIAS_HZ / 2
        self.last_result = {
            "total_log_likelihood": -0.5 * float(np.sum(residual**2)),
            "prediction_gradient": -residual,
            "group_values": np.arange(len(predicted)),
            "satellite_support": np.ones(predicted.shape[1]),
            "null_support": 0.0,
        }
        return self.last_result


def synthetic_data(candidate_count=3):
    return SimpleNamespace(
        times=np.array([0.0, 0.0, 1.0, 1.0]),
        measured=np.zeros(4),
        rf=np.full(4, 11.2e9),
        receiver=np.array([0, 1, 0, 1]),
        channel=np.array([1, 2, 2, 1]),
        group=np.arange(4),
        numbers=np.arange(candidate_count),
    )


def test_gradient_including_omega_and_zero_state_matches_baseline():
    rng = np.random.default_rng(94)
    data = synthetic_data()
    satellites = np.array([0, 2])
    full_size = 6 + len(data.numbers)
    matrix = rng.normal(size=(len(data.times) * len(satellites), full_size))
    source_parameters = rng.normal(size=full_size)
    source_parameters[6:] = np.array([0.2, -0.1, 0.3])
    specification = model._trial_specification(data, source_parameters, satellites)
    target = rng.normal(size=(len(data.times), len(satellites)))
    likelihood = QuadraticLikelihood(target, model.frozen_raw_masses(2, 3))
    plan = LinearPlan(matrix, data, satellites)

    state = model.evaluate_bias_state(
        specification["vector"],
        data=data,
        specification=specification,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
    )
    baseline_prediction = (matrix @ source_parameters).reshape(target.shape)
    baseline = 0.5 * np.sum((baseline_prediction - target) ** 2)
    baseline += 0.5 * np.sum(source_parameters[6 + satellites] ** 2)
    assert state.objective == pytest.approx(baseline, abs=1e-10)
    assert np.array_equal(state.omega_hz, np.zeros(2))

    candidate = specification["vector"].copy()
    candidate[-2:] = [0.35, -0.2]
    analytic = model.evaluate_bias_state(
        candidate,
        data=data,
        specification=specification,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
    ).gradient
    finite = np.empty_like(candidate)
    step = 1e-6
    for index in range(len(candidate)):
        delta = np.zeros_like(candidate)
        delta[index] = step
        upper = model.evaluate_bias_state(
            candidate + delta,
            data=data,
            specification=specification,
            satellites=satellites,
            likelihood=likelihood,
            plan=plan,
        ).objective
        lower = model.evaluate_bias_state(
            candidate - delta,
            data=data,
            specification=specification,
            satellites=satellites,
            likelihood=likelihood,
            plan=plan,
        ).objective
        finite[index] = (upper - lower) / (2 * step)
    np.testing.assert_allclose(analytic, finite, rtol=2e-6, atol=3e-5)


def test_alias_shift_preserves_likelihood_but_proper_prior_selects_nearest_alias():
    data = synthetic_data(candidate_count=1)
    satellites = np.array([0])
    parameters = np.zeros(7)
    specification = model._trial_specification(data, parameters, satellites)
    matrix = np.zeros((len(data.times), 7))
    plan = LinearPlan(matrix, data, satellites)
    likelihood = CircularLikelihood(np.zeros((len(data.times), 1)), model.frozen_raw_masses(1, 1))
    zero = model.evaluate_bias_state(
        specification["vector"],
        data=data,
        specification=specification,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
    )
    shifted_vector = specification["vector"].copy()
    shifted_vector[-1] = DEFAULT_ALIAS_HZ / model.OMEGA_SIGMA_HZ
    shifted = model.evaluate_bias_state(
        shifted_vector,
        data=data,
        specification=specification,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
    )
    assert shifted.likelihood["total_log_likelihood"] == pytest.approx(
        zero.likelihood["total_log_likelihood"], abs=1e-12
    )
    assert shifted.objective - zero.objective == pytest.approx(shifted.omega_prior)


def test_common_omega_rx_intercept_gauge_is_resolved_only_by_prior():
    data = synthetic_data(candidate_count=2)
    satellites = np.array([0, 1])
    parameters = np.zeros(8)
    specification = model._trial_specification(data, parameters, satellites)
    matrix = np.zeros((len(data.times) * 2, len(parameters)))
    for row, receiver in enumerate(data.receiver):
        for column in range(2):
            matrix[row * 2 + column, 2 + 2 * receiver] = 1.0
    plan = LinearPlan(matrix, data, satellites)
    likelihood = QuadraticLikelihood(np.zeros((len(data.times), 2)), model.frozen_raw_masses(2, 2))
    base = specification["vector"].copy()
    shift_hz = 40.0
    shifted = base.copy()
    shifted[2] -= shift_hz / specification["physical_scales"][2]
    shifted[4] -= shift_hz / specification["physical_scales"][4]
    shifted[-2:] += shift_hz / model.OMEGA_SIGMA_HZ
    base_state = model.evaluate_bias_state(
        base,
        data=data,
        specification=specification,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
    )
    shifted_state = model.evaluate_bias_state(
        shifted,
        data=data,
        specification=specification,
        satellites=satellites,
        likelihood=likelihood,
        plan=plan,
    )
    assert shifted_state.likelihood["total_log_likelihood"] == pytest.approx(
        base_state.likelihood["total_log_likelihood"], abs=1e-12
    )
    assert shifted_state.objective - base_state.objective == pytest.approx(
        len(satellites) * 0.5 * (shift_hz / model.OMEGA_SIGMA_HZ) ** 2
    )


def test_topology_requires_connected_receiver_satellite_support():
    data = synthetic_data(candidate_count=2)
    satellites = np.array([0, 1])
    connected = np.array([[True, False], [True, True], [False, True], [True, False]], dtype=bool)
    receipt = model.receiver_satellite_topology(data, satellites, connected)
    assert receipt["connected"] is True
    assert receipt["component_count"] == 1
    assert receipt["likelihood_identifiable_omega_contrasts"] == 1

    disconnected = np.array(
        [[True, False], [False, True], [True, False], [False, True]], dtype=bool
    )
    with pytest.raises(ValueError, match="disconnected"):
        model.receiver_satellite_topology(data, satellites, disconnected)
    receipt = model.receiver_satellite_topology(
        data, satellites, disconnected, require_connected=False
    )
    assert receipt["connected"] is False
    assert receipt["component_count"] == 2


def test_visibility_change_retains_connected_incumbent_and_marks_terminal_invalid():
    data = synthetic_data(candidate_count=2)
    satellites = np.array([0, 1])
    parameters = np.zeros(8)
    masses = model.frozen_raw_masses(2, 2)
    likelihood = QuadraticLikelihood(np.ones((len(data.times), 2)), masses)
    connected = np.ones((len(data.times), 2), dtype=bool)
    disconnected = np.array(
        [[True, False], [False, True], [True, False], [False, True]], dtype=bool
    )

    class VisibilityChangingPlan:
        def __init__(self, source, selected):
            self.source = source
            self.selected = selected
            self.matrix = np.zeros((len(source.times) * len(selected), len(parameters)))
            self.matrix[:, 0] = 1.0

        def predict(self, current):
            current = np.asarray(current, dtype=float)
            predicted = self.matrix @ current
            visible = connected if current[0] == 0 else disconnected
            return predicted, visible.ravel(), DenseJacobian(self.matrix)

    def disconnected_minimizer(evaluate, initial, bounds):
        candidate = np.asarray(initial).copy()
        candidate[0] = 0.05
        evaluate(candidate)
        return SimpleNamespace(
            success=True,
            message="synthetic disconnected optimum",
            status=0,
            nit=1,
            x=candidate,
        )

    trial = model.fit_satellite_bias_trial(
        data,
        {"satellite_indices": satellites, "parameters": parameters},
        likelihood,
        budget_s=1.0,
        minimizer=disconnected_minimizer,
        plan_factory=VisibilityChangingPlan,
    )
    assert trial["success"] is False
    assert trial["status"] == "nonconverged"
    assert trial["message"].startswith("optimizer_terminal_topology_disconnected")
    assert trial["initial_topology"]["connected"] is True
    assert trial["final_topology"]["connected"] is True
    assert trial["optimizer_terminal_topology"]["connected"] is False
    assert trial["optimizer_terminal_matches_retained"] is False
    assert trial["disconnected_topology_evaluation_count"] == 1
    assert trial["omega_identifiable_parameter_count"] == 1
    assert trial["parameters"][0] == 0.0


def test_connected_terminal_must_match_retained_incumbent_for_convergence():
    data = synthetic_data(candidate_count=2)
    satellites = np.array([0, 1])
    parameters = np.zeros(8)
    target = np.full((len(data.times), 2), 20.0)
    likelihood = QuadraticLikelihood(target, model.frozen_raw_masses(2, 2))
    connected = np.ones((len(data.times), 2), dtype=bool)

    class ConnectedPlan:
        def __init__(self, source, selected):
            self.matrix = np.zeros((len(source.times) * len(selected), len(parameters)))
            self.matrix[:, 0] = 1.0

        def predict(self, current):
            predicted = self.matrix @ np.asarray(current, dtype=float)
            return predicted, connected.ravel(), DenseJacobian(self.matrix)

    def mismatched_minimizer(evaluate, initial, bounds):
        retained = np.asarray(initial).copy()
        retained[0] = 1.0
        evaluate(retained)
        terminal = np.asarray(initial).copy()
        terminal[0] = 0.5
        evaluate(terminal)
        return SimpleNamespace(
            success=True,
            message="synthetic connected terminal",
            status=0,
            nit=2,
            x=terminal,
        )

    trial = model.fit_satellite_bias_trial(
        data,
        {"satellite_indices": satellites, "parameters": parameters},
        likelihood,
        budget_s=1.0,
        minimizer=mismatched_minimizer,
        plan_factory=ConnectedPlan,
    )
    assert trial["success"] is False
    assert trial["status"] == "nonconverged"
    assert trial["message"] == ("optimizer_terminal_differs_from_retained_connected_incumbent")
    assert trial["final_topology"]["connected"] is True
    assert trial["optimizer_terminal_topology"]["connected"] is True
    assert trial["optimizer_terminal_matches_retained"] is False
    assert trial["parameters"][0] == pytest.approx(20.0)


def source_receipt(data, bank_sizes=(1, 2, 3, 4, 5)):
    full_bank = np.arange(max(bank_sizes))
    groups = len(np.unique(data.group))
    trials = []
    for count in bank_sizes:
        parameters = np.zeros(6 + len(data.numbers))
        penalty = 0.5 * count * np.log(groups)
        trials.append(
            {
                "arm": "finite_set",
                "satellite_indices": np.arange(count),
                "satellite_count": count,
                "parameters": parameters,
                "objective": float(100 - count),
                "selection_score": float(100 - count + penalty),
                "entry_penalty": float(penalty),
                "groups": groups,
                "success": count < max(bank_sizes),
                "status": "converged" if count < max(bank_sizes) else "nonconverged",
                "raw_masses": model.frozen_raw_masses(count, len(full_bank)),
                "per_satellite_probability": 0.8 / len(full_bank),
            }
        )
    return {
        "schema": "finite-set-raw-control-continuation/v1",
        "stage": "finite_set_raw_control_continuation",
        "unit": {"unit_id": model.PILOT_UNIT},
        "dataset": "DS11",
        "reference_read_before_seal": False,
        "v1_evaluation_read": False,
        "evaluation_written": False,
        "prefit_hashes_reverified_unchanged_before_seal": True,
        "fit": {
            "full_bank": full_bank,
            "finite_set_trials": trials,
            "anchors_used_by_either_arm": 0,
            "finite_set_clutter_rate": 2.0,
            "geometry": data.geometry_receipt,
        },
    }


def paired_source_data(candidate_count=5):
    return SimpleNamespace(
        times=np.array([0.0, 0.0, 1.0, 1.0]),
        measured=np.zeros(4),
        rf=np.full(4, 11.2e9),
        receiver=np.array([0, 1, 0, 1]),
        channel=np.array([1, 1, 2, 2]),
        group=np.arange(4),
        numbers=np.arange(candidate_count),
    )


def test_penalty_seed_routing_and_baseline_incumbents(monkeypatch):
    geometry = model.GroupMedianGeometryData(paired_source_data())
    source = source_receipt(geometry)
    calls = []

    class Prepared:
        pass

    class Adapter:
        def __init__(self, prepared, detection_probability, clutter_rate):
            self.frozen_masses = None
            self.last_result = None

    monkeypatch.setattr(model, "FiniteSetLikelihoodAdapter", Adapter)

    def fake_fitter(data, source_trial, likelihood, **options):
        count = source_trial["satellite_count"]
        calls.append(
            {
                "count": count,
                "parameters": np.asarray(source_trial["parameters"]).copy(),
                "budget": options["budget_s"],
            }
        )
        likelihood.last_result = {
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set",
            "group_values": np.arange(4),
            "satellite_support": np.ones(count),
            "expected_clutter_count": np.zeros(4),
            "raw_peak_count": np.ones(4, dtype=int),
            "unique_peak_count": np.ones(4, dtype=int),
        }
        entry = 0.5 * count * np.log(4)
        omega_penalty = 0.5 * (count - 1) * np.log(4)
        objective = float(100 - count)
        return {
            "model": "finite_set_satellite_bias",
            "satellite_indices": source_trial["satellite_indices"],
            "satellite_count": count,
            "parameters": source_trial["parameters"],
            "omega_hz": np.zeros(count),
            "objective": objective,
            "initial_objective": objective,
            "selection_score": objective + entry + omega_penalty,
            "entry_penalty": entry,
            "omega_parameter_penalty": omega_penalty,
            "success": source_trial["success"],
            "status": source_trial["status"],
        }

    result = model.fit_satellite_bias_models(
        geometry,
        source,
        budget_s_per_bank=7.0,
        trial_fitter=fake_fitter,
        likelihood_preparer=lambda *args: Prepared(),
    )
    assert [call["count"] for call in calls] == [1, 2, 3, 4, 5]
    assert all(call["budget"] == 7.0 for call in calls)
    for call, source_trial in zip(calls, source["fit"]["finite_set_trials"], strict=True):
        np.testing.assert_array_equal(call["parameters"], source_trial["parameters"])
    assert result["zero_omega_initialization"] is True
    assert result["baseline_linear_v2_incumbent_retained"] is True
    assert len(result["baseline_linear_trials"]) == 5
    assert len(result["satellite_bias_trials"]) == 5
    expected = 0.5 * (5 - 1) * np.log(4)
    assert result["satellite_bias_trials"][-1]["omega_parameter_penalty"] == pytest.approx(expected)
    assert result["satellite_bias_selection"]["selection_resolved"] is False


def test_no_reference_curvature_or_relative_calibration_access(monkeypatch):
    class GuardedData(SimpleNamespace):
        def __getattr__(self, name):
            forbidden = ("reference", "truth", "known", "curvature", "calibration")
            if any(value in name for value in forbidden):
                raise AssertionError(f"forbidden input requested: {name}")
            raise AttributeError(name)

    source_data = paired_source_data()
    guarded = GuardedData(**source_data.__dict__)
    geometry = model.GroupMedianGeometryData(guarded)
    source = source_receipt(geometry)

    class Adapter:
        def __init__(self, *args, **kwargs):
            self.frozen_masses = None
            self.last_result = None

    monkeypatch.setattr(model, "FiniteSetLikelihoodAdapter", Adapter)

    def fake_fitter(data, source_trial, likelihood, **options):
        count = source_trial["satellite_count"]
        likelihood.last_result = {
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set",
            "group_values": np.arange(4),
            "satellite_support": np.ones(count),
            "expected_clutter_count": np.zeros(4),
            "raw_peak_count": np.ones(4, dtype=int),
            "unique_peak_count": np.ones(4, dtype=int),
        }
        objective = float(source_trial["objective"])
        return {
            "satellite_indices": source_trial["satellite_indices"],
            "satellite_count": count,
            "parameters": source_trial["parameters"],
            "omega_hz": np.zeros(count),
            "objective": objective,
            "initial_objective": objective,
            "selection_score": objective + 0.5 * count * np.log(4) + 0.5 * (count - 1) * np.log(4),
            "entry_penalty": 0.5 * count * np.log(4),
            "omega_parameter_penalty": 0.5 * (count - 1) * np.log(4),
            "success": True,
            "status": "converged",
        }

    result = model.fit_satellite_bias_models(
        geometry,
        source,
        budget_s_per_bank=1.0,
        trial_fitter=fake_fitter,
        likelihood_preparer=lambda *args: object(),
    )
    assert result["anchors_used"] == 0
    assert "No reference" in result["scope"]
