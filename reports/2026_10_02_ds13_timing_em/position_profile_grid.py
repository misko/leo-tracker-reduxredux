"""Bounded fixed-position profile grid for the current common-RF DS13 loss."""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, digest, snapshot_files
from oracle_position_diagnostic import reference_coordinates
from prepare_scans import ROOT, load_scan
from rf_calibration_diagnostic import CalibrationObjective
from rough_smoke import serializable
from truth_start_diagnostic import optimize, projected_gradient

SIGMA_HZ = 200.0
CLUTTER_RATE = 2.0
STAGE_BUDGET_S = 6.0
MAX_STAGE_BUDGET_S = 8.0
MAX_SCAN_BUDGET_S = 320.0
EARTH_RADIUS_KM = 6371.0088
BEARINGS = (
    ("N", 0.0),
    ("NE", 45.0),
    ("E", 90.0),
    ("SE", 135.0),
    ("S", 180.0),
    ("SW", 225.0),
    ("W", 270.0),
    ("NW", 315.0),
)
RADII_M = (50.0, 100.0, 500.0)


def geodesic_position(latitude_deg, longitude_deg, bearing_deg, radius_m):
    values = np.asarray(
        [latitude_deg, longitude_deg, bearing_deg, radius_m],
        dtype=float,
    )
    if np.any(~np.isfinite(values)) or radius_m < 0.0:
        raise ValueError("geodesic inputs must be finite with nonnegative radius")
    latitude = np.deg2rad(latitude_deg)
    longitude = np.deg2rad(longitude_deg)
    bearing = np.deg2rad(bearing_deg)
    angular = radius_m / 1000.0 / EARTH_RADIUS_KM
    destination_latitude = np.arcsin(
        np.sin(latitude) * np.cos(angular)
        + np.cos(latitude) * np.sin(angular) * np.cos(bearing)
    )
    destination_longitude = longitude + np.arctan2(
        np.sin(bearing) * np.sin(angular) * np.cos(latitude),
        np.cos(angular) - np.sin(latitude) * np.sin(destination_latitude),
    )
    return reference_coordinates(
        np.rad2deg(destination_latitude),
        np.rad2deg(destination_longitude),
    )


def position_grid(reference_site, protocol_positions):
    latitude = float(reference_site["latitude_deg"])
    longitude = float(reference_site["longitude_deg"])
    bearings = protocol_positions["bearings_deg_clockwise_from_north"]
    radii = protocol_positions["radii_m"]
    if list(map(float, bearings)) != [value for _label, value in BEARINGS]:
        raise ValueError("protocol bearings differ from the fixed compass grid")
    if list(map(float, radii)) != list(RADII_M):
        raise ValueError("protocol radii differ from the fixed profile grid")
    grid = {}
    for label, bearing in BEARINGS:
        grid[label] = [
            {
                "label": f"{label}-{int(radius)}m",
                "kind": "radial",
                "bearing_label": label,
                "bearing_deg": bearing,
                "radius_m": radius,
                "position_km": geodesic_position(
                    latitude,
                    longitude,
                    bearing,
                    radius,
                ),
            }
            for radius in RADII_M
        ]
    return grid


def _probability(probability_override, satellite_count):
    value = 0.8 / satellite_count if probability_override is None else probability_override
    if not np.ndim(value) == 0 or not np.isfinite(value) or not 0 < value <= 1:
        raise ValueError("probability_override must be a scalar in (0,1]")
    return float(value)


