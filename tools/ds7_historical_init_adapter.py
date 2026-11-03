#!/usr/bin/env python3
"""DS7 exact baseline with a predeclared historical-style initialization."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
from pathlib import Path

import ds7_baseline_adapter as baseline
import ds7_fast_baseline_adapter as fast
import numpy as np
import scipy
from scipy.optimize import minimize


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_initialization(config: dict, expected_session_ids: list[str]):
    bindings = config["single_fit_bindings"]
    expected_count = len(expected_session_ids)
    if len(bindings) != expected_count:
        raise ValueError("one qualified single-fit binding required per recording")
    xyz = np.zeros(3)
    taus = []
    seen = set()
    for binding, expected_session_id in zip(bindings, expected_session_ids, strict=True):
        response_path = Path(binding["response_path"])
        request_path = Path(binding["request_path"])
        seal_path = Path(binding["seal_path"])
        if (
            digest(response_path) != binding["response_sha256"]
            or digest(request_path) != binding["request_sha256"]
            or digest(seal_path) != binding["seal_sha256"]
        ):
            raise ValueError("single-fit source or seal digest changed")
        seal = json.loads(seal_path.read_text())
        try:
            response_name = str(response_path.relative_to(seal_path.parent))
            request_name = str(request_path.relative_to(seal_path.parent))
        except ValueError as exc:
            raise ValueError("single-fit source is outside its sealed run") from exc
        if (
            seal.get("schema") != "ds7-run-seal/v1"
            or seal.get("files", {}).get(response_name) != binding["response_sha256"]
            or seal.get("files", {}).get(request_name) != binding["request_sha256"]
        ):
            raise ValueError("single-fit request/response is not bound by its seal")
        response = json.loads(response_path.read_text())
        source_request = json.loads(request_path.read_text())
        source_sessions = source_request.get("unit", {}).get("session_ids")
        if (
            response.get("unit_id") != binding["unit_id"]
            or source_request.get("unit", {}).get("unit_id") != binding["unit_id"]
            or source_sessions != [expected_session_id]
            or binding.get("session_id") != expected_session_id
            or response.get("status") != "ok"
            or response.get("converged") is not True
            or response.get("boundary_hit") is not False
            or binding["unit_id"] in seen
        ):
            raise ValueError("single-fit initialization source is unqualified or duplicated")
        seen.add(binding["unit_id"])
        lat = math.radians(response["estimate"]["latitude_deg"])
        lon = math.radians(response["estimate"]["longitude_deg"])
        xyz += [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
        offsets = response["diagnostics"]["timing_offsets_s"]
        if len(offsets) != 1 or not math.isfinite(offsets[0]):
            raise ValueError("single fit does not provide one finite timing offset")
        taus.append(float(offsets[0]))
    if np.linalg.norm(xyz) < 1e-12 * expected_count:
        raise ValueError("ambiguous independent-estimate spherical mean")
    latitude = math.degrees(math.atan2(xyz[2], math.hypot(xyz[0], xyz[1])))
    longitude = math.degrees(math.atan2(xyz[1], xyz[0]))
    center = config["geographic_prior_center_deg"]
    north = (latitude - center[0]) * 111.195
    east = (longitude - center[1]) * 111.195 * math.cos(math.radians(center[0]))
    return np.asarray([east, north, *taus]), np.asarray([0.0, 0.0, *taus])


def estimate(request: dict) -> dict:
    base = {"schema": "ds7-response/v1", "unit_id": request["unit"]["unit_id"]}
    documents = fast.load_documents(request)
    if any(not document.get("tracks") for document in documents):
        return {**base, "status": "abstained", "reason": "no qualified frozen tracks"}
    starts = load_initialization(
        request["config"], [document["session_id"] for document in documents]
    )
    objective = fast.JointObjective(documents, request["config"])
    bounds = [tuple(request["config"]["position_bounds_km"])] * 2 + [
        tuple(request["config"]["timing_bounds_s"])
    ] * len(documents)
    original_profile = baseline.profile
    baseline.profile = fast.profile
    try:
        runs = [
            minimize(
                objective.value_gradient,
                start,
                method="L-BFGS-B",
                jac=True,
                bounds=bounds,
                options={
                    "maxiter": 100,
                    "maxfun": 180,
                    "ftol": 1e-10,
                    "gtol": 1e-5,
                    "eps": 1e-4,
                    "maxls": 30,
                },
            )
            for start in starts
        ]
    finally:
        baseline.profile = original_profile
    fit = min(runs, key=lambda run: run.fun)
    lat, lon = objective.coordinates(fit.x)
    boundary = any(
        abs(value - low) < 1e-3 or abs(value - high) < 1e-3
        for value, (low, high) in zip(fit.x, bounds, strict=True)
    )
    rms = fast.training_rms_hz(documents, request["config"], fit.x)
    return {
        **base,
        "status": "ok",
        "estimate": {"latitude_deg": lat, "longitude_deg": lon},
        "converged": bool(fit.success),
        "boundary_hit": bool(boundary),
        "rf_rms_hz": rms,
        "diagnostics": {
            "solver": "corrected_ds6_stationary_joint_historical_initialization",
            "train_log_likelihood": -float(fit.fun),
            "recordings": len(documents),
            "tracks": sum(len(document["tracks"]) for document in documents),
            "nfev": int(fit.nfev),
            "total_nfev": sum(int(run.nfev) for run in runs),
            "starts": [
                {
                    "kind": kind,
                    "nfev": int(run.nfev),
                    "success": bool(run.success),
                    "objective": -float(run.fun),
                }
                for kind, run in zip(
                    ("independent_spherical_mean", "donor_center"), runs, strict=True
                )
            ],
            "east_north_km": fit.x[:2].tolist(),
            "timing_offsets_s": fit.x[2:].tolist(),
            "rf_rms_hz": rms,
            "track_eligibility_exclusions": [
                {
                    "session_id": document["session_id"],
                    "count": len(document["eligibility_exclusions"]),
                    "tracks": document["eligibility_exclusions"],
                }
                for document in documents
            ],
            "runtime": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "scipy": scipy.__version__,
            },
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    result = estimate(json.loads(args.request.read_text()))
    with args.response.open("x") as stream:
        json.dump(result, stream, allow_nan=False)


if __name__ == "__main__":
    main()
