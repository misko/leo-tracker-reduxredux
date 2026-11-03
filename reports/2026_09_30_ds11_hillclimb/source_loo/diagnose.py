#!/usr/bin/env python3
"""Training-only source deletion influence diagnostics for frozen DS11 endpoints."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from collections import Counter
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


HERE = Path(__file__).resolve().parent
HILL = HERE.parent
ROOT = HERE.parents[2]
BASE = HILL.parent / "2026_09_30_ds11_single10"
TOOLS = ROOT / "tools"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
INDICES = (0, 16)
STEPS = np.asarray((1e-4, 1e-4, 1e-5), dtype=float)
HALF_STEPS = STEPS / 2.0
SYMMETRY_LIMIT = 0.005
STEP_AGREEMENT_LIMIT = 0.005
CONDITION_LIMIT = 1e10
BOUNDS = np.asarray(((-12.0, 12.0), (-12.0, 12.0), (-5.0, 5.0)))

sys.path.insert(0, str(TOOLS))
import ds7_fast_baseline_adapter as fast  # noqa: E402


FAMILIES = {
    "iid_t4_scale100": {
        "kind": "iid",
        "variant": "iid",
        "model": TOOLS / "ds7_fast_baseline_adapter.py",
        "result": lambda index: BASE / "runs" / f"{index:02d}_iid.json",
        "receipt": lambda index: BASE / "runs" / f"{index:02d}_iid.receipt.json",
    },
    "source_receiver_equal": {
        "kind": "source",
        "variant": "source_receiver_equal",
        "model": HILL / "source_balance" / "model.py",
        "result": lambda index: HILL / "source_balance" / "runs" / "wave1" / f"source_receiver_equal_{index:02d}.json",
        "receipt": lambda index: HILL / "source_balance" / "runs" / "wave1" / f"source_receiver_equal_{index:02d}.receipt.json",
    },
    "robust_t8_scale100": {
        "kind": "robust",
        "variant": "df8",
        "model": HILL / "robust" / "model.py",
        "result": lambda index: HILL / "robust" / "runs" / "wave1_vectorized" / f"df8_{index:02d}.json",
        "receipt": lambda index: HILL / "robust" / "runs" / "wave1_vectorized" / f"df8_{index:02d}.receipt.json",
    },
    "robust_t4_scale200": {
        "kind": "robust",
        "variant": "scale200",
        "model": HILL / "robust" / "model.py",
        "result": lambda index: HILL / "robust" / "runs" / "wave1_vectorized" / f"scale200_{index:02d}.json",
        "receipt": lambda index: HILL / "robust" / "runs" / "wave1_vectorized" / f"scale200_{index:02d}.receipt.json",
    },
}


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def subset_document(document: dict, track_indices: list[int]) -> dict:
    subset = copy.copy(document)
    subset["tracks"] = [document["tracks"][index] for index in track_indices]
    return subset


class IIDEvaluator:
    def __init__(self, document, config):
        self.model = fast.baseline.Stationary(document, config)

    def evaluate(self, x, gradient=True):
        score, derivative = self.model.evaluate(np.asarray(x), gradient)
        return {"score": float(score), "gradient": np.asarray(derivative)}


def finite_negative_hessian(model, x, steps):
    """Observed negative Hessian from central differences of score gradients."""
    x = np.asarray(x, dtype=float)
    steps = np.asarray(steps, dtype=float)
    if x.shape != (3,) or steps.shape != (3,) or np.any(steps <= 0):
        raise ValueError("three finite parameters and positive derivative steps required")
    score_hessian = np.empty((3, 3), dtype=float)
    for axis, step in enumerate(steps):
        delta = np.zeros(3)
        delta[axis] = step
        positive = np.asarray(model.evaluate(x + delta, gradient=True)["gradient"], dtype=float)
        negative = np.asarray(model.evaluate(x - delta, gradient=True)["gradient"], dtype=float)
        score_hessian[:, axis] = (positive - negative) / (2.0 * step)
    return -score_hessian


def matrix_relative_asymmetry(matrix):
    matrix = np.asarray(matrix, dtype=float)
    return float(np.linalg.norm(matrix - matrix.T) / max(np.linalg.norm(matrix), np.finfo(float).tiny))


def assess_fold(full_negative_hessians, source_negative_hessians, source_gradient,
                full_gradient, x, bounds=BOUNDS):
    primary = np.asarray(full_negative_hessians[0]) - np.asarray(source_negative_hessians[0])
    half = np.asarray(full_negative_hessians[1]) - np.asarray(source_negative_hessians[1])
    x = np.asarray(x, dtype=float)
    source_gradient = np.asarray(source_gradient, dtype=float)
    full_gradient = np.asarray(full_gradient, dtype=float)
    reasons = []
    finite = bool(
        np.isfinite(primary).all() and np.isfinite(half).all()
        and np.isfinite(source_gradient).all() and np.isfinite(full_gradient).all()
    )
    if not finite:
        reasons.append("nonfinite")
        return {"available": False, "failure_reasons": reasons}
    primary_asymmetry = matrix_relative_asymmetry(primary)
    half_asymmetry = matrix_relative_asymmetry(half)
    if primary_asymmetry > SYMMETRY_LIMIT or half_asymmetry > SYMMETRY_LIMIT:
        reasons.append("asymmetry")
    symmetric = 0.5 * (primary + primary.T)
    symmetric_half = 0.5 * (half + half.T)
    eigenvalues = np.linalg.eigvalsh(symmetric)
    positive_definite = bool(np.all(eigenvalues > 0.0))
    if not positive_definite:
        reasons.append("not_positive_definite")
    condition_raw = float(np.linalg.cond(symmetric))
    condition = condition_raw if np.isfinite(condition_raw) else None
    if condition is None or condition > CONDITION_LIMIT:
        reasons.append("condition")
    step_agreement = float(
        np.linalg.norm(symmetric - symmetric_half)
        / max(np.linalg.norm(symmetric_half), np.finfo(float).tiny)
    )
    if step_agreement > STEP_AGREEMENT_LIMIT:
        reasons.append("step_halving")
    influence_delta = optimizer_residual_correction = estimate = None
    if positive_definite and condition is not None and condition <= CONDITION_LIMIT:
        influence_delta_array = -np.linalg.solve(symmetric, source_gradient)
        correction_array = np.linalg.solve(symmetric, full_gradient)
        estimate_array = x + influence_delta_array
        influence_delta = influence_delta_array.tolist()
        optimizer_residual_correction = correction_array.tolist()
        estimate = estimate_array.tolist()
        if not np.isfinite(estimate_array).all() or np.any(estimate_array < bounds[:, 0]) or np.any(estimate_array > bounds[:, 1]):
            reasons.append("bounds")
    else:
        reasons.append("solve_unavailable")
    available = not reasons
    return {
        "available": available,
        "failure_reasons": reasons,
        "retained_negative_hessian": primary.tolist(),
        "retained_negative_hessian_half_step": half.tolist(),
        "relative_asymmetry": primary_asymmetry,
        "half_step_relative_asymmetry": half_asymmetry,
        "step_halving_relative_disagreement": step_agreement,
        "eigenvalues": eigenvalues.tolist(),
        "condition_number": condition,
        "influence_delta": influence_delta,
        "estimate": estimate,
        "en_displacement_km": (float(np.linalg.norm(influence_delta_array[:2]))
                               if influence_delta is not None else None),
        "optimizer_residual_correction": optimizer_residual_correction,
        "optimizer_residual_correction_en_km": (
            float(np.linalg.norm(correction_array[:2]))
            if optimizer_residual_correction is not None else None
        ),
        "optimizer_residual_correction_time_s": (
            float(abs(correction_array[2]))
            if optimizer_residual_correction is not None else None
        ),
    }


def select_extremes(rows):
    qualified = sorted(
        (row for row in rows if row["available"]),
        key=lambda row: (row["en_displacement_km"], row["norad"]),
    )
    eligible_count = len(rows)
    if not qualified:
        return {"eligible_count": eligible_count, "available_count": 0,
                "selection_complete": False, "largest_norad": None,
                "lower_median_norad": None,
                "exploratory_available_largest_norad": None,
                "exploratory_available_lower_median_norad": None}
    maximum = qualified[-1]["en_displacement_km"]
    largest = min(row["norad"] for row in qualified if row["en_displacement_km"] == maximum)
    exploratory = {
        "exploratory_available_largest_norad": int(largest),
        "exploratory_available_lower_median_norad": int(qualified[(len(qualified) - 1) // 2]["norad"]),
    }
    complete = len(qualified) == eligible_count
    return {
        "eligible_count": eligible_count,
        "available_count": len(qualified),
        "selection_complete": complete,
        "largest_norad": int(largest) if complete else None,
        "lower_median_norad": int(qualified[(len(qualified) - 1) // 2]["norad"]) if complete else None,
        **exploratory,
    }


def validate_inputs(index):
    if index not in INDICES:
        raise ValueError(f"phase one permits indices {INDICES}")
    plan_path = BASE / "plan.json"
    plan = json.loads(plan_path.read_text())
    entry = plan["inputs"][index]
    for artifact in entry["artifacts"]:
        if artifact["sha256"] != "sha256:" + digest(Path(artifact["path"])):
            raise ValueError(f"input artifact binding mismatch: {artifact['path']}")
    documents = fast.load_documents({"config": plan["config"], "inputs": [entry]})
    if len(documents) != 1 or documents[0]["session_id"] != entry["session_id"]:
        raise ValueError("loaded document session mismatch")
    sidecar_path = HILL / "source_balance" / "catalogue_identities.json"
    sidecar = json.loads(sidecar_path.read_text())
    if sidecar["schema"] != "ds11-source-balance-identities/v1" or sidecar["plan_sha256"] != digest(plan_path):
        raise ValueError("identity sidecar plan binding mismatch")
    scan = sidecar["scans"][str(index)]
    if scan["session_id"] != entry["session_id"]:
        raise ValueError("identity sidecar session mismatch")
    paths = [Path(item["path"]) for item in entry["artifacts"]]
    bindings = {
        "observation_sha256": next(path for path in paths if path.name == "observations.json"),
        "manifest_sha256": next(path for path in paths if path.name == "manifest.json"),
        "bank_sha256": next(path for path in paths if path.suffix == ".npz"),
    }
    for key, path in bindings.items():
        if scan[key] != digest(path):
            raise ValueError(f"identity sidecar {key} mismatch")
    candidate_norad = [{track_id: row["candidate_norad"] for track_id, row in scan["tracks"].items()}]
    return plan_path, plan, entry, documents, sidecar_path, candidate_norad


def load_endpoint(family_name, family, index, session):
    path = family["result"](index)
    receipt_path = family["receipt"](index)
    result = json.loads(path.read_text())
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("exit_code") != 0 or receipt.get("index") != index:
        raise ValueError(f"nonterminal or stale {family_name} endpoint receipt")
    selected = result.get("selected")
    if selected is None or not selected.get("qualified"):
        raise ValueError(f"unqualified {family_name} endpoint")
    if result.get("index") != index or result.get("session") != session:
        raise ValueError(f"stale {family_name} endpoint")
    if family["kind"] == "iid":
        if result.get("method") != "iid" or receipt.get("method") != "iid":
            raise ValueError("original endpoint method mismatch")
        embedded_sources = {}
    else:
        expected_family = "source_balance" if family["kind"] == "source" else "robust"
        expected_stage = "wave1" if family["kind"] == "source" else "wave1_vectorized"
        if result.get("family") != expected_family or receipt.get("family") != expected_family:
            raise ValueError(f"{family_name} family mismatch")
        if result.get("variant") != family["variant"] or receipt.get("variant") != family["variant"]:
            raise ValueError(f"{family_name} variant mismatch")
        if result.get("stage") != expected_stage or receipt.get("command", [])[-1:] != [expected_stage]:
            raise ValueError(f"{family_name} stage mismatch")
        embedded_sources = {}
        for source, expected in result.get("sources", {}).items():
            source_path = Path(source)
            if digest(source_path) != expected:
                raise ValueError(f"{family_name} embedded source mismatch: {source}")
            embedded_sources[str(source_path)] = expected
        for artifact in result.get("artifacts", []):
            artifact_path = Path(artifact["path"])
            expected = artifact["sha256"].removeprefix("sha256:")
            if digest(artifact_path) != expected:
                raise ValueError(f"{family_name} embedded artifact mismatch: {artifact_path}")
            embedded_sources[str(artifact_path)] = expected
    x = np.asarray(selected["x"], dtype=float)
    if x.shape != (3,) or not np.isfinite(x).all():
        raise ValueError(f"invalid {family_name} endpoint")
    if np.any(x - BOUNDS[:, 0] < 0.001) or np.any(BOUNDS[:, 1] - x < 0.001):
        raise ValueError(f"non-interior {family_name} endpoint")
    return path, receipt_path, result, x, float(selected["score"]), embedded_sources


def build_evaluator(kind, variant, document, config, modules, *, weights=None, assignments=None):
    if kind == "iid":
        return IIDEvaluator(document, config)
    if kind == "robust":
        return modules["robust"].RobustIID([document], config, variant)
    return modules["source"].SourceBalancedIID(
        [document], config, np.asarray(weights, dtype=float), assignments
    )


def run(index, output):
    started = time.monotonic()
    fast.baseline.profile = fast.profile
    plan_path, plan, entry, documents, sidecar_path, candidate_norad = validate_inputs(index)
    source_path = HILL / "source_balance" / "model.py"
    robust_path = HILL / "robust" / "model.py"
    modules = {
        "source": load_module("ds11_source_loo_source_model", source_path),
        "robust": load_module("ds11_source_loo_robust_model", robust_path),
    }
    iid_path = FAMILIES["iid_t4_scale100"]["result"](index)
    iid_result = json.loads(iid_path.read_text())
    if iid_result.get("selected") is None or not iid_result["selected"].get("qualified"):
        raise ValueError("original IID endpoint is unqualified")
    iid_x = np.asarray(iid_result["selected"]["x"], dtype=float)
    assignments = modules["source"].freeze_assignments(
        documents, plan["config"], iid_x, candidate_norad
    )
    if len(assignments) != len(documents[0]["tracks"]):
        raise ValueError("assignment count mismatch")
    counts = Counter(row["norad"] for row in assignments if row["unambiguous"])
    eligible = sorted(int(norad) for norad, count in counts.items() if count >= 2)
    group_indices = {
        norad: [i for i, row in enumerate(assignments) if row["unambiguous"] and row["norad"] == norad]
        for norad in eligible
    }
    all_indices = list(range(len(assignments)))
    source_weights = modules["source"].derive_weights(assignments, "source_receiver_equal")
    family_rows = []
    source_bindings = {
        str(HERE / "diagnose.py"): digest(HERE / "diagnose.py"),
        str(HERE / "PROTOCOL.md"): digest(HERE / "PROTOCOL.md"),
        str(plan_path): digest(plan_path),
        str(sidecar_path): digest(sidecar_path),
        str(source_path): digest(source_path),
        str(robust_path): digest(robust_path),
        str(TOOLS / "ds7_baseline_adapter.py"): digest(TOOLS / "ds7_baseline_adapter.py"),
        str(TOOLS / "ds7_fast_baseline_adapter.py"): digest(TOOLS / "ds7_fast_baseline_adapter.py"),
    }
    for family_name, family in FAMILIES.items():
        endpoint_path, receipt_path, endpoint_result, x, endpoint_score, embedded_sources = load_endpoint(
            family_name, family, index, entry["session_id"]
        )
        source_bindings[str(endpoint_path)] = digest(endpoint_path)
        source_bindings[str(receipt_path)] = digest(receipt_path)
        source_bindings.update(embedded_sources)
        full = build_evaluator(
            family["kind"], family["variant"], documents[0], plan["config"], modules,
            weights=source_weights, assignments=assignments,
        )
        full_eval = full.evaluate(x, gradient=True)
        score_difference = float(full_eval["score"] - endpoint_score)
        if abs(score_difference) > 1e-6:
            raise ValueError(f"{family_name} endpoint score replay mismatch: {score_difference}")
        full_gradient = np.asarray(full_eval["gradient"], dtype=float)
        full_hessians = (
            finite_negative_hessian(full, x, STEPS),
            finite_negative_hessian(full, x, HALF_STEPS),
        )
        folds = []
        for norad in eligible:
            selected_indices = group_indices[norad]
            retained_indices = [i for i in all_indices if i not in set(selected_indices)]
            source_doc = subset_document(documents[0], selected_indices)
            if family["kind"] == "source":
                group_weights = source_weights[selected_indices]
                group_assignments = [assignments[i] for i in selected_indices]
            else:
                group_weights = group_assignments = None
            source_model = build_evaluator(
                family["kind"], family["variant"], source_doc, plan["config"], modules,
                weights=group_weights, assignments=group_assignments,
            )
            source_eval = source_model.evaluate(x, gradient=True)
            source_gradient = np.asarray(source_eval["gradient"], dtype=float)
            source_hessians = (
                finite_negative_hessian(source_model, x, STEPS),
                finite_negative_hessian(source_model, x, HALF_STEPS),
            )
            assessment = assess_fold(
                full_hessians, source_hessians, source_gradient, full_gradient, x
            )
            assessment.update({
                "norad": norad,
                "track_count": len(selected_indices),
                "track_ids": [assignments[i]["track_id"] for i in selected_indices],
                "receiver_ids": sorted({assignments[i]["receiver_id"] for i in selected_indices}),
                "rf_hz": sorted({assignments[i]["rf_hz"] for i in selected_indices}),
                "source_score": float(source_eval["score"]),
                "source_gradient": source_gradient.tolist(),
                "omitted_training_observation_count": int(sum(
                    np.asarray(documents[0]["tracks"][i]["mask"], dtype=bool).sum()
                    for i in selected_indices
                )),
                "omitted_held_observation_count": int(sum(
                    (~np.asarray(documents[0]["tracks"][i]["mask"], dtype=bool)).sum()
                    for i in selected_indices
                )),
                "retained_track_count": len(retained_indices),
                "weights_preserved_without_renormalization": family["kind"] == "source",
            })
            folds.append(assessment)
        timing_grid = np.asarray(plan["config"]["timing_grid_s"], dtype=float)
        selectors = select_extremes(folds)
        family_rows.append({
            "family": family_name,
            "variant": family["variant"],
            "endpoint_path": str(endpoint_path),
            "endpoint_receipt_path": str(receipt_path),
            "endpoint_x": x.tolist(),
            "endpoint_score": endpoint_score,
            "replayed_score_difference": score_difference,
            "full_gradient": full_gradient.tolist(),
            "full_gradient_max_abs": float(np.max(np.abs(full_gradient))),
            "timing_distance_to_nearest_grid_knot_s": float(np.min(np.abs(timing_grid - x[2]))),
            "negative_hessian": full_hessians[0].tolist(),
            "negative_hessian_half_step": full_hessians[1].tolist(),
            "eligible_source_count": len(eligible),
            "folds": folds,
            "selection": selectors,
        })
    record = {
        "schema": "ds11-source-loo-influence-phase1/v1",
        "index": index,
        "session_id": entry["session_id"],
        "training_only": True,
        "reference_used": False,
        "held_observations_used": False,
        "confidence_threshold": 0.90,
        "fold_key": "physical NORAD across receiver and RF",
        "steps": STEPS.tolist(),
        "half_steps": HALF_STEPS.tolist(),
        "bounds": BOUNDS.tolist(),
        "track_count": len(assignments),
        "ambiguous_track_count": sum(not row["unambiguous"] for row in assignments),
        "eligible_sources": eligible,
        "assignments": [
            {
                "track_id": row["track_id"],
                "track_index": row["track_index"],
                "receiver_id": row["receiver_id"],
                "rf_hz": row["rf_hz"],
                "norad": row["norad"],
                "confidence": row["confidence"],
                "unambiguous": row["unambiguous"],
                "source_receiver_equal_weight": float(source_weights[i]),
            }
            for i, row in enumerate(assignments)
        ],
        "families": family_rows,
        "input_artifacts": entry["artifacts"],
        "sources": source_bindings,
        "elapsed_s": time.monotonic() - started,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
    print(json.dumps({"index": index, "elapsed_s": record["elapsed_s"],
                      "eligible_sources": len(eligible),
                      "available": {row["family"]: row["selection"]["available_count"]
                                    for row in family_rows}}), flush=True)


def batch(indices):
    output_dir = HERE / "runs" / "phase1"
    output_dir.mkdir(parents=True, exist_ok=True)
    for index in indices:
        base = output_dir / f"{index:02d}"
        output = base.with_suffix(".json")
        log = base.with_suffix(".log")
        receipt = base.with_suffix(".receipt.json")
        if receipt.exists():
            print(f"Existing terminal attempt retained: {receipt}", flush=True)
            continue
        if output.exists() or log.exists():
            raise RuntimeError(f"unreceipted attempt requires audit: {base}")
        command = [
            "sudo", "-n", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
            "MKL_NUM_THREADS=1", "timeout", "--kill-after=5s", "90s", "nice", "-n", "19",
            PYTHON, str(HERE / "diagnose.py"), "one", str(index), str(output),
        ]
        started = time.monotonic()
        with log.open("x") as stream:
            completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        row = {
            "index": index,
            "exit_code": completed.returncode,
            "wall_s": time.monotonic() - started,
            "command": command,
            "diagnose_sha256": digest(HERE / "diagnose.py"),
            "protocol_sha256": digest(HERE / "PROTOCOL.md"),
        }
        with receipt.open("x") as stream:
            json.dump(row, stream, indent=2)
        print(json.dumps(row), flush=True)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    one = subparsers.add_parser("one")
    one.add_argument("index", type=int)
    one.add_argument("output")
    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("indices", nargs="*", type=int, default=list(INDICES))
    args = parser.parse_args()
    if args.command == "one":
        run(args.index, args.output)
    else:
        batch(args.indices)


if __name__ == "__main__":
    main()
