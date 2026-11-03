from types import SimpleNamespace

import finite_set_relative_rx
import numpy as np
import pytest
import relative_rx_fit


def calibration():
    return relative_rx_fit.RelativeCalibration(
        model="quadratic",
        parameters=np.array([20.0, -8.0, 14.0]),
        reference_time_s=None,
        start_time_s=0.0,
        end_time_s=300.0,
    )


def test_calibration_derivative_and_physical_slopes_include_both_receivers():
    data = SimpleNamespace(times=np.array([0.0, 150.0, 300.0]))
    current = calibration()

    np.testing.assert_allclose(
        finite_set_relative_rx.calibration_derivative(current, [0.0, 150.0, 300.0]),
        [-8.0, 3.0, 14.0],
    )
    slopes = finite_set_relative_rx.physical_endpoint_slopes(
        data, current, common_slope_hz_s=3.0, curvature_hz=150.0
    )
    np.testing.assert_allclose(slopes, [[5.0, -3.0], [-2.0, 12.0]])


def test_slope_constraint_matches_direct_endpoint_slopes():
    data = SimpleNamespace(times=np.array([0.0, 300.0]))
    current = calibration()
    vector = np.array([0.0, 0.0, 0.0, 0.3, 0.6])
    matrix, lower, upper = finite_set_relative_rx.slope_constraint(
        data, current, True, len(vector)
    )
    values = matrix @ vector
    offsets = np.array([4.0, -4.0, -7.0, 7.0])
    direct = finite_set_relative_rx.physical_endpoint_slopes(
        data,
        current,
        common_slope_hz_s=vector[3] * 10.0,
        curvature_hz=vector[-1] * 250.0,
    ).ravel()

    np.testing.assert_allclose(values + offsets, direct)
    assert np.all(values >= lower)
    assert np.all(values <= upper)


class DenseJacobian:
    def __init__(self, matrix):
        self.matrix = np.asarray(matrix, dtype=float)

    def transpose_multiply(self, weights):
        return self.matrix.T @ np.asarray(weights)


class LinearPlan:
    def __init__(self, matrix, rows, satellites):
        self.matrix = np.asarray(matrix, dtype=float)
        self.rows = rows
        self.satellites = satellites

    def predict(self, parameters):
        predicted = (self.matrix @ parameters).reshape(self.rows, self.satellites)
        visible = np.ones_like(predicted, dtype=bool)
        return predicted.ravel(), visible.ravel(), DenseJacobian(self.matrix)


class QuadraticLikelihood:
    def __init__(self, target):
        self.target = np.asarray(target, dtype=float)
        count = self.target.shape[1]
        self.frozen_masses = {
            "raw_satellite_mass": np.full(count, 0.8 / count),
            "raw_background_mass": 0.2,
            "anchor_satellite_mass": np.empty((0, count)),
            "anchor_unknown_mass": np.empty(0),
        }

    def evaluate(self, predicted, visible, **options):
        residual = predicted - self.target
        return {
            "total_log_likelihood": -0.5 * float(np.sum(residual**2)),
            "prediction_gradient": -residual,
            "group_values": np.arange(len(predicted)),
            "satellite_support": np.ones(predicted.shape[1]),
            "null_support": 0.0,
        }


def test_joint_log_likelihood_gradient_matches_finite_difference():
    rng = np.random.default_rng(73)
    rows = 4
    satellite_count = 2
    candidate_count = 3
    full_size = 6 + candidate_count
    matrix = rng.normal(size=(rows * satellite_count, full_size))
    plan = LinearPlan(matrix, rows, satellite_count)
    data = SimpleNamespace(
        times=np.array([0.0, 90.0, 210.0, 300.0]),
        numbers=np.arange(candidate_count),
        receiver=np.array([0, 1, 0, 1]),
    )
    source_parameters = rng.normal(size=full_size)
    satellites = np.array([0, 2])
    current = calibration()
    specification = finite_set_relative_rx._trial_specification(
        data, source_parameters, satellites, current, True
    )
    vector = specification["vector"].copy()
    vector[-1] = 0.4
    target = rng.normal(size=(rows, satellite_count))
    likelihood = QuadraticLikelihood(target)
    design = finite_set_relative_rx.quadratic_time_basis(data)

    def objective(candidate):
        return finite_set_relative_rx._evaluate_trial_state(
            candidate,
            data=data,
            specification=specification,
            satellites=satellites,
            likelihood=likelihood,
            plan=plan,
            design=design,
        )

    state = objective(vector)
    assert np.isclose(state.curvature_prior, 0.5 * vector[-1] ** 2)
    finite = np.empty_like(vector)
    step = 1e-6
    for index in range(len(vector)):
        delta = np.zeros_like(vector)
        delta[index] = step
        finite[index] = (
            objective(vector + delta).objective - objective(vector - delta).objective
        ) / (2 * step)

    np.testing.assert_allclose(state.gradient, finite, rtol=2e-6, atol=2e-5)


