"""Evaluation-only fixed-position profile path toward the known DS13 site."""

from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from finite_set_likelihood import prepare_finite_set_likelihood
from oracle_position_diagnostic import FixedLocationPlan, reference_coordinates
from prepare_scans import ROOT, load_scan
from rough_smoke import serializable
from run_experiment import association_summary
from soft_likelihood import SoftLikelihood
from soft_solvers import fit_soft
from timing_model import TimingObjective

SIGMA_HZ = 200.0
STATION_BUDGET_S = 30.0
FRACTIONS = np.array([0.0, 0.25, 0.5, 0.75, 1.0])


def profile_positions(start_position, known_position, fractions=FRACTIONS):
    start = np.asarray(start_position, dtype=float)
    known = np.asarray(known_position, dtype=float)
    fractions = np.asarray(fractions, dtype=float)
    if start.shape != (2,) or known.shape != (2,):
        raise ValueError("profile endpoints must be two-dimensional")
    if (
        fractions.ndim != 1
        or len(fractions) < 2
        or np.any(~np.isfinite(fractions))
        or fractions[0] != 0.0
        or fractions[-1] != 1.0
        or np.any(np.diff(fractions) <= 0.0)
    ):
        raise ValueError("fractions must increase strictly from zero to one")
    return start + fractions[:, None] * (known - start)


def reported_status(fitted):
    status = fitted["status"]
    if status == "projected_stationary_visibility_branch" and not fitted["success"]:
        return "best_finite_nonterminal_stationarity_unverified"
    return status


def continue_profile(
    start_parameters,
    known_position,
    fit_station,
    evaluate_station,
    *,
    fractions=FRACTIONS,
):
    current = np.asarray(start_parameters, dtype=float).copy()
    if current.ndim != 1 or len(current) < 7 or np.any(~np.isfinite(current)):
        raise ValueError("start_parameters must be a finite complete model vector")
    positions = profile_positions(current[:2], known_position, fractions)
    stations = []
    for index, (fraction, position) in enumerate(
        zip(np.asarray(fractions, dtype=float), positions, strict=True)
    ):
        fitted = None
        if index:
            station_start = current.copy()
            station_start[:2] = position
            fitted = fit_station(station_start, position.copy())
            current = np.asarray(fitted["parameters"], dtype=float).copy()
            if current.shape != station_start.shape or np.any(~np.isfinite(current)):
                raise ValueError("station fit returned invalid complete parameters")
            if not np.array_equal(current[:2], position):
                raise ValueError("profile station position was not held exactly fixed")
        assessment = evaluate_station(current.copy())
        station = {
            "index": index,
            "fraction": float(fraction),
            "fixed_position_km": position.copy(),
            **assessment,
        }
        if fitted is None:
            station.update(
                {
                    "solver_status": "sealed_warm_medium_start",
                    "raw_solver_status": "sealed_warm_medium_start",
                    "solver_success": True,
                    "fit_elapsed_s": 0.0,
                    "fit_calls": 0,
                }
            )
        else:
            station.update(
                {
                    "solver_status": reported_status(fitted),
                    "raw_solver_status": fitted["status"],
                    "solver_success": bool(fitted["success"]),
                    "fit_elapsed_s": float(fitted["elapsed_s"]),
                    "fit_calls": int(fitted["calls"]),
                    "best_is_terminal": bool(fitted["best_is_terminal"]),
                    "projected_gradient_inf_norm": fitted[
                        "projected_gradient_inf_norm"
                    ],
                    "newton_decrement": fitted["newton_decrement"],
                }
            )
        stations.append(station)
    return stations


def _likelihood(data, satellite_count):
    return SoftLikelihood(
        prepare_finite_set_likelihood(data.measured, data.group),
        0.8 / satellite_count,
    )


def _profile_scan(data, start_parameters, satellites, known_position):
    satellites = np.asarray(satellites, dtype=int)

    def fit_station(parameters, _position):
        likelihood = _likelihood(data, len(satellites))
        return fit_soft(
            data,
            parameters,
            satellites,
            likelihood,
            SIGMA_HZ,
            budget_s=STATION_BUDGET_S,
            method="fisher",
            plan_factory=FixedLocationPlan,
        )

    def evaluate_station(parameters):
        likelihood = _likelihood(data, len(satellites))
        objective = TimingObjective(
            data,
            parameters,
            satellites,
            likelihood,
            SIGMA_HZ,
        )
        vector = objective.initial_vector
        value, gradient = objective.evaluate(vector)
        if objective.last is None or not np.isfinite(value):
            raise RuntimeError("profile station objective is not finite")
        return {
            "objective": float(value),
            "data_objective": float(objective.last["data_objective"]),
            "prior_objective": float(objective.last["prior_objective"]),
            "free_position_gradient": np.asarray(gradient[:2], dtype=float).copy(),
            "parameters": np.asarray(parameters, dtype=float).copy(),
            "support": association_summary(likelihood.last_result),
        }

    return continue_profile(
        start_parameters,
        known_position,
        fit_station,
        evaluate_station,
    )