def _evaluate_state(objective, vector, bounds, *, started, calls_before):
    objective.base.deadline = float("inf")
    value, gradient = objective.evaluate(vector)
    if objective.base.last is None or not np.isfinite(value):
        raise RuntimeError("fixed-position profile state is not finite")
    likelihood = objective.likelihood.last_result
    data_nll = -float(likelihood["total_log_likelihood"])
    prior_nll, _prior_gradient = objective.base.penalty(vector[: objective.size])
    if not np.isclose(value, data_nll + prior_nll, rtol=0.0, atol=1.0e-8):
        raise ValueError("profile objective decomposition does not close")
    projected, _free = projected_gradient(
        vector,
        gradient,
        bounds,
        objective.scale,
    )
    state = objective.base.state(vector[: objective.size])
    group_values = np.asarray(likelihood["group_values"]).copy()
    data = objective.base.data
    group_time = np.asarray(
        [
            np.median(np.asarray(data.times)[np.asarray(data.group) == group_value])
            for group_value in group_values
        ],
        dtype=float,
    )
    return {
        "vector": np.asarray(vector, dtype=float).copy(),
        "parameters": state["parameters"].copy(),
        "rf_coefficient_hz_per_ghz": np.asarray(
            vector[objective.size :],
            dtype=float,
        ).copy(),
        "objective": float(value),
        "total_nll": float(value),
        "data_nll": data_nll,
        "nuisance_prior_nll": float(prior_nll),
        "gradient": np.asarray(gradient, dtype=float).copy(),
        "free_position_gradient": np.asarray(gradient[:2], dtype=float).copy(),
        "projected_nuisance_gradient_inf_norm": float(
            np.max(np.abs(projected), initial=0.0)
        ),
        "group_values": group_values,
        "group_time_s": group_time,
        "group_log_likelihood": np.asarray(
            likelihood["log_likelihood"],
            dtype=float,
        ).copy(),
        "satellite_support": np.asarray(
            likelihood["satellite_support"],
            dtype=float,
        ).copy(),
        "elapsed_s": float(time.monotonic() - started),
        "calls": int(objective.base.calls - calls_before),
    }


def run_profile(
    data,
    initial_parameters,
    satellites,
    rf_coefficient,
    position,
    probability_override=None,
    *,
    start_vector=None,
    budget_s=STAGE_BUDGET_S,
    objective_factory=CalibrationObjective,
):
    """Profile all nuisance variables at one fixed optimizer position."""
    if not np.isfinite(budget_s) or not 0 < budget_s <= MAX_STAGE_BUDGET_S:
        raise ValueError("budget_s must lie in (0,8]")
    satellites = np.asarray(satellites, dtype=int)
    if satellites.ndim != 1 or not len(satellites):
        raise ValueError("satellites must be a nonempty one-dimensional array")
    position = np.asarray(position, dtype=float)
    if position.shape != (2,) or np.any(~np.isfinite(position)):
        raise ValueError("position must contain finite east/north kilometers")
    probability = _probability(probability_override, len(satellites))
    started = time.monotonic()
    objective = objective_factory(
        data,
        np.asarray(initial_parameters, dtype=float),
        satellites,
        False,
        float(budget_s),
    )
    objective.likelihood.detection_probability = probability
    if start_vector is None:
        current = objective.initial.copy()
        coefficients = np.asarray(rf_coefficient, dtype=float).reshape(-1)
        if coefficients.shape != (len(current) - objective.size,):
            raise ValueError("rf_coefficient has the wrong shape")
        current[objective.size :] = coefficients
    else:
        current = np.asarray(start_vector, dtype=float).copy()
        if current.shape != objective.initial.shape or np.any(~np.isfinite(current)):
            raise ValueError("start_vector has the wrong shape or non-finite values")
    current[:2] = position
    bounds = list(objective.bounds)
    bounds[:2] = [(coordinate, coordinate) for coordinate in position]
    calls_before = objective.base.calls
    fitted = optimize(objective, current, bounds, budget_s=float(budget_s))
    vector = np.asarray(fitted["vector"], dtype=float)
    if not np.array_equal(vector[:2], position):
        raise ValueError("optimizer changed a fixed profile position")
    evaluated = _evaluate_state(
        objective,
        vector,
        bounds,
        started=started,
        calls_before=calls_before,
    )
    return {
        **evaluated,
        "status": fitted["status"],
        "success": bool(fitted["success"]),
        "budget_s": float(budget_s),
        "detection_probability": probability,
        "optimizer_elapsed_s": float(fitted["elapsed_s"]),
        "optimizer_calls": int(len(fitted["trace"])),
    }