def source_receipt(data, counts=(1, 2), statuses=("converged", "nonconverged")):
    full_bank = np.arange(max(counts))
    trials = []
    for count, status in zip(counts, statuses, strict=True):
        parameters = np.zeros(6 + len(data.numbers))
        parameters[2:6] = [100.0 + count, 2.0, 140.0 + count, 4.0]
        masses = finite_set_relative_rx.frozen_raw_masses(count, len(full_bank))
        trials.append(
            {
                "arm": "finite_set",
                "satellite_indices": np.arange(count),
                "satellite_count": count,
                "parameters": parameters,
                "objective": float(100 - count),
                "selection_score": float(105 - count),
                "success": status == "converged",
                "status": status,
                "raw_masses": masses,
                "per_satellite_probability": 0.8 / len(full_bank),
            }
        )
    return {
        "schema": "finite-set-raw-control-continuation/v1",
        "stage": "finite_set_raw_control_continuation",
        "unit": {"unit_id": "DS10-S01"},
        "reference_read_before_seal": False,
        "v1_evaluation_read": False,
        "evaluation_written": False,
        "prefit_hashes_reverified_unchanged_before_seal": True,
        "fit": {
            "full_bank": full_bank,
            "finite_set_trials": trials,
            "anchors_used_by_either_arm": 0,
            "finite_set_clutter_rate": 2.0,
            "finite_set_clutter_rate_semantics": "frozen heuristic",
            "geometry": data.geometry_receipt,
        },
    }


def diagnostic_case(pair_count):
    line_objective = 100.0
    quadratic_objective = 90.0
    return {
        "pairing": {"paired_group_count": pair_count},
        "selected_model": "quadratic",
        "penalized_scores": {
            "line": line_objective + np.log(pair_count),
            "quadratic": quadratic_objective + 1.5 * np.log(pair_count),
        },
        "fit": {
            "reference_time_s": 150.0,
            "line": {
                "objective": line_objective,
                "intercept_hz_at_reference": 0.0,
                "slope_hz_s": 0.0,
            },
            "quadratic": {
                "objective": quadratic_objective,
                "intercept_hz_at_start": 0.0,
                "slope_start_hz_s": -8.0,
                "slope_end_hz_s": 14.0,
            },
        },
    }


def paired_source_data():
    return SimpleNamespace(
        times=np.array([0.0, 0.0, 0.0005, 0.0005, 300.0, 300.0, 300.0005, 300.0005]),
        measured=np.array([10.0, 11.0, 20.0, 21.0, 30.0, 31.0, 40.0, 41.0]),
        rf=np.full(8, 12.0),
        receiver=np.array([0, 0, 1, 1, 0, 0, 1, 1]),
        channel=np.ones(8, dtype=int),
        group=np.array([1, 1, 2, 2, 3, 3, 4, 4]),
        numbers=np.arange(2),
    )


