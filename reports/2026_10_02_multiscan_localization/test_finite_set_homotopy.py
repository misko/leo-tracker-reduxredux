from types import SimpleNamespace

import finite_set_fixed_position
import finite_set_fit
import finite_set_homotopy
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
    banks = {"finite_set": np.array([0, 1]), "categorical_control": np.array([0, 2])}
    for arm in finite_set_homotopy.ARMS:
        parameters = np.array([1.0, -2.0, 10.0, 0.1, 20.0, -0.2, 0.3, -0.4, 0.0])
        satellites = banks[arm]
        probability = 0.8 / len(fit["full_bank"])
        trial = {
            "parameters": parameters.copy(),
            "satellite_indices": satellites.copy(),
            "satellite_count": len(satellites),
            "objective": 0.0,
            "selection_score": 1.0,
            "success": True,
            "status": "converged",
            "convergence_reason": "fixture",
            "per_satellite_probability": probability,
            "raw_masses": {
                "raw_satellite_mass": np.full(len(satellites), probability),
                "raw_background_mass": 1.0 - len(satellites) * probability,
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
        "configuration": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "slope_bound_hz_s": 50.0,
        },
        "fit": fit,
    }


class SyntheticJacobian:
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


class SyntheticPlan:
    def __init__(self, data, satellites):
        self.data = data
        self.satellites = np.asarray(satellites)

    def predict(self, parameters):
        receiver = np.asarray(self.data.receiver)
        prediction = (
            parameters[0]
            + 0.5 * parameters[1]
            + np.where(receiver == 0, parameters[2], parameters[4])[:, None]
            + 300.0 * self.satellites[None, :]
            + parameters[6 + self.satellites][None, :]
        )
        visible = np.ones_like(prediction, dtype=bool)
        return (
            prediction.ravel(),
            visible.ravel(),
            SyntheticJacobian(len(receiver), self.satellites, len(self.data.numbers)),
        )


def reproduce_source_objectives(data, source):
    geometry = finite_set_fit.GroupMedianGeometryData(data)
    for arm in finite_set_homotopy.ARMS:
        leader = source["fit"][f"{arm}_selection"]["score_leader"]
        satellites = np.asarray(leader["satellite_indices"])
        likelihood = finite_set_fit.build_likelihood_arms(
            geometry, len(satellites), len(source["fit"]["full_bank"])
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


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make_refiner(clock, calls, consume):
    def refiner(data, initial, satellites, support, likelihood, **options):
        calls.append(
            {
                "initial": initial.copy(),
                "satellites": np.asarray(satellites).copy(),
                "budget": options["budget_s"],
                "position": np.asarray(options["fixed_position_km"]).copy(),
            }
        )
        clock.now += consume(options["budget_s"], len(calls))
        parameters = initial.copy()
        parameters[:2] = options["fixed_position_km"]
        parameters[2] += 0.01
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
            "fixed_position_km": np.asarray(options["fixed_position_km"]).copy(),
            "objective": state["objective"],
            "success": True,
            "status": "converged",
            "convergence_reason": "fixture",
        }

    return refiner


def test_all_nodes_fixed_exact_no_free_fit_and_warm_sequentially():
    data = synthetic_data()
    source = source_receipt()
    reproduce_source_objectives(data, source)
    clock = Clock()
    calls = []
    result = finite_set_homotopy.fit_fixed_position_homotopy(
        data,
        source,
        [9.0, 6.0],
        refiner=make_refiner(clock, calls, lambda budget, call: 0.5),
        plan_factory=SyntheticPlan,
        clock=clock,
    )

    assert result["free_fit_calls"] == 0
    assert len(calls) == 16
    for arm in finite_set_homotopy.ARMS:
        nodes = result["arms"][arm]["nodes"]
        assert len(nodes) == 8
        assert all(node["attempted"] and node["fit_returned"] for node in nodes)
        np.testing.assert_array_equal(nodes[-1]["position_km"], [9.0, 6.0])
        np.testing.assert_array_equal(nodes[-1]["optimizer"]["parameters"][:2], [9.0, 6.0])
        assert nodes[0]["warm_start_source"] == "sealed_v2_free_leader_nuisance"
        assert nodes[1]["warm_start_source"] == "fixed_node_1_best_finite_nuisance"
        assert result["arms"][arm]["endpoint"] is not None


def test_remaining_time_is_divided_across_remaining_nodes():
    data = synthetic_data()
    source = source_receipt()
    reproduce_source_objectives(data, source)
    clock = Clock()
    calls = []
    finite_set_homotopy.fit_fixed_position_homotopy(
        data,
        source,
        [2.0, 3.0],
        total_budget_s_per_arm=8.0,
        refiner=make_refiner(clock, calls, lambda budget, call: budget / 2),
        plan_factory=SyntheticPlan,
        clock=clock,
    )

    first_arm = calls[:8]
    assert first_arm[0]["budget"] == pytest.approx(1.0)
    assert first_arm[1]["budget"] == pytest.approx(7.5 / 7)
    assert first_arm[2]["budget"] == pytest.approx((7.5 - 7.5 / 14) / 6)
    assert all(call["budget"] > 0 for call in first_arm)


def test_all_nodes_remain_represented_after_shared_deadline_timeout():
    data = synthetic_data()
    source = source_receipt()
    reproduce_source_objectives(data, source)
    clock = Clock()
    calls = []
    result = finite_set_homotopy.fit_fixed_position_homotopy(
        data,
        source,
        [2.0, 3.0],
        total_budget_s_per_arm=4.0,
        refiner=make_refiner(clock, calls, lambda budget, call: 5.0),
        plan_factory=SyntheticPlan,
        clock=clock,
    )

    for arm in finite_set_homotopy.ARMS:
        nodes = result["arms"][arm]["nodes"]
        assert len(nodes) == 8
        assert nodes[0]["attempted"] is True
        assert all(node["status"] == "limit_reached" for node in nodes[1:])
        assert all(node["attempted"] is False for node in nodes[1:])
        assert result["arms"][arm]["cooperative_deadline_overrun_s"] > 0


def test_snapshot_detects_provenance_mutation(tmp_path):
    source = tmp_path / "source.json"
    dependency = tmp_path / "solver.py"
    source.write_text('{"sealed": true}\n')
    dependency.write_text("stable\n")
    snapshot = finite_set_homotopy._snapshot([source, dependency])

    finite_set_homotopy._assert_snapshot(snapshot)
    dependency.write_text("changed\n")
    with pytest.raises(RuntimeError, match="provenance changed before seal"):
        finite_set_homotopy._assert_snapshot(snapshot)