def _evaluate_sealed(
    data,
    initial_parameters,
    satellites,
    vector,
    position,
    *,
    objective_factory=CalibrationObjective,
):
    started = time.monotonic()
    objective = objective_factory(
        data,
        initial_parameters,
        satellites,
        False,
        MAX_STAGE_BUDGET_S,
    )
    probability = _probability(None, len(satellites))
    objective.likelihood.detection_probability = probability
    vector = np.asarray(vector, dtype=float).copy()
    position = np.asarray(position, dtype=float)
    if vector.shape != objective.initial.shape or not np.allclose(
        vector[:2],
        position,
        rtol=0.0,
        atol=1.0e-12,
    ):
        raise ValueError("sealed vector does not match the declared position")
    bounds = list(objective.bounds)
    bounds[:2] = [(coordinate, coordinate) for coordinate in position]
    evaluated = _evaluate_state(
        objective,
        vector,
        bounds,
        started=started,
        calls_before=objective.base.calls,
    )
    success = evaluated["projected_nuisance_gradient_inf_norm"] <= 1.0e-3
    return {
        **evaluated,
        "status": (
            "sealed_parent_projected_gradient_converged"
            if success
            else "sealed_parent_stationarity_unverified"
        ),
        "success": success,
        "budget_s": 0.0,
        "detection_probability": probability,
        "optimizer_elapsed_s": 0.0,
        "optimizer_calls": 0,
    }


def select_best_attempt(attempts):
    finite = [
        (index, attempt)
        for index, attempt in enumerate(attempts)
        if attempt.get("objective") is not None and np.isfinite(attempt["objective"])
    ]
    if not finite:
        return None, None
    return min(finite, key=lambda item: item[1]["objective"])


def _compact_attempt(attempt):
    return {
        key: value
        for key, value in attempt.items()
        if key
        not in {
            "group_values",
            "group_time_s",
            "group_log_likelihood",
            "satellite_support",
        }
    }


def _failure_attempt(direction, sequence_index, start_vector, status, error=None):
    result = {
        "direction": direction,
        "sequence_index": sequence_index,
        "start_vector": np.asarray(start_vector, dtype=float).copy(),
        "objective": None,
        "status": status,
        "success": False,
        "elapsed_s": 0.0,
        "calls": 0,
    }
    if error is not None:
        result["error"] = f"{type(error).__name__}: {error}"
    return result


def _run_chain(
    data,
    initial_parameters,
    satellites,
    rf_coefficient,
    points,
    start_vector,
    direction,
    scan_started,
):
    current = np.asarray(start_vector, dtype=float).copy()
    results = {}
    for sequence_index, point in enumerate(points):
        remaining = MAX_SCAN_BUDGET_S - (time.monotonic() - scan_started)
        if remaining <= 0.25:
            attempt = _failure_attempt(
                direction,
                sequence_index,
                current,
                "scan_budget_not_run",
            )
        else:
            try:
                fitted = run_profile(
                    data,
                    initial_parameters,
                    satellites,
                    rf_coefficient,
                    point["position_km"],
                    start_vector=current,
                    budget_s=min(STAGE_BUDGET_S, remaining),
                )
                attempt = {
                    **fitted,
                    "direction": direction,
                    "sequence_index": sequence_index,
                    "start_vector": current.copy(),
                }
                current = np.asarray(fitted["vector"], dtype=float).copy()
            except Exception as error:
                attempt = _failure_attempt(
                    direction,
                    sequence_index,
                    current,
                    "execution_error",
                    error,
                )
        results.setdefault(point["label"], []).append(attempt)
    return results


def _position_receipt(point, attempts):
    best_index, best = select_best_attempt(attempts)
    return {
        **point,
        "fixed_position_km": np.asarray(point["position_km"], dtype=float).copy(),
        "best_attempt_index": best_index,
        "best": best,
        "attempts": [_compact_attempt(attempt) for attempt in attempts],
        "ranking_resolved": bool(best is not None and best.get("success", False)),
    }


