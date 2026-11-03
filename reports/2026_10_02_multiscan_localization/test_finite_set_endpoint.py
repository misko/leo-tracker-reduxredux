from types import SimpleNamespace

import finite_set_endpoint
import finite_set_fit
import finite_set_fixed_position
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


def source_receipt():
    fit = {"full_bank": np.array([0, 1, 2]), "finite_set_clutter_rate": 2.0}
    for arm, satellites in (
        ("finite_set", np.array([0, 1])),
        ("categorical_control", np.array([0, 2])),
    ):
        parameters = np.array([1.0, -2.0, 10.0, 0.1, 20.0, -0.2, 0.3, -0.4, 0.0])
        probability = 0.8 / 3
        trial = {
            "parameters": parameters.copy(),
            "satellite_indices": satellites.copy(),
            "satellite_count": 2,
            "objective": 0.0,
            "selection_score": 1.0,
            "success": True,
            "status": "converged",
            "convergence_reason": "fixture",
            "per_satellite_probability": probability,
            "raw_masses": {
                "raw_satellite_mass": np.full(2, probability),
                "raw_background_mass": 1.0 - 2 * probability,
            },
        }
        fit[f"{arm}_trials"] = [trial]
        fit[f"{arm}_selection"] = {
            "score_leader": {**trial, "parameters": parameters.copy()},
            "selection_resolved": True,
        }
    return {
        "stage": "finite_set_raw_control_continuation",
        "reference_read_before_seal": False,
        "sealed_utc": "2026-10-02T00:00:00Z",
        "unit": {"unit_id": "DS10-S01"},
        "configuration": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "slope_bound_hz_s": 50.0,
        },
        "fit": fit,
    }


class Jacobian:
    def __init__(self, row_count, satellites, candidate_count):
        self.row_count = row_count
        self.satellites = satellites
        self.candidate_count = candidate_count

    def transpose_multiply(self, values):
        values = np.asarray(values).reshape(self.row_count, len(self.satellites))
        gradient = np.zeros(6 + self.candidate_count)
        gradient[0] = np.sum(values)
        gradient[1] = 0.5 * np.sum(values)
        for column, satellite in enumerate(self.satellites):
            gradient[6 + satellite] = np.sum(values[:, column])
        return gradient


class Plan:
    def __init__(self, data, satellites):
        self.data = data
        self.satellites = np.asarray(satellites)

    def predict(self, parameters):
        receiver = np.asarray(self.data.receiver)
        predicted = (
            parameters[0]
            + 0.5 * parameters[1]
            + np.where(receiver == 0, parameters[2], parameters[4])[:, None]
            + 300.0 * self.satellites[None, :]
            + parameters[6 + self.satellites][None, :]
        )
        visible = np.ones_like(predicted, dtype=bool)
        return (
            predicted.ravel(),
            visible.ravel(),
            Jacobian(len(receiver), self.satellites, len(self.data.numbers)),
        )


def reproduce_source(data, source):
    geometry = finite_set_fit.GroupMedianGeometryData(data)
    leader = source["fit"]["finite_set_selection"]["score_leader"]
    satellites = np.asarray(leader["satellite_indices"])
    likelihood = finite_set_fit.build_likelihood_arms(geometry, len(satellites), 3)["finite_set"]
    state = finite_set_fixed_position._evaluate_state(
        geometry,
        np.asarray(leader["parameters"]),
        satellites,
        likelihood,
        sigma_hz=200.0,
        tau_sigma_s=1.0,
        plan_factory=Plan,
    )
    leader["objective"] = state["objective"]
    source["fit"]["finite_set_trials"][0]["objective"] = state["objective"]
    return state


