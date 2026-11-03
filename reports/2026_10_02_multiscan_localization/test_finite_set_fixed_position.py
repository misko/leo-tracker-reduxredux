from types import SimpleNamespace

import finite_set_fixed_position
import finite_set_fit
import numpy as np
import pytest


def synthetic_data():
    return SimpleNamespace(
        times=np.array([1.0, 1.002, 2.0, 2.004]),
        measured=np.array([0.0, 120.0, 600.0, 900.0]),
        rf=np.array([11.0, 11.0, 12.0, 12.0]),
        receiver=np.array([0, 0, 1, 1]),
        group=np.array([5, 5, 8, 8]),
        channel=np.ones(4, dtype=int),
        numbers=np.array([101, 202, 303]),
    )


def source_receipt(data):
    parameters = {
        "finite_set": np.array([1.0, -2.0, 10.0, 0.1, 20.0, -0.2, 0.3, -0.4, 0.0]),
        "categorical_control": np.array(
            [1.5, -1.0, 11.0, 0.2, 19.0, -0.1, 0.2, 0.0, -0.5]
        ),
    }
    banks = {"finite_set": np.array([0, 1]), "categorical_control": np.array([0, 2])}
    fit = {"full_bank": np.array([0, 1, 2])}
    for arm in finite_set_fixed_position.ARMS:
        satellites = banks[arm]
        per_satellite = 0.8 / len(fit["full_bank"])
        trial = {
            "parameters": parameters[arm],
            "satellite_indices": satellites,
            "satellite_count": 2,
            "objective": 0.0,
            "selection_score": 1.0,
            "success": arm == "categorical_control",
            "status": "converged" if arm == "categorical_control" else "nonconverged",
            "convergence_reason": "fixture",
            "per_satellite_probability": per_satellite,
            "raw_masses": {
                "raw_satellite_mass": np.full(len(satellites), per_satellite),
                "raw_background_mass": 1.0 - len(satellites) * per_satellite,
            },
        }
        fit[f"{arm}_trials"] = [trial]
        fit[f"{arm}_selection"] = {
            "score_leader": {
                **trial,
                "parameters": parameters[arm].copy(),
                "satellite_indices": banks[arm].copy(),
            },
            "selection_resolved": arm == "categorical_control",
        }
    return {
        "stage": "finite_set_raw_control",
        "reference_read_before_seal": False,
        "sealed_utc": "2026-10-02T00:00:00Z",
        "configuration": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "slope_bound_hz_s": 50.0,
            "finite_set_clutter_rate": 2.0,
            "finite_set_implementation": "batched",
            "full_bank_signal_or_detection_mass": 0.8,
        },
        "fit": fit,
    }


class SyntheticJacobian:
    def __init__(self, rows, satellites, candidate_count):
        self.rows = rows
        self.satellites = satellites
        self.candidate_count = candidate_count

    def transpose_multiply(self, values):
        values = np.asarray(values).reshape(len(self.rows), len(self.satellites))
        gradient = np.zeros(6 + self.candidate_count)
        gradient[0] = np.sum(values)
        gradient[1] = 0.5 * np.sum(values)
        gradient[2] = np.sum(values[self.rows == 0])
        gradient[4] = np.sum(values[self.rows == 1])
        for column, satellite in enumerate(self.satellites):
            gradient[6 + satellite] = np.sum(values[:, column])
        return gradient


class SyntheticPlan:
    def __init__(self, data, satellites):
        self.data = data
        self.satellites = np.asarray(satellites)

    def predict(self, parameters):
        receiver = np.asarray(self.data.receiver)
        base = parameters[0] + 0.5 * parameters[1]
        rx = np.where(receiver == 0, parameters[2], parameters[4])
        prediction = (
            base
            + rx[:, None]
            + 300.0 * self.satellites[None, :]
            + parameters[6 + self.satellites][None, :]
        )
        visible = np.ones_like(prediction, dtype=bool)
        return (
            prediction.ravel(),
            visible.ravel(),
            SyntheticJacobian(receiver, self.satellites, len(self.data.numbers)),
        )


def set_reproduced_objectives(data, source):
    geometry = finite_set_fit.GroupMedianGeometryData(data)
    full_bank = source["fit"]["full_bank"]
    for arm in finite_set_fixed_position.ARMS:
        leader = source["fit"][f"{arm}_selection"]["score_leader"]
        satellites = np.asarray(leader["satellite_indices"])
        likelihood = finite_set_fit.build_likelihood_arms(
            geometry, len(satellites), len(full_bank)
        )[arm]
        state = finite_set_fixed_position._evaluate_state(
            geometry,
            np.asarray(leader["parameters"]),
            satellites,
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            plan_factory=SyntheticPlan,
        )
        leader["objective"] = state["objective"]
        source["fit"][f"{arm}_trials"][0]["objective"] = state["objective"]