def _validated_inputs(session, protocol):
    truth_path = ROOT / "truth-start-diagnostic" / f"{session}-common-rf-profiled.json"
    rf_path = ROOT / "rf-calibration-diagnostic" / f"{session}-common.json"
    seed_path = ROOT / "scans" / session / "seed.json"
    reference_path = ROOT / "scans" / session / "evaluation.json"
    records = {
        "truth": json.loads(truth_path.read_text()),
        "rf": json.loads(rf_path.read_text()),
        "seed": json.loads(seed_path.read_text()),
        "reference": json.loads(reference_path.read_text()),
    }
    if (
        records["truth"].get("schema") != "ds13-truth-start-diagnostic/v1"
        or records["truth"].get("session") != session
        or records["truth"].get("variant") != "common-rf-profiled"
        or records["truth"].get("reference_used_for_fitting") is not True
        or records["rf"].get("schema") != "ds13-rf-calibration-diagnostic/v1"
        or records["rf"].get("variant") != "common"
        or records["rf"].get("reference_read_in_fitter") is not False
        or session not in protocol["sessions"]
    ):
        raise ValueError("invalid sealed position-profile input")
    inherited = {}
    for key in ("truth", "rf"):
        assert_snapshot_unchanged(records[key]["source_hashes"])
        inherited.update(records[key]["source_hashes"])
    paths = [
        Path(__file__),
        ROOT / "position-profile-protocol.json",
        ROOT / "position-profile-resource-amendment.json",
        truth_path,
        rf_path,
        seed_path,
        reference_path,
        ROOT / "truth_start_diagnostic.py",
        ROOT / "rf_calibration_diagnostic.py",
    ]
    return records, paths, inherited


