#!/usr/bin/env python3
"""Iteration-6B: fixed candidate-union exact session-scale ablation.

Consumes the completed iteration-4 union verbatim.  At each fixed candidate it
jointly profiles bounded causal per-NORAD phase rates, a per-track CFO, and a
common-plus-session fractional Doppler scale hierarchy.  No reference data is
available to this program.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ITER4 = ROOT / "reports/2026_09_24_ds1_joint_rate_search/iteration4-results.json"
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
SOURCE = ROOT / "reports/2026_09_24_ds1_train_full/artifacts/one-hour/global_time"
RATE_SIGMA = 0.09176615913014215
RATE_BOUND = 0.25
SCALE_SIGMA = 5e-4
SESSION_DEVIATION_SIGMA = 5e-4
SCALE_BOUND = 0.002
MAXITER = 500


def digest(p: Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


def load(p: Path, n: str) -> Any:
    s = importlib.util.spec_from_file_location(n, p)
    m = importlib.util.module_from_spec(s)
    sys.modules[n] = m
    s.loader.exec_module(m)
    return m


def task(group: str) -> dict[str, Any]:
    s = json.loads(
        (SOURCE / f"one-hour--train-{group}--prefix-6--reno--global_time.json").read_text()
    )
    if s.get("reference_used_for_fit") is not False or s.get("partition") != "train":
        raise ValueError("invalid sealed source")
    return {
        "task_id": "iteration6b-" + group,
        "group_id": group,
        "session_ids": s["session_ids"],
        "session_groups": s["session_groups"],
        "prior": s["prior"],
        "method": "global_tau_per_norad_orbit_rate",
        "output_path": str(HERE / "unused.json"),
        "options": {},
    }


def capped(error, track, weights):
    return sum(
        weights[str(k)] * min((float(np.sqrt(np.mean(error[track == k] ** 2))) / 800.0) ** 2, 1.0)
        for k in np.unique(track)
    ) / sum(weights.values())


def audit(arg):
    group, candidate = arg
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    existing = load(RUNNER, "i6b_existing_" + str(os.getpid()))
    orbit = load(ORBIT, "i6b_orbit_" + str(os.getpid()))
    engine = existing.FullObservationEngine(existing.validate_task(task(group)))
    begun = time.perf_counter()
    data = existing._make_exact_prepared(
        engine,
        orbit,
        candidate["latitude_deg"],
        candidate["longitude_deg"],
        candidate["tau_s"],
        candidate["track_associations"],
    )
    receiver, _ = engine.search.receiver_ecef(candidate["latitude_deg"], candidate["longitude_deg"])
    src, si = np.unique(data.source.astype(str), return_inverse=True)
    sess, ssi = np.unique(data.session.astype(str), return_inverse=True)
    trk, ti = np.unique(data.track.astype(str), return_inverse=True)

    def evaluate(x):
        rates = x[: len(src)]
        common = x[len(src)]
        dev = x[len(src) + 1 :]
        phase = data.age_h * rates[si]
        base = orbit.doppler(
            receiver,
            orbit.quartic(data.p_nodes, phase),
            orbit.quartic(data.v_nodes, phase),
            engine.search,
        )
        predicted = (1 + common + dev[ssi]) * base
        raw = data.y - predicted
        cfo = np.asarray([raw[ti == i].mean() for i in range(len(trk))])
        return raw - cfo[ti], rates, common, dev

    def objective(x):
        error, rates, common, dev = evaluate(x)
        z = error / 250.0
        return float(
            np.sum(np.sqrt(1 + z * z) - 1)
            + 0.5 * np.sum((rates / RATE_SIGMA) ** 2)
            + 0.5 * (common / SCALE_SIGMA) ** 2
            + 0.5 * np.sum((dev / SESSION_DEVIATION_SIGMA) ** 2)
        )

    x0 = np.zeros(len(src) + 1 + len(sess))
    bounds = [(-RATE_BOUND, RATE_BOUND)] * len(src) + [(-SCALE_BOUND, SCALE_BOUND)] * (
        1 + len(sess)
    )
    opt = minimize(
        objective,
        x0,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": MAXITER, "maxls": 100, "ftol": 1e-11, "gtol": 1e-7},
    )
    err, rates, common, dev = evaluate(np.asarray(opt.x))
    loss = capped(err, data.track.astype(str), data.weights)
    null_err, _, _, _ = evaluate(x0)
    null_loss = capped(null_err, data.track.astype(str), data.weights)
    rate_only_loss = float(candidate["exact_comparison"]["exact_full_observation_capped_loss"])
    improved_over_rate_only = bool(loss < rate_only_loss - 1e-12)
    selected = bool(opt.success and improved_over_rate_only)
    reaches = bool(np.any(np.abs(np.r_[common, dev]) >= SCALE_BOUND - 1e-8))
    return {
        "group_id": group,
        "latitude_deg": candidate["latitude_deg"],
        "longitude_deg": candidate["longitude_deg"],
        "tau_s": candidate["tau_s"],
        "selection_origin": candidate["selection_origin"],
        "exact_capped_loss": float(loss),
        "zero_rate_scale_exact_capped_loss": float(null_loss),
        "input_rate_only_exact_capped_loss": rate_only_loss,
        "improved_over_rate_only": improved_over_rate_only,
        "selected": selected,
        "converged": bool(opt.success),
        "solver_message": str(opt.message),
        "iterations": int(opt.nit),
        "rate_boundary_count": int(np.sum(np.abs(rates) >= RATE_BOUND - 1e-8)),
        "common_scale": float(common),
        "session_deviations": {str(k): float(v) for k, v in zip(sess, dev, strict=True)},
        "scale_reaches_guard": reaches,
        "rates": {str(k): float(v) for k, v in zip(src, rates, strict=True)},
        "elapsed_s": time.perf_counter() - begun,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    if not 1 <= a.workers <= 4:
        raise ValueError("workers must be 1..4")
    d = json.loads(ITER4.read_text())
    if d.get("complete") is not True or d.get("reference_used_for_fit") is not False:
        raise ValueError("invalid iteration4 input")
    jobs = [(row["group_id"], c) for row in d["results"] for c in row["candidates"]]
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=a.workers, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        rows = list(pool.map(audit, jobs, chunksize=1))
    groups = []
    for group in sorted({r["group_id"] for r in rows}):
        candidates = [r for r in rows if r["group_id"] == group]
        winner = min(
            candidates,
            key=lambda r: (
                r["exact_capped_loss"],
                abs(r["tau_s"]),
                r["tau_s"],
                r["latitude_deg"],
                r["longitude_deg"],
            ),
        )
        groups.append({"group_id": group, "candidates": candidates, "winner": winner})
    portable = all(
        g["winner"]["selected"] and not g["winner"]["scale_reaches_guard"] for g in groups
    )
    out = {
        "schema": "ds1-iteration6b-hierarchical-session-scale/v1",
        "complete": True,
        "partition": "train",
        "reference_used_for_fit": False,
        "candidate_input": {"path": str(ITER4), "sha256": digest(ITER4)},
        "model": {
            "rate_sigma_s_h": RATE_SIGMA,
            "rate_bound_s_h": RATE_BOUND,
            "common_scale_sigma": SCALE_SIGMA,
            "session_deviation_sigma": SESSION_DEVIATION_SIGMA,
            "scale_guard": SCALE_BOUND,
            "max_iterations": MAXITER,
        },
        "portability_accepted": portable,
        "portability_rule": (
            "each group winner converges, improves its matched exact rate-only input, "
            "and no selected scale reaches guard"
        ),
        "groups": groups,
        "bindings": {
            "driver": digest(Path(__file__)),
            "runner": digest(RUNNER),
            "orbit": digest(ORBIT),
        },
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(a.output), "portable": portable}))


if __name__ == "__main__":
    main()
