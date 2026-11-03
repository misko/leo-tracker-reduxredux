"""Evaluation-only known-position nuisance profiling, never a localization result."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from finite_set_likelihood import prepare_finite_set_likelihood
from joint_inputs import FRAME_LATITUDE_DEG, FRAME_LONGITUDE_DEG
from prediction_plan import SharedPredictionPlan
from prepare_scans import ROOT, load_scan
from rough_smoke import serializable
from soft_likelihood import SoftLikelihood
from soft_solvers import fit_soft
from timing_model import TimingObjective


def reference_coordinates(latitude_deg, longitude_deg):
    origin_latitude, origin_longitude = np.deg2rad([FRAME_LATITUDE_DEG, FRAME_LONGITUDE_DEG])
    latitude, longitude = np.deg2rad([latitude_deg, longitude_deg])
    delta_longitude = longitude - origin_longitude
    east = np.cos(latitude) * np.sin(delta_longitude)
    north = (np.cos(origin_latitude) * np.sin(latitude)
             - np.sin(origin_latitude) * np.cos(latitude) * np.cos(delta_longitude))
    dot = (np.sin(origin_latitude) * np.sin(latitude)
           + np.cos(origin_latitude) * np.cos(latitude) * np.cos(delta_longitude))
    angular = np.arctan2(np.hypot(east, north), dot)
    bearing = np.arctan2(east, north)
    return 6371.0088 * angular * np.array([np.sin(bearing), np.cos(bearing)])


class FixedLocationJacobian:
    def __init__(self, original):
        self.original = original

    def transpose_multiply(self, weights):
        result = self.original.transpose_multiply(weights).copy()
        result[:2] = 0
        return result

    def normal_matrix(self, weights):
        result = self.original.normal_matrix(weights).copy()
        result[:2, :] = 0
        result[:, :2] = 0
        return result


class FixedLocationPlan(SharedPredictionPlan):
    def predict(self, parameters):
        prediction, visible, jacobian = super().predict(parameters)
        return prediction, visible, FixedLocationJacobian(jacobian)


def run_case(cell):
    session, start_method = cell
    destination = ROOT / "oracle-diagnostic" / f"{session}-{start_method}.json"
    if destination.exists():
        raise FileExistsError(destination)
    evaluated = ROOT / "comparison-soft.json"
    comparison = json.loads(evaluated.read_text())
    assert_snapshot_unchanged(comparison["source_hashes"])
    start_path = (ROOT / "runs-soft" / session / "fisher-medium" / "fit.json"
                  if start_method == "cold"
                  else ROOT / "runs-continuation" / session / "medium" / "fit.json")
    reference_path = ROOT / "scans" / session / "evaluation.json"
    parent = json.loads(start_path.read_text())
    source_hashes = {**parent["source_hashes"], **snapshot_files(
        [__file__, evaluated, start_path, reference_path])}
    assert_snapshot_unchanged(source_hashes)
    reference = json.loads(reference_path.read_text())["reference_site"]
    fixed = reference_coordinates(reference["latitude_deg"], reference["longitude_deg"])
    parameters = np.asarray(parent["fit"]["parameters"], dtype=float)
    parameters[:2] = fixed
    satellites = np.asarray(parent["fit"]["satellite_indices"], dtype=int)
    _, data = load_scan(session)
    likelihood = SoftLikelihood(prepare_finite_set_likelihood(data.measured, data.group),
                                0.8 / len(satellites))
    fitted = fit_soft(data, parameters, satellites, likelihood, 200., budget_s=30.,
                      plan_factory=FixedLocationPlan)
    if not np.array_equal(np.asarray(fitted["parameters"])[:2], fixed):
        raise ValueError("oracle position was not held exactly fixed")
    objective = TimingObjective(data, parameters, satellites, likelihood, 200.)
    value, gradient = objective.evaluate(fitted["vector"])
    if not np.isclose(value, fitted["objective"], rtol=0, atol=1e-6):
        raise ValueError("profiled nuisance fit changed the objective")
    free_gradient = gradient[:2]
    assert_snapshot_unchanged(source_hashes)
    result = {"schema": "ds13-oracle-position-diagnostic/v1", "session": session,
              "start_method": start_method, "sigma_hz": 200., "fit": fitted,
              "known_position_km": fixed, "reference_used_for_fitting": True,
              "interpretation": "Evaluation-only constrained nuisance fit, not an estimator. "
                                "Only a local profile from two already-fitted starts, not a "
                                "proof of the global nuisance optimum at the known location.",
              "free_position_gradient": free_gradient,
              "parent_free_objective": parent["fit"]["objective"],
              "oracle_minus_parent_objective": value - parent["fit"]["objective"],
              "source_hashes": source_hashes, "parent_sha256": digest(start_path)}
    destination.parent.mkdir(exist_ok=True)
    with destination.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"session": session, "start_method": start_method, "success": fitted["success"],
            "objective": value, "oracle_minus_parent": result["oracle_minus_parent_objective"],
            "elapsed_s": fitted["elapsed_s"], "free_position_gradient": free_gradient.tolist()}


if __name__ == "__main__":
    sessions = json.loads((ROOT / "protocol-soft.json").read_text())["sessions"]
    cells = [(session, method) for method in ("cold", "warm") for session in sessions]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for row in executor.map(run_case, cells):
            print(json.dumps(row), flush=True)