def test_fixed_pair_uses_each_frozen_bank_without_free_refits_and_retains_status():
    data = synthetic_data()
    source = source_receipt(data)
    set_reproduced_objectives(data, source)
    calls = []

    def refiner(data, initial, satellites, support, likelihood, **options):
        calls.append(
            {
                "initial": initial.copy(),
                "satellites": np.asarray(satellites).copy(),
                "options": options,
            }
        )
        parameters = initial.copy()
        parameters[:2] = options["fixed_position_km"]
        parameters[2] += 0.25
        state = finite_set_fixed_position._evaluate_state(
            data,
            parameters,
            np.asarray(satellites),
            likelihood,
            sigma_hz=options["sigma_hz"],
            tau_sigma_s=options["tau_sigma_s"],
            plan_factory=SyntheticPlan,
        )
        return {
            "parameters": parameters,
            "satellite_indices": np.asarray(satellites),
            "objective": state["objective"],
            "success": len(calls) == 2,
            "status": "converged" if len(calls) == 2 else "nonconverged",
            "convergence_reason": "fixture-fixed",
        }

    result = finite_set_fixed_position.fit_fixed_position_pairs(
        data,
        source,
        [4.0, -5.0],
        budget_s_per_arm=7.0,
        refiner=refiner,
        plan_factory=SyntheticPlan,
    )

    assert len(calls) == 2
    assert result["free_fit_calls"] == 0
    assert result["fixed_fit_calls"] == 2
    assert result["maximum_case_fit_budget_s"] == 14.0
    assert result["cross_arm_absolute_nll_comparisons"] is False
    for index, arm in enumerate(finite_set_fixed_position.ARMS):
        leader = source["fit"][f"{arm}_selection"]["score_leader"]
        np.testing.assert_array_equal(calls[index]["initial"], leader["parameters"])
        np.testing.assert_array_equal(calls[index]["satellites"], leader["satellite_indices"])
        np.testing.assert_array_equal(calls[index]["options"]["fixed_position_km"], [4.0, -5.0])
        assert calls[index]["options"]["tau_sigma_s"] == 1.0
        assert calls[index]["options"]["tau_bound_s"] == 3.0
        assert calls[index]["options"]["slope_bound"] == 50.0
        np.testing.assert_array_equal(
            result["arms"][arm]["fixed_reference"]["parameters"][:2], [4.0, -5.0]
        )
        assert result["arms"][arm]["source_free"]["status"] == leader["status"]
        assert result["arms"][arm]["fixed_reference"]["status"] == (
            "nonconverged" if index == 0 else "converged"
        )


def test_group_and_prior_decomposition_reconstructs_each_arm_only():
    data = synthetic_data()
    source = source_receipt(data)
    set_reproduced_objectives(data, source)

    def refiner(data, initial, satellites, support, likelihood, **options):
        parameters = initial.copy()
        parameters[:2] = options["fixed_position_km"]
        parameters[6 + np.asarray(satellites)] += 0.1
        state = finite_set_fixed_position._evaluate_state(
            data,
            parameters,
            np.asarray(satellites),
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            plan_factory=SyntheticPlan,
        )
        return {
            "parameters": parameters,
            "satellite_indices": np.asarray(satellites),
            "objective": state["objective"],
            "success": False,
            "status": "nonconverged",
            "convergence_reason": "fixture",
        }

    result = finite_set_fixed_position.fit_fixed_position_pairs(
        data,
        source,
        [2.0, 3.0],
        refiner=refiner,
        plan_factory=SyntheticPlan,
    )

    for arm in finite_set_fixed_position.ARMS:
        decomposition = result["arms"][arm]["decomposition"]
        assert decomposition["decomposition_reconstruction_error"] == pytest.approx(0.0, abs=1e-9)
        assert np.sum(decomposition["group"]["fixed_minus_free_nll"]) == pytest.approx(
            decomposition["fixed_minus_free_negative_log_likelihood"]
        )
        assert len(decomposition["satellites"]) == 2
        assert decomposition["satellite_log_likelihood_additivity"] is False
        assert decomposition["group"]["free_satellite_support"].shape == (2, 2)
        assert result["arms"][arm]["fixed_reference"]["success"] is False


def test_source_selection_validation_and_budget_are_strict():
    data = synthetic_data()
    source = source_receipt(data)
    full_bank, frozen = finite_set_fixed_position.freeze_selected_arms(source, len(data.numbers))
    np.testing.assert_array_equal(full_bank, [0, 1, 2])
    assert set(frozen) == set(finite_set_fixed_position.ARMS)

    source["fit"]["finite_set_trials"][0]["parameters"] = np.zeros(9)
    with pytest.raises(ValueError, match="not uniquely bound"):
        finite_set_fixed_position.freeze_selected_arms(source, len(data.numbers))

    with pytest.raises(ValueError, match=r"\(0, 20\]"):
        finite_set_fixed_position.fit_fixed_position_pairs(
            data, source_receipt(data), [0.0, 0.0], budget_s_per_arm=20.01
        )
