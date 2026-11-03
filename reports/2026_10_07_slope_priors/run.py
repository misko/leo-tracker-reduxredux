"""Matched slope-window experiment on frozen numerical ports, with no storage IO.

Selections use the published objective plus the frozen calibration penalty.
Reference coordinates are accessed only after those selections are fixed.
"""

import argparse
from dataclasses import replace
import hashlib
import inspect
import json
import os
from pathlib import Path
import time

# Set before importing numerical libraries; the CLI never accepts larger budgets.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import numpy as np
from scipy.optimize import nnls

from leo.analysis.regional_position_score import PositionObjective, coordinates
from leo.contracts.regional_position import (
    PositionObservations, PositionOrbitBank, PositionScore, RegionalPrior,
)
from bounded_fit import fit_position

HERE = Path(__file__).resolve().parent
OPTIONS = {"control": None, "window60": 60., "window30": 30., "window10": 10.}
ARMS = ("zero-c", "fitted-c")
SECONDS = 6.
ITERATIONS = 300
LOCAL_RADIUS_KM = 25.


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def vector_digest(vector):
    return digest(np.asarray(vector, dtype="<f8").tobytes())


def encode(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def audit(vector, gradient, objective, arm, center, half_width):
    """Independent physical bounds and scaled KKT audit, including slope bounds."""
    v, g = np.asarray(vector), np.asarray(gradient)
    n = len(v)
    scales = np.r_[1., 1., 200., 2., 200., 2., 200., np.ones(n - 7)]
    free = np.array([i for i in range(n) if arm != "zero-c" or i != 6])
    low, high = np.full(n, -np.inf), np.full(n, np.inf)
    radius = objective.prior.radius_km
    low[:2], high[:2] = -radius, radius
    low[6], high[6], low[7], high[7] = -5000., 5000., -10., 10.
    if half_width is not None:
        low[[3, 5]], high[[3, 5]] = -half_width, half_width
    matrix = np.zeros((len(objective.bank.numbers), n))
    matrix[:, 7], matrix[:, 8:] = 1., objective.basis
    shifts = matrix @ v
    minimum = max(-20., objective.bank.nodes_s[0] - objective.observations.times_s.min())
    maximum = min(20., objective.bank.nodes_s[-1] - objective.observations.times_s.max())
    slacks = np.r_[shifts - minimum, maximum - shifts]
    normals = []
    active_bounds = []
    for j in range(len(shifts)):
        for slack, sign, label in ((shifts[j] - minimum, 1., "lower"),
                                   (maximum - shifts[j], -1., "upper")):
            if slack <= 1e-6:
                normals.append((sign * matrix[j] * scales)[free])
                active_bounds.append(f"shift:{j}:{label}")
    boundary = False
    spatial_slacks = []
    for label, origin, r in (("global", np.zeros(2), radius),
                              ("local", np.asarray(center), LOCAL_RADIUS_KM)):
        delta = v[:2] - origin
        distance = np.linalg.norm(delta)
        slack = float(r * r - delta @ delta)
        spatial_slacks.append(slack)
        boundary |= bool(distance >= r - 1e-4)
        if slack <= 1e-6:
            normal = np.zeros(n)
            normal[:2] = -2 * delta
            normals.append((normal * scales)[free])
            active_bounds.append(f"disk:{label}")
    z = v / scales
    for k, i in enumerate(free):
        for active, sign, label in ((z[i] <= low[i] / scales[i] + 1e-7, 1., "lower"),
                                    (z[i] >= high[i] / scales[i] - 1e-7, -1., "upper")):
            if active:
                normals.append(sign * np.eye(len(free))[k])
                active_bounds.append(f"parameter:{i}:{label}")
    scaled = (g * scales)[free]
    if normals:
        active = np.asarray(normals).T
        multipliers, _ = nnls(active, scaled, maxiter=100 * max(1, active.shape[1]))
        scaled = scaled - active @ multipliers
    stationarity = float(np.max(abs(scaled), initial=0))
    finite_bound_slack = np.r_[(v - low)[np.isfinite(low)], (high - v)[np.isfinite(high)]]
    constraint_slack = float(min(np.min(slacks), min(spatial_slacks)))
    bounds_ok = bool(np.all(v[free] >= low[free] - 1e-7) and np.all(v[free] <= high[free] + 1e-7))
    feasible = bool(constraint_slack >= -1e-6 and bounds_ok and (arm != "zero-c" or v[6] == 0))
    slope_active = [label for label in active_bounds if label.startswith(("parameter:3:", "parameter:5:"))]
    return dict(stationarity=stationarity, converged=bool(feasible and stationarity <= .001),
                feasible=feasible, boundary=boundary, active_bounds=active_bounds,
                slope_active_bounds=slope_active, minimum_constraint_slack=constraint_slack,
                minimum_parameter_bound_slack=float(np.min(finite_bound_slack)),
                shifts_s=shifts.tolist(), relative_shifts_s=(objective.basis @ v[8:]).tolist(),
                common_shift_s=float(v[7]), timing_bounds_s=[float(minimum), float(maximum)],
                slope_bounds_hz_s=None if half_width is None else [-half_width, half_width])


def seeds(initial, arm, half_width):
    """Both shared starts derive only from the frozen association vector."""
    original = np.asarray(initial, float)
    answer = []
    for label in ("association", "zero-timing"):
        v = original.copy()
        if label == "zero-timing":
            v[7:] = 0.
        if arm == "zero-c":
            v[6] = 0.
        if half_width is not None:
            v[[3, 5]] = np.clip(v[[3, 5]], -half_width, half_width)
        shared = original if label == "association" else np.r_[original[:7], np.zeros(len(original)-7)]
        answer.append((label, v, vector_digest(shared)))
    return answer


def load_objective(manifest_dir, case, basin, method):
    region = case["basins"][basin]
    # Frozen manifest paths are relative to the report root ("inputs/...").
    path = manifest_dir.parent / region["file"]
    raw = path.read_bytes()
    if digest(raw) != region["sha256"]:
        raise ValueError(f"fixture digest mismatch: {path}")
    with np.load(path, allow_pickle=False) as data:
        obs = PositionObservations(tuple(data["obs_window_ids"].tolist()),
                                   **{name:data["obs_"+name] for name in
                                      ("times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin")})
        bank = PositionOrbitBank(**{name:data["bank_"+name] for name in
                                    ("numbers", "nodes_s", "position_km", "velocity_km_s")})
        baseline = data["receiver_baseline_hz"].copy()
    score = replace(PositionScore(**case["scores"][method]), relative_sigma_s=1.)
    return PositionObjective(obs, bank, RegionalPrior(**case["prior"]), score,
                             receiver_baseline_hz=baseline)


def candidate(objective, region, vector, option, arm, basin, method, origin, **extra):
    v = np.asarray(vector)
    value, gradient, terms = objective.evaluate(v)
    mass = float(terms.responsibilities.sum())
    common = .5 * (v[7] / objective.score.common_sigma_s) ** 2
    relative = .5 * np.sum((objective.basis @ v[8:]) ** 2)
    linear = {}
    obs = objective.observations
    for rx in (0, 1):
        mask = obs.receiver == rx
        design = np.column_stack([np.ones(mask.sum()), obs.times_s[mask] - obs.time_center_s,
                                  (obs.rf_hz[mask] - obs.rf_center_hz) / 1e9])
        coef = np.linalg.lstsq(design, objective.baseline[mask], rcond=None)[0]
        linear[str(rx)] = float(coef[1])
    calibration_slopes = np.asarray(region["calibration_vector"])[[3, 5]]
    return dict(option=option, arm=arm, basin=basin, method=method, origin=origin,
                vector=v.tolist(), objective=float(value),
                selection_score=float(value + region["calibration_penalty"]),
                calibration_penalty=float(region["calibration_penalty"]), data_nll=float(terms.nll),
                timing_penalty=float(value - terms.nll), common_timing_penalty=float(common),
                relative_timing_penalty=float(relative), signal_mass=mass,
                signal_fraction=mass/len(obs.window_ids),
                posterior_rms_hz=float(np.sqrt(np.sum(terms.responsibilities * terms.residual_hz**2)/mass)) if mass>1e-12 else None,
                mean_clutter_posterior=float(terms.clutter_probability.mean()),
                c_hz_per_ghz=float(v[6]), additional_slopes_hz_s=[float(v[3]), float(v[5])],
                calibration_postfit_slopes_hz_s=calibration_slopes.tolist(),
                total_linear_slopes_hz_s=(calibration_slopes+v[[3, 5]]).tolist(),
                frozen_baseline_regressed_slopes_hz_s=linear,
                calibration_fields=region["calibration_fields"], calibration_vector=region["calibration_vector"],
                **audit(v, gradient, objective, arm, region["center_km"], OPTIONS[option]), **extra)


def select(candidates, case, method, arm):
    return min((r for r in candidates if r["case"]==case and r["method"]==method and r["arm"]==arm),
               key=lambda r:(r["selection_score"], r["basin"], r["origin"]))


def run(option, destination, manifest_path=HERE/"inputs/manifest.json"):
    if option not in OPTIONS:
        raise ValueError(option)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    completed, progress = destination/"results.json", destination/"progress.json"
    if completed.exists() or progress.exists():
        raise FileExistsError("existing experiment receipt; use a fresh output directory")
    begun = time.monotonic()
    raw = Path(manifest_path).read_bytes()
    manifest = json.loads(raw)
    output = dict(status="running", option=option, slope_half_width_hz_s=OPTIONS[option],
                  manifest_sha256=digest(raw), seconds_per_fit=SECONDS, maximum_iterations=ITERATIONS,
                  protocol_sha256=digest((HERE/"protocol.txt").read_bytes()),
                  local_radius_km=LOCAL_RADIUS_KM, relative_sigma_s=1., blas_threads=1,
                  source_hashes={str(p):digest(p.read_bytes()) for p in
                                 (Path(__file__), HERE/"bounded_fit.py", Path(inspect.getfile(PositionObjective)))},
                  runs=[], candidates=[], seeds=[], selections=[], cases=[], nested_search_gaps=[])
    def save():
        temporary = progress.with_suffix(".tmp")
        temporary.write_text(json.dumps(output, indent=2, default=encode)+"\n")
        temporary.replace(progress)
    save()
    for case in manifest["cases"]:
        case_id = case["case"]
        output["cases"].append({key:value for key,value in case.items() if key != "evaluation_reference"})
        for method, basins in case["methods"].items():
            for basin in basins:
                region = case["basins"][basin]
                objective = load_objective(Path(manifest_path).parent, case, basin, method)
                for arm in ARMS:
                    for label, seed, shared_digest in seeds(region["initial_vector"], arm, OPTIONS[option]):
                        metadata = dict(case=case_id, fixture_sha256=region["sha256"],
                                        association_seed_sha256=vector_digest(region["initial_vector"]),
                                        shared_seed_sha256=shared_digest, seed_sha256=vector_digest(seed))
                        initial_audit = audit(seed, np.zeros(objective.size), objective, arm,
                                              region["center_km"], OPTIONS[option])
                        output["seeds"].append(dict(method=method, basin=basin, arm=arm, origin=label,
                                                     vector=seed.tolist(), initial_feasible=initial_audit["feasible"],
                                                     **metadata))
                        if initial_audit["feasible"]:
                            initial = candidate(objective, region, seed, option, arm, basin, method,
                                                "initial:"+label, **metadata)
                            output["candidates"].append(initial)
                        try:
                            result = fit_position(objective, seed.copy(), rf_arm=arm,
                                                  maximum_seconds=SECONDS, maximum_iterations=ITERATIONS,
                                                  local_center=np.asarray(region["center_km"]),
                                                  local_radius_km=LOCAL_RADIUS_KM,
                                                  slope_half_width_hz_s=OPTIONS[option])
                        except (TimeoutError, ValueError, ArithmeticError) as error:
                            output["runs"].append(dict(option=option, arm=arm, basin=basin, method=method,
                                                        origin="fit:"+label, status="failed", vector=seed.tolist(),
                                                        elapsed_s=None, error_type=type(error).__name__,
                                                        error=str(error), **metadata))
                            save()
                            print(case_id, method, basin, arm, label, "FAILED", repr(error), flush=True)
                            continue
                        row = candidate(objective, region, result.vector, option, arm, basin, method,
                                        "fit:"+label, elapsed_s=result.elapsed_s,
                                        status="complete",
                                        evaluations=result.evaluations, stop_reason=result.stop_reason,
                                        solver_stationarity=result.stationarity, **metadata)
                        if abs(row["objective"]-result.objective)>1e-6 or abs(row["stationarity"]-result.stationarity)>1e-5:
                            raise AssertionError("independent fit audit disagrees")
                        output["runs"].append(row)
                        if row["feasible"]:
                            output["candidates"].append(row)
                        save()
                        print(case_id, method, basin, arm, label, round(row["selection_score"], 3), row["converged"], flush=True)
            for arm in ARMS:
                output["selections"].append(select(output["candidates"], case_id, method, arm))
            zero, free = [select(output["candidates"], case_id, method, arm) for arm in ARMS]
            gap = max(0., free["selection_score"]-zero["selection_score"])
            output["nested_search_gaps"].append(dict(case=case_id, method=method, gap=gap,
                                                       incomplete_search=bool(gap>1e-6)))
        # Reference coordinates first accessed after all score selections for this case.
        reference = case["evaluation_reference"]
        if isinstance(reference, dict):
            reference = [reference["latitude_deg"], reference["longitude_deg"]]
        for row in output["candidates"]:
            if row["case"] != case_id:
                continue
            lat, lon = np.radians(coordinates(RegionalPrior(**case["prior"]), row["vector"][:2]))
            a, b = np.radians(reference)
            h = np.sin((lat-a)/2)**2 + np.cos(lat)*np.cos(a)*np.sin((lon-b)/2)**2
            row["horizontal_error_m"] = float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))
        save()
    output.update(status="complete", elapsed_s=time.monotonic()-begun,
                  fit_elapsed_s=sum(row["elapsed_s"] or 0. for row in output["runs"]))
    save()
    completed.write_text(json.dumps(output, indent=2, default=encode)+"\n")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--option", choices=OPTIONS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.option, args.output)
