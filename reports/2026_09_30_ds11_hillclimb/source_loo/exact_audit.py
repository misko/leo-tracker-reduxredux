#!/usr/bin/env python3
"""Exact local deletion refits selected by the frozen source influence diagnostic."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOLS = ROOT / "tools"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
STEPS = np.asarray((1e-4, 1e-4, 1e-5), dtype=float)
MAX_WORKERS = 3

sys.path.insert(0, str(TOOLS))
import ds7_fast_baseline_adapter as fast  # noqa: E402


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_phase1(index):
    result_path = HERE / "runs" / "phase1" / f"{index:02d}.json"
    receipt_path = result_path.with_suffix(".receipt.json")
    result = json.loads(result_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    if result.get("schema") != "ds11-source-loo-influence-phase1/v1":
        raise ValueError("phase-one schema mismatch")
    if result.get("index") != index or receipt.get("index") != index or receipt.get("exit_code") != 0:
        raise ValueError("phase-one result/receipt mismatch")
    for path, expected in result["sources"].items():
        if digest(path) != expected:
            raise ValueError(f"phase-one bound source changed: {path}")
    if receipt.get("diagnose_sha256") != digest(HERE / "diagnose.py"):
        raise ValueError("phase-one diagnostic source binding mismatch")
    if receipt.get("protocol_sha256") != digest(HERE / "PROTOCOL.md"):
        raise ValueError("phase-one protocol binding mismatch")
    return result_path, receipt_path, result


def selected_jobs(phase1):
    jobs = []
    for family in phase1["families"]:
        selection = family["selection"]
        if not selection.get("selection_complete"):
            raise ValueError(f"incomplete phase-one selection for {family['family']}")
        for rank, key in (("largest", "largest_norad"), ("lower_median", "lower_median_norad")):
            norad = selection.get(key)
            if norad is None:
                raise ValueError("missing frozen selected source")
            jobs.append({"family": family["family"], "rank": rank, "norad": int(norad)})
    if len(jobs) != 8:
        raise ValueError("each scan must freeze exactly eight audit jobs")
    return jobs


def common_held_score(document, track_indices, x, config=None, *, stationary_factory=None,
                      profile_fn=None):
    """Original t4/100 held score with each candidate CFO fitted on training only."""
    factory = stationary_factory or fast.baseline.Stationary
    profiler = profile_fn or fast.profile
    engine = factory(document, config or {})
    total = 0.0
    observations = 0
    for index in track_indices:
        track = document["tracks"][index]
        prediction, visible = engine.prediction(track, np.asarray(x, dtype=float))
        train, joint, audits, _ = profiler(track["y"][None, :] - prediction, track["mask"])
        if not all(audit["converged"] for audit in audits):
            raise RuntimeError("common held scorer CFO profile failed")
        train_normal = float(logsumexp(np.where(visible, train, -np.inf)))
        joint_normal = float(logsumexp(np.where(visible, joint, -np.inf)))
        if not np.isfinite(train_normal) or not np.isfinite(joint_normal):
            raise ValueError("common held scorer has no visible finite candidate")
        total += joint_normal - train_normal
        observations += int((~np.asarray(track["mask"], dtype=bool)).sum())
    return {"score": float(total), "held_observation_count": observations}


def qualify(result, model, bounds):
    x = np.asarray(result.x, dtype=float)
    gradient = -np.asarray(result.jac, dtype=float)
    finite = bool(np.isfinite(x).all() and np.isfinite(gradient).all() and np.isfinite(result.fun))
    boundary = bool(np.any(x - bounds[:, 0] < 0.001) or np.any(bounds[:, 1] - x < 0.001))
    maximum = float(np.max(np.abs(gradient))) if finite else None
    discrepancies = []
    if finite:
        for axis, step in enumerate(STEPS):
            delta = np.zeros(3)
            delta[axis] = step
            numerical = (
                model.evaluate(x + delta, gradient=False)["score"]
                - model.evaluate(x - delta, gradient=False)["score"]
            ) / (2.0 * step)
            discrepancies.append(abs(float(numerical - gradient[axis])))
    audit = max(discrepancies, default=math.inf)
    qualified = bool(result.success and finite and not boundary and maximum <= 0.01 and audit <= 0.02)
    return {
        "qualified": qualified,
        "success": bool(result.success),
        "message": str(result.message),
        "boundary": boundary,
        "gradient_max_abs": maximum,
        "gradient_audit_max_abs": float(audit) if np.isfinite(audit) else None,
    }


def comparison(exact_x, influence_x, full_x, exact_held, influence_held):
    exact_x = np.asarray(exact_x, dtype=float)
    influence_x = np.asarray(influence_x, dtype=float)
    full_x = np.asarray(full_x, dtype=float)
    exact_shift = float(np.linalg.norm(exact_x[:2] - full_x[:2]))
    en_discrepancy = float(np.linalg.norm(exact_x[:2] - influence_x[:2]))
    en_limit = max(0.05, 0.10 * exact_shift)
    time_discrepancy = float(abs(exact_x[2] - influence_x[2]))
    held_discrepancy = float(abs(exact_held - influence_held))
    return {
        "exact_en_shift_km": exact_shift,
        "en_discrepancy_km": en_discrepancy,
        "en_limit_km": en_limit,
        "time_discrepancy_s": time_discrepancy,
        "time_limit_s": 0.02,
        "held_score_discrepancy_nat": held_discrepancy,
        "held_score_limit_nat": 0.1,
        "passes_tolerances": bool(
            en_discrepancy <= en_limit and time_discrepancy <= 0.02 and held_discrepancy <= 0.1
        ),
    }


def run_one(index, family_name, norad, output):
    started = time.monotonic()
    fast.baseline.profile = fast.profile
    diagnose = load_module("ds11_source_loo_frozen_diagnose", HERE / "diagnose.py")
    phase_path, phase_receipt, phase = validate_phase1(index)
    frozen_jobs = selected_jobs(phase)
    matching_jobs = [job for job in frozen_jobs if job["family"] == family_name and job["norad"] == norad]
    if not matching_jobs:
        raise ValueError("job was not selected by frozen phase one")
    plan_path, plan, entry, documents, sidecar_path, candidate_norad = diagnose.validate_inputs(index)
    source_module = diagnose.load_module("ds11_source_loo_exact_source", diagnose.HILL / "source_balance" / "model.py")
    robust_module = diagnose.load_module("ds11_source_loo_exact_robust", diagnose.HILL / "robust" / "model.py")
    modules = {"source": source_module, "robust": robust_module}
    iid_result = json.loads(diagnose.FAMILIES["iid_t4_scale100"]["result"](index).read_text())
    assignments = source_module.freeze_assignments(
        documents, plan["config"], np.asarray(iid_result["selected"]["x"]), candidate_norad
    )
    phase_assignments = phase["assignments"]
    comparable = [(row["track_id"], row["norad"], row["unambiguous"], row["confidence"])
                  for row in assignments]
    frozen_comparable = [(row["track_id"], row["norad"], row["unambiguous"], row["confidence"])
                         for row in phase_assignments]
    if comparable != frozen_comparable:
        raise ValueError("recomputed assignment differs from frozen phase one")
    family = diagnose.FAMILIES[family_name]
    endpoint_path, endpoint_receipt, endpoint_result, full_x, endpoint_score, embedded = diagnose.load_endpoint(
        family_name, family, index, entry["session_id"]
    )
    del endpoint_result, endpoint_score
    selected_indices = [i for i, row in enumerate(assignments)
                        if row["unambiguous"] and row["norad"] == norad]
    if len(selected_indices) < 2:
        raise ValueError("selected NORAD is not an eligible repeated source")
    retained_indices = [i for i in range(len(assignments)) if i not in set(selected_indices)]
    retained_doc = diagnose.subset_document(documents[0], retained_indices)
    full_weights = source_module.derive_weights(assignments, "source_receiver_equal")
    if family["kind"] == "source":
        retained_weights = full_weights[retained_indices]
        retained_assignments = [assignments[i] for i in retained_indices]
    else:
        retained_weights = retained_assignments = None
    model = diagnose.build_evaluator(
        family["kind"], family["variant"], retained_doc, plan["config"], modules,
        weights=retained_weights, assignments=retained_assignments,
    )
    bounds = diagnose.BOUNDS.copy()

    def objective(x):
        evaluated = model.evaluate(x, gradient=True)
        return -float(evaluated["score"]), -np.asarray(evaluated["gradient"], dtype=float)

    result = minimize(
        objective, full_x, jac=True, method="L-BFGS-B", bounds=bounds.tolist(),
        options={"maxiter": 100, "maxfun": 160, "ftol": 1e-13, "gtol": 1e-6, "maxls": 25},
    )
    qualification = qualify(result, model, bounds)
    phase_family = next(row for row in phase["families"] if row["family"] == family_name)
    fold = next(row for row in phase_family["folds"] if row["norad"] == norad)
    influence_x = np.asarray(fold["estimate"], dtype=float)
    exact_held = common_held_score(
        documents[0], selected_indices, result.x, plan["config"],
    )
    influence_held = common_held_score(
        documents[0], selected_indices, influence_x, plan["config"],
    )
    audit_comparison = comparison(
        result.x, influence_x, full_x, exact_held["score"], influence_held["score"]
    )
    sources = {
        str(HERE / "exact_audit.py"): digest(HERE / "exact_audit.py"),
        str(HERE / "EXACT_PROTOCOL.md"): digest(HERE / "EXACT_PROTOCOL.md"),
        str(HERE / "diagnose.py"): digest(HERE / "diagnose.py"),
        str(HERE / "PROTOCOL.md"): digest(HERE / "PROTOCOL.md"),
        str(phase_path): digest(phase_path),
        str(phase_receipt): digest(phase_receipt),
        str(plan_path): digest(plan_path),
        str(sidecar_path): digest(sidecar_path),
        str(endpoint_path): digest(endpoint_path),
        str(endpoint_receipt): digest(endpoint_receipt),
        **embedded,
    }
    record = {
        "schema": "ds11-source-loo-exact-audit/v1",
        "index": index,
        "session_id": entry["session_id"],
        "family": family_name,
        "variant": family["variant"],
        "norad": norad,
        "selection_ranks": sorted(job["rank"] for job in matching_jobs),
        "training_only_refit": True,
        "reference_used": False,
        "full_endpoint_x": full_x.tolist(),
        "influence_x": influence_x.tolist(),
        "exact_x": np.asarray(result.x).tolist(),
        "exact_score": float(-result.fun),
        "source_track_indices": selected_indices,
        "source_track_ids": [assignments[i]["track_id"] for i in selected_indices],
        "retained_track_count": len(retained_indices),
        "source_weights_preserved_without_renormalization": family["kind"] == "source",
        "optimizer": {
            **qualification,
            "nfev": int(result.nfev),
            "nit": int(result.nit),
        },
        "exact_common_held": exact_held,
        "influence_common_held": influence_held,
        "comparison": audit_comparison,
        "audit_pass": bool(qualification["qualified"] and audit_comparison["passes_tolerances"]),
        "sources": sources,
        "elapsed_s": time.monotonic() - started,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
    print(json.dumps({"index": index, "family": family_name, "norad": norad,
                      "qualified": qualification["qualified"],
                      "audit_pass": record["audit_pass"], "elapsed_s": record["elapsed_s"]}), flush=True)


def launch_job(index, family, norad):
    folder = HERE / "runs" / "exact_audit"
    folder.mkdir(parents=True, exist_ok=True)
    base = folder / f"{index:02d}_{family}_{norad}"
    output = base.with_suffix(".json")
    log = base.with_suffix(".log")
    receipt = base.with_suffix(".receipt.json")
    if receipt.exists():
        return {"existing": True, **json.loads(receipt.read_text())}
    if output.exists() or log.exists():
        raise RuntimeError(f"unreceipted audit attempt requires review: {base}")
    command = [
        "sudo", "-n", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
        "MKL_NUM_THREADS=1", "timeout", "--kill-after=5s", "90s", "nice", "-n", "19",
        PYTHON, str(HERE / "exact_audit.py"), "one", str(index), family, str(norad), str(output),
    ]
    started = time.monotonic()
    with log.open("x") as stream:
        completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    row = {
        "index": index, "family": family, "norad": norad,
        "exit_code": completed.returncode, "wall_s": time.monotonic() - started,
        "command": command,
        "exact_audit_sha256": digest(HERE / "exact_audit.py"),
        "exact_protocol_sha256": digest(HERE / "EXACT_PROTOCOL.md"),
    }
    with receipt.open("x") as stream:
        json.dump(row, stream, indent=2)
    return row


def batch(indices, workers):
    if workers < 1 or workers > MAX_WORKERS:
        raise ValueError(f"workers must be within 1..{MAX_WORKERS}")
    jobs = []
    for index in indices:
        _, _, phase = validate_phase1(index)
        for row in selected_jobs(phase):
            key = (index, row["family"], row["norad"])
            if key not in jobs:
                jobs.append(key)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(launch_job, *job): job for job in jobs}
        for future in as_completed(futures):
            print(json.dumps(future.result()), flush=True)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("one")
    one.add_argument("index", type=int, choices=(0, 16))
    one.add_argument("family", choices=tuple(("iid_t4_scale100", "source_receiver_equal",
                                               "robust_t8_scale100", "robust_t4_scale200")))
    one.add_argument("norad", type=int)
    one.add_argument("output")
    many = commands.add_parser("batch")
    many.add_argument("indices", nargs="*", type=int, default=[0, 16], choices=(0, 16))
    many.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()
    if args.command == "one":
        run_one(args.index, args.family, args.norad, args.output)
    else:
        batch(args.indices, args.workers)


if __name__ == "__main__":
    main()