def oracle_receipts(source_sha256, source, free_state):
    leader = source["fit"]["finite_set_selection"]["score_leader"]
    node7_parameters = np.asarray(leader["parameters"]).copy()
    node7_parameters[:2] = [8.0, 6.0]
    homotopy = {
        "schema": "finite-set-fixed-position-homotopy-oracle/v1",
        "oracle": True,
        "eligible_for_cohort": False,
        "unit_id": "DS10-S01",
        "source_fit_sha256": source_sha256,
        "known_position_km": np.array([9.0, 7.0]),
        "fit": {
            "arms": {
                "finite_set": {
                    "selected_bank": np.array([0, 1]),
                    "nodes": [
                        {
                            "node_index": 7,
                            "fraction_from_free_to_known": 0.875,
                            "position_km": np.array([8.0, 6.0]),
                            "attempted": True,
                            "fit_returned": True,
                            "parameters": node7_parameters,
                        }
                    ],
                }
            }
        },
    }
    abrupt = {
        "oracle": True,
        "eligible_for_cohort": False,
        "unit_id": "DS10-S01",
        "source_fit_sha256": source_sha256,
        "oracle_position_km": np.array([9.0, 7.0]),
        "fit": {
            "arms": {
                "finite_set": {
                    "selected_bank": np.array([0, 1]),
                    "fixed_reference": {
                        "success": False,
                        "status": "nonconverged",
                        "objective": free_state["objective"] + 10.0,
                        "satellite_support": free_state["result"]["satellite_support"],
                    },
                }
            }
        },
    }
    return homotopy, abrupt, node7_parameters


def test_endpoint_uses_exact_node7_nuisance_and_runs_no_free_fit():
    data = synthetic_data()
    source = source_receipt()
    free = reproduce_source(data, source)
    homotopy, abrupt, node7 = oracle_receipts("source-sha", source, free)
    calls = []

    def refiner(data, initial, satellites, support, likelihood, **options):
        calls.append((initial.copy(), np.asarray(satellites).copy(), options))
        parameters = initial.copy()
        parameters[:2] = options["fixed_position_km"]
        state = finite_set_fixed_position._evaluate_state(
            data,
            parameters,
            np.asarray(satellites),
            likelihood,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            plan_factory=Plan,
        )
        return {
            "parameters": parameters,
            "satellite_indices": np.asarray(satellites),
            "objective": state["objective"],
            "success": False,
            "status": "nonconverged",
            "convergence_reason": "fixture",
        }

    result = finite_set_endpoint.fit_finite_endpoint(
        data,
        source,
        homotopy,
        abrupt,
        source_sha256="source-sha",
        refiner=refiner,
        plan_factory=Plan,
    )

    assert len(calls) == 1
    assert result["fit_calls"] == 1
    assert result["free_fit_calls"] == 0
    np.testing.assert_array_equal(calls[0][0], node7)
    np.testing.assert_array_equal(calls[0][2]["fixed_position_km"], [9.0, 7.0])
    np.testing.assert_array_equal(result["endpoint"]["parameters"][:2], [9.0, 7.0])
    assert result["endpoint"]["status"] == "nonconverged"


def test_endpoint_rejects_missing_or_changed_node7():
    data = synthetic_data()
    source = source_receipt()
    free = reproduce_source(data, source)
    homotopy, abrupt, _ = oracle_receipts("source-sha", source, free)
    homotopy["fit"]["arms"]["finite_set"]["nodes"][0]["fit_returned"] = False
    with pytest.raises(ValueError, match="returned fixed fit"):
        finite_set_endpoint.fit_finite_endpoint(
            data,
            source,
            homotopy,
            abrupt,
            source_sha256="source-sha",
            plan_factory=Plan,
        )

    homotopy, abrupt, _ = oracle_receipts("source-sha", source, free)
    homotopy["fit"]["arms"]["finite_set"]["selected_bank"] = [1, 2]
    with pytest.raises(ValueError, match="bank differs"):
        finite_set_endpoint.fit_finite_endpoint(
            data,
            source,
            homotopy,
            abrupt,
            source_sha256="source-sha",
            plan_factory=Plan,
        )


def test_snapshot_detects_mutation(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.py"
    first.write_text('{"sealed": true}\n')
    second.write_text("stable\n")
    snapshot = finite_set_endpoint._snapshot([first, second])
    finite_set_endpoint._assert_snapshot(snapshot)
    first.write_text('{"sealed": false}\n')
    with pytest.raises(RuntimeError, match="provenance changed before seal"):
        finite_set_endpoint._assert_snapshot(snapshot)
