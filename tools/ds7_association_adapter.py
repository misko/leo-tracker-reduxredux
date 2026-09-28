#!/usr/bin/env python3
"""Matched-budget local and multibasin wrappers for the DS7 baseline model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from tools import ds7_baseline_adapter as baseline


def frozen_starts(policy: str, recordings: int) -> list[np.ndarray]:
    if policy == "local":
        return [np.r_[0.0, 0.0, [tau] * recordings] for tau in (0.0, -2.0, 2.0)]
    if policy == "multibasin":
        positions = (
            (0.0, 0.0),
            (-8.0, -8.0),
            (-8.0, 0.0),
            (-8.0, 8.0),
            (0.0, -8.0),
            (0.0, 8.0),
            (8.0, -8.0),
            (8.0, 0.0),
            (8.0, 8.0),
        )
        return [np.r_[east, north, [0.0] * recordings] for east, north in positions]
    raise ValueError(f"unknown search policy: {policy}")


def reverse_trajectory_time(documents: list[dict]) -> list[dict]:
    """Build a physically mismatched control while retaining membership and shapes."""
    output = []
    for document in documents:
        changed = dict(document)
        changed["tracks"] = []
        for source in document["tracks"]:
            track = dict(source)
            track["candidate_position_km"] = source["candidate_position_km"][:, :, ::-1].copy()
            track["candidate_velocity_km_s"] = source["candidate_velocity_km_s"][:, :, ::-1].copy()
            changed["tracks"].append(track)
        output.append(changed)
    return output


def permute_candidate_rows(documents: list[dict]) -> list[dict]:
    """Permutation-invariance control: reorder complete mixture rows only."""
    output = []
    for document in documents:
        changed = dict(document)
        changed["tracks"] = []
        for source in document["tracks"]:
            track = dict(source)
            track["candidate_position_km"] = source["candidate_position_km"][::-1].copy()
            track["candidate_velocity_km_s"] = source["candidate_velocity_km_s"][::-1].copy()
            changed["tracks"].append(track)
        output.append(changed)
    return output


def winning_run_index(runs) -> int:
    """Select by scalar objective without comparing array-bearing results."""
    return min(range(len(runs)), key=lambda index: float(runs[index].fun))


def estimate(request: dict) -> dict:
    base = {"schema": "ds7-response/v1", "unit_id": request["unit"]["unit_id"]}
    documents = baseline.load_documents(request)
    if any(not document.get("tracks") for document in documents):
        return {**base, "status": "abstained", "reason": "no qualified frozen tracks"}
    config = request["config"]
    policy = config["search_policy"]
    starts = frozen_starts(policy, len(documents))
    configured_starts = [np.asarray(row, dtype=float) for row in config["frozen_starts"]]
    if len(configured_starts) != len(starts) or any(
        not np.array_equal(configured, generated)
        for configured, generated in zip(configured_starts, starts, strict=True)
    ):
        raise ValueError("request starts differ from frozen search policy")
    if float(config["canonical_rf_hz"]) != baseline.REFERENCE_RF_HZ:
        raise ValueError("prediction carrier differs from normalized measurement carrier")
    total_cap = int(config["total_nfev_cap"])
    per_start_cap = int(config["per_start_nfev_cap"])
    if len(starts) * per_start_cap != total_cap:
        raise ValueError("frozen starts and per-start cap must exactly allocate total nfev cap")
    objective = baseline.JointObjective(documents, config)
    bounds = [tuple(config["position_bounds_km"])] * 2 + [tuple(config["timing_bounds_s"])] * len(
        documents
    )
    runs = []
    for start in starts:
        fit = minimize(
            objective.value_gradient,
            start,
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={
                "maxiter": per_start_cap,
                "maxfun": per_start_cap,
                "ftol": 1e-10,
                "gtol": 1e-5,
                "maxls": 10,
            },
        )
        runs.append(fit)
    total_nfev = sum(int(run.nfev) for run in runs)
    if total_nfev > total_cap:
        raise RuntimeError("optimizer exceeded frozen total evaluation cap")
    winning_index = winning_run_index(runs)
    fit = runs[winning_index]
    lat, lon = objective.coordinates(fit.x)
    boundary = any(
        abs(value - lower) < 1e-3 or abs(value - upper) < 1e-3
        for value, (lower, upper) in zip(fit.x, bounds, strict=True)
    )
    run_rows = [
        {
            "start": start.tolist(),
            "objective": -float(run.fun),
            "nfev": int(run.nfev),
            "converged": bool(run.success),
            "message": str(run.message),
            "x": run.x.tolist(),
        }
        for start, run in zip(starts, runs, strict=True)
    ]
    return {
        **base,
        "status": "ok",
        "estimate": {"latitude_deg": lat, "longitude_deg": lon},
        "converged": bool(fit.success),
        "boundary_hit": bool(boundary),
        "diagnostics": {
            "solver": "ds7_matched_budget_association_search_v1",
            "search_policy": policy,
            "train_log_likelihood": -float(fit.fun),
            "total_nfev": total_nfev,
            "total_nfev_cap": total_cap,
            "per_start_nfev_cap": per_start_cap,
            "start_count": len(starts),
            "winning_start_index": winning_index,
            "east_north_km": fit.x[:2].tolist(),
            "timing_offsets_s": fit.x[2:].tolist(),
            "runs": run_rows,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    result = estimate(json.loads(args.request.read_text()))
    with args.response.open("x") as stream:
        json.dump(result, stream, allow_nan=False)


if __name__ == "__main__":
    main()