def test_full_ladder_uses_same_projected_seed_budget_and_all_bank_statuses(monkeypatch):
    geometry = finite_set_relative_rx.GroupMedianGeometryData(paired_source_data())
    source = source_receipt(geometry)
    calls = []

    class Prepared:
        pass

    class Adapter:
        def __init__(self, prepared, detection_probability, clutter_rate):
            self.last_result = None

    monkeypatch.setattr(finite_set_relative_rx, "FiniteSetLikelihoodAdapter", Adapter)
    monkeypatch.setattr(
        finite_set_relative_rx,
        "FiniteSetQuadraticLikelihoodAdapter",
        lambda finite_set, masses: finite_set,
    )

    def fake_fitter(data, source_trial, likelihood, calibration, **options):
        tied = relative_rx_fit.expand_tied_parameters(
            relative_rx_fit.reduce_tied_parameters(source_trial["parameters"])
        )
        count = source_trial["satellite_count"]
        quadratic = options["include_quadratic"]
        calls.append(
            {
                "count": count,
                "quadratic": quadratic,
                "budget": options["budget_s"],
                "parameters": tied.copy(),
            }
        )
        likelihood.last_result = {
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set",
            "group_values": np.array([1, 2, 3, 4]),
            "satellite_support": np.ones(count),
            "expected_clutter_count": np.ones(4),
            "raw_peak_count": np.full(4, 2),
            "unique_peak_count": np.full(4, 2),
        }
        objective = float(100 - count - int(quadratic))
        penalty = 0.5 * count * np.log(4) + 0.5 * int(quadratic) * np.log(4)
        return {
            "model": finite_set_relative_rx.MODEL_NAMES[int(quadratic)],
            "parameters": tied,
            "satellite_indices": source_trial["satellite_indices"],
            "satellite_count": count,
            "objective": objective,
            "initial_objective": 123.0 + count,
            "selection_score": objective + penalty,
            "success": source_trial["success"],
            "status": source_trial["status"],
        }

    result = finite_set_relative_rx.fit_relative_rx_models(
        geometry,
        source,
        diagnostic_case(pair_count=2),
        budget_s_per_model_bank=7.0,
        trial_fitter=fake_fitter,
        likelihood_preparer=lambda *args: Prepared(),
    )

    assert [(row["count"], row["quadratic"]) for row in calls] == [
        (1, False),
        (1, True),
        (2, False),
        (2, True),
    ]
    assert all(row["budget"] == 7.0 for row in calls)
    assert all(row["parameters"][2] == row["parameters"][4] for row in calls)
    assert all(row["parameters"][3] == row["parameters"][5] for row in calls)
    assert result["same_sealed_v2_bank_seed_for_both_models"] is True
    assert result["all_source_ladder_banks_fitted_in_both_models"] is True
    assert result["linear_selection"]["selection_resolved"] is False
    assert result["quadratic_selection"]["selection_resolved"] is False
    assert result["combined_selection"]["selection_resolved"] is False
    assert result["combined_selection"]["score_leader"] is not None
    assert [row["source_status"] for row in result["linear_trials"]] == [
        "converged",
        "nonconverged",
    ]


def test_fit_does_not_request_reference_and_adds_no_differential_factor(monkeypatch):
    class Data(SimpleNamespace):
        def __getattr__(self, name):
            if "reference" in name or "truth" in name or "known" in name:
                raise AssertionError(f"forbidden reference input {name}")
            raise AttributeError(name)

    source_data = paired_source_data()
    guarded = Data(**source_data.__dict__)
    geometry = finite_set_relative_rx.GroupMedianGeometryData(guarded)
    source = source_receipt(geometry, counts=(1,), statuses=("converged",))

    class Adapter:
        def __init__(self, *args, **kwargs):
            self.last_result = None

    monkeypatch.setattr(finite_set_relative_rx, "FiniteSetLikelihoodAdapter", Adapter)
    monkeypatch.setattr(
        finite_set_relative_rx,
        "FiniteSetQuadraticLikelihoodAdapter",
        lambda finite_set, masses: finite_set,
    )

    def fake_fitter(data, source_trial, likelihood, calibration, **options):
        likelihood.last_result = {
            "conditioned_nonempty": True,
            "density_convention": "unlabeled_finite_set",
            "group_values": np.array([1, 2, 3, 4]),
            "satellite_support": np.ones(1),
            "expected_clutter_count": np.ones(4),
            "raw_peak_count": np.full(4, 2),
            "unique_peak_count": np.full(4, 2),
        }
        return {
            "parameters": source_trial["parameters"],
            "satellite_indices": source_trial["satellite_indices"],
            "satellite_count": 1,
            "objective": 10.0,
            "initial_objective": 11.0,
            "selection_score": 10.5 + int(options["include_quadratic"]),
            "success": True,
            "status": "converged",
        }

    result = finite_set_relative_rx.fit_relative_rx_models(
        geometry,
        source,
        diagnostic_case(pair_count=2),
        budget_s_per_model_bank=1.0,
        trial_fitter=fake_fitter,
        likelihood_preparer=lambda *args: object(),
    )

    assert result["differential_likelihood_added_to_localization_objective"] is False
    assert result["same_data_calibration_treated_as_independent_evidence"] is False
    assert result["plug_in_calibration_uncertainty_propagated"] is False


def test_source_validation_rejects_reference_tainted_receipt():
    geometry = finite_set_relative_rx.GroupMedianGeometryData(paired_source_data())
    source = source_receipt(geometry, counts=(1,), statuses=("converged",))
    source["v1_evaluation_read"] = True

    with pytest.raises(ValueError, match="prior evaluation"):
        finite_set_relative_rx.fit_relative_rx_models(
            geometry,
            source,
            diagnostic_case(pair_count=2),
            budget_s_per_model_bank=1.0,
        )