def run_case(session):
    destination = ROOT / "position-profile-grid" / f"{session}.json"
    if destination.exists():
        raise FileExistsError(destination)
    protocol_path = ROOT / "position-profile-protocol.json"
    protocol = json.loads(protocol_path.read_text())
    records, paths, inherited = _validated_inputs(session, protocol)
    source_hashes = {**inherited, **snapshot_files(paths)}
    assert_snapshot_unchanged(source_hashes)
    scan_started = time.monotonic()
    _source, data = load_scan(session)
    satellites = np.asarray(records["seed"]["satellites"], dtype=int)
    initial_parameters = np.asarray(records["rf"]["fit"]["parameters"], dtype=float)
    rf_coefficient = np.asarray(
        records["rf"]["fit"]["rf_coefficient_hz_per_ghz"],
        dtype=float,
    )
    truth_vector = np.asarray(records["truth"]["start_vector"], dtype=float)
    displaced_vector = np.asarray(records["truth"]["fit"]["vector"], dtype=float)
    reference = records["reference"]["reference_site"]
    true_position = reference_coordinates(
        reference["latitude_deg"],
        reference["longitude_deg"],
    )
    if not np.allclose(
        truth_vector[:2],
        true_position,
        rtol=0.0,
        atol=1.0e-12,
    ):
        raise ValueError("sealed truth-profile vector is not at the reference")
    expected_size = 7 + len(satellites)
    if truth_vector.shape != (expected_size,) or displaced_vector.shape != (expected_size,):
        raise ValueError("sealed extended calibration vector has the wrong size")
    grid = position_grid(reference, protocol["positions"])
    truth_attempt = {
        **_evaluate_sealed(
            data,
            initial_parameters,
            satellites,
            truth_vector,
            true_position,
        ),
        "direction": "sealed_truth",
        "sequence_index": 0,
        "start_vector": truth_vector.copy(),
    }
    displaced_attempt = {
        **_evaluate_sealed(
            data,
            initial_parameters,
            satellites,
            displaced_vector,
            displaced_vector[:2],
        ),
        "direction": "sealed_displaced",
        "sequence_index": 0,
        "start_vector": displaced_vector.copy(),
    }
    positions = [
        _position_receipt(
            {
                "label": "truth",
                "kind": "reference",
                "bearing_label": None,
                "bearing_deg": None,
                "radius_m": 0.0,
                "position_km": true_position,
            },
            [truth_attempt],
        )
    ]
    for bearing_label, _bearing in BEARINGS:
        points = grid[bearing_label]
        attempts = _run_chain(
            data,
            initial_parameters,
            satellites,
            rf_coefficient,
            points,
            truth_vector,
            "outward_from_truth",
            scan_started,
        )
        inward = _run_chain(
            data,
            initial_parameters,
            satellites,
            rf_coefficient,
            list(reversed(points)),
            displaced_vector,
            "inward_from_displaced",
            scan_started,
        )
        for point in points:
            positions.append(
                _position_receipt(
                    point,
                    attempts.get(point["label"], []) + inward.get(point["label"], []),
                )
            )
    positions.append(
        _position_receipt(
            {
                "label": "displaced_optimum",
                "kind": "previous_displaced_optimum",
                "bearing_label": None,
                "bearing_deg": None,
                "radius_m": None,
                "position_km": displaced_vector[:2],
            },
            [displaced_attempt],
        )
    )
    failed = [position["label"] for position in positions if position["best"] is None]
    unresolved = [
        position["label"]
        for position in positions
        if not position["ranking_resolved"]
    ]
    elapsed = time.monotonic() - scan_started
    result = {
        "schema": "ds13-position-profile-grid/v1",
        "session": session,
        "sigma_hz": SIGMA_HZ,
        "detection_probability": 0.8 / len(satellites),
        "clutter_rate": CLUTTER_RATE,
        "satellite_indices": satellites,
        "catalog_numbers": np.asarray(data.numbers)[satellites],
        "row_count": int(len(data.measured)),
        "group_count": int(len(np.unique(data.group))),
        "group_values": truth_attempt["group_values"],
        "group_time_s": truth_attempt["group_time_s"],
        "true_position_km": true_position,
        "displaced_optimum_position_km": displaced_vector[:2],
        "position_count": len(positions),
        "attempt_count": int(sum(len(position["attempts"]) for position in positions)),
        "stage_budget_s": STAGE_BUDGET_S,
        "maximum_stage_budget_s": MAX_STAGE_BUDGET_S,
        "maximum_scan_budget_s": MAX_SCAN_BUDGET_S,
        "elapsed_s": elapsed,
        "complete": bool(not failed and elapsed <= MAX_SCAN_BUDGET_S + 2.0),
        "completed_position_count": len(positions) - len(failed),
        "failed_position_labels": failed,
        "unresolved_position_labels": unresolved,
        "positions": positions,
        "source_hashes": source_hashes,
        "protocol_sha256": digest(protocol_path),
        "resource_amendment_sha256": digest(
            ROOT / "position-profile-resource-amendment.json"
        ),
        "truth_start_sha256": digest(
            ROOT / "truth-start-diagnostic" / f"{session}-common-rf-profiled.json"
        ),
        "common_rf_sha256": digest(
            ROOT / "rf-calibration-diagnostic" / f"{session}-common.json"
        ),
        "reference_used_for_fitting": True,
        "scope": (
            "Known-position current-loss control using every stored alias-family "
            "representative GLRT peak row, unchanged groups, original fixed satellite "
            "set, sigma 200 Hz, detection probability 0.8/K, clutter rate 2, timing "
            "priors, RX lines, and one common RF coefficient. Outward and inward warm "
            "chains probe two local nuisance continuations that may reuse one basin; "
            "the retained profile is not a global optimum certificate, blind "
            "localization result, holdout evaluation, or full GLRT response-surface fit."
        ),
    }
    assert_snapshot_unchanged(source_hashes)
    destination.parent.mkdir(exist_ok=True)
    with destination.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {
        "session": session,
        "complete": result["complete"],
        "elapsed_s": elapsed,
        "completed_position_count": result["completed_position_count"],
        "unresolved_position_count": len(unresolved),
        "truth_objective": truth_attempt["objective"],
        "displaced_objective": displaced_attempt["objective"],
    }


def main():
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    protocol = json.loads((ROOT / "position-profile-protocol.json").read_text())
    with ProcessPoolExecutor(max_workers=2) as executor:
        for result in executor.map(run_case, protocol["sessions"]):
            print(json.dumps(serializable(result)), flush=True)


if __name__ == "__main__":
    main()


__all__ = [
    "geodesic_position",
    "position_grid",
    "run_profile",
    "select_best_attempt",
]