def _validated_parent(session):
    path = ROOT / "runs-continuation" / session / "medium" / "fit.json"
    record = json.loads(path.read_text())
    fitted = record.get("fit", {})
    if (
        record.get("schema") != "ds13-soft-continuation-fit/v1"
        or record.get("session") != session
        or record.get("tolerance") != "medium"
        or record.get("reference_read_before_seal") is not False
        or fitted.get("success") is not True
        or fitted.get("best_is_terminal") is not True
    ):
        raise ValueError("profile path requires a converged sealed warm-medium parent")
    assert_snapshot_unchanged(record["source_hashes"])
    return path, record


def run_case(session):
    protocol_path = ROOT / "protocol-soft.json"
    protocol = json.loads(protocol_path.read_text())
    if session not in protocol["sessions"]:
        raise ValueError("session is outside the frozen soft protocol")
    destination = ROOT / "profile-path-diagnostic" / f"{session}.json"
    if destination.exists():
        raise FileExistsError(destination)
    parent_path, parent = _validated_parent(session)
    reference_path = ROOT / "scans" / session / "evaluation.json"
    previous_path = ROOT / "oracle-diagnostic" / f"{session}-warm.json"
    previous = json.loads(previous_path.read_text())
    if (
        previous.get("schema") != "ds13-oracle-position-diagnostic/v1"
        or previous.get("session") != session
        or previous.get("reference_used_for_fitting") is not True
    ):
        raise ValueError("invalid previous known-position diagnostic")
    source_hashes = {
        **parent["source_hashes"],
        **snapshot_files(
            [
                __file__,
                protocol_path,
                parent_path,
                reference_path,
                previous_path,
                ROOT / "oracle_position_diagnostic.py",
                ROOT / "soft_solvers.py",
            ]
        ),
    }
    assert_snapshot_unchanged(source_hashes)
    reference = json.loads(reference_path.read_text())["reference_site"]
    known_position = reference_coordinates(
        reference["latitude_deg"],
        reference["longitude_deg"],
    )
    parameters = np.asarray(parent["fit"]["parameters"], dtype=float)
    satellites = np.asarray(parent["fit"]["satellite_indices"], dtype=int)
    _source, data = load_scan(session)
    stations = _profile_scan(data, parameters, satellites, known_position)
    start_objective = stations[0]["objective"]
    truth_objective = stations[-1]["objective"]
    previous_truth_objective = float(previous["fit"]["objective"])
    comparison_tolerance = 1.0e-8 * max(1.0, abs(previous_truth_objective))
    lower_truth_profile_found = bool(
        truth_objective < previous_truth_objective - comparison_tolerance
    )
    assert_snapshot_unchanged(source_hashes)
    result = {
        "schema": "ds13-known-position-profile-path/v1",
        "session": session,
        "sigma_hz": SIGMA_HZ,
        "fractions": FRACTIONS,
        "station_budget_s": STATION_BUDGET_S,
        "maximum_profile_fits": len(FRACTIONS) - 1,
        "start_position_km": parameters[:2],
        "known_position_km": known_position,
        "stations": stations,
        "start_objective": start_objective,
        "truth_objective": truth_objective,
        "truth_minus_start_objective": truth_objective - start_objective,
        "previous_oracle_truth_objective": previous_truth_objective,
        "truth_improvement_vs_previous_oracle": (
            previous_truth_objective - truth_objective
        ),
        "lower_truth_profile_found": lower_truth_profile_found,
        "reverse_path_run": False,
        "reference_used_for_fitting": True,
        "estimator_result": False,
        "interpretation": (
            "Evaluation-only forward continuation of nuisance parameters along a "
            "fixed path from a converged free-position fit to the known site. A lower "
            "truth objective than the previous direct oracle fit identifies a nuisance-"
            "basin artifact in that earlier comparison; otherwise this bounded path does "
            "not establish the global profile. It is not a localization estimator."
        ),
        "reverse_path_omission": (
            "Omitted to retain the four-fit, 120-second-per-scan bound."
        ),
        "parent_path": str(parent_path),
        "parent_sha256": digest(parent_path),
        "previous_oracle_path": str(previous_path),
        "previous_oracle_sha256": digest(previous_path),
        "source_hashes": source_hashes,
    }
    destination.parent.mkdir(exist_ok=True)
    with destination.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {
        "session": session,
        "start_objective": start_objective,
        "truth_objective": truth_objective,
        "previous_oracle_truth_objective": previous_truth_objective,
        "lower_truth_profile_found": lower_truth_profile_found,
        "station_statuses": [station["solver_status"] for station in stations],
    }


def main():
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    sessions = json.loads((ROOT / "protocol-soft.json").read_text())["sessions"]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for result in executor.map(run_case, sessions):
            print(json.dumps(serializable(result)), flush=True)


if __name__ == "__main__":
    main()


__all__ = [
    "FixedLocationPlan",
    "continue_profile",
    "profile_positions",
    "reported_status",
    "run_case",
]
