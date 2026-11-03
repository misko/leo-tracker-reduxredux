#!/usr/bin/env python3
"""Exact source-holdout family fits with reference-free common held scoring."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from scipy.optimize import minimize


HERE = Path(__file__).resolve().parent
HILL = HERE.parent
ROOT = HERE.parents[2]
TOOLS = ROOT / "tools"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
SCREEN = (0, 4, 8, 12, 16, 20, 24, 28)
PILOT_INDEX = 0
CURRENT_RUN_INDICES = (PILOT_INDEX,)
FAMILY_ORDER = (
    "iid_t4_scale100",
    "source_receiver_equal",
    "robust_t8_scale100",
    "robust_t4_scale200",
)

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


def eligible_groups(assignments):
    counts = Counter(row["norad"] for row in assignments if row["unambiguous"])
    return {
        int(norad): [index for index, row in enumerate(assignments)
                     if row["unambiguous"] and row["norad"] == norad]
        for norad, count in sorted(counts.items()) if count >= 2
    }


def retained_fold(assignments, full_weights, norad):
    omitted = [index for index, row in enumerate(assignments)
               if row["unambiguous"] and row["norad"] == norad]
    omitted_set = set(omitted)
    retained = [index for index in range(len(assignments)) if index not in omitted_set]
    return {
        "omitted_indices": omitted,
        "retained_indices": retained,
        "retained_weights": np.asarray(full_weights)[retained],
        "retained_assignments": [assignments[index] for index in retained],
    }


def fit_local(model, seed, bounds, qualify_fn, minimize_fn=minimize):
    def objective(x):
        evaluated = model.evaluate(x, gradient=True)
        return -float(evaluated["score"]), -np.asarray(evaluated["gradient"], dtype=float)

    result = minimize_fn(
        objective, np.asarray(seed, dtype=float), jac=True, method="L-BFGS-B",
        bounds=np.asarray(bounds).tolist(),
        options={"maxiter": 100, "maxfun": 160, "ftol": 1e-13, "gtol": 1e-6, "maxls": 25},
    )
    qualification = qualify_fn(result, model, np.asarray(bounds, dtype=float))
    return result, qualification


def select_family(rows):
    if [row["family"] for row in rows] != list(FAMILY_ORDER):
        raise ValueError("family rows must follow the frozen tie order")
    if not all(row["family_qualified"] for row in rows):
        return {"selectable": False, "reason": "unqualified_fold", "selected_family": None}
    coverage = [row["coverage"] for row in rows]
    if any(value != coverage[0] for value in coverage[1:]):
        return {"selectable": False, "reason": "coverage_mismatch", "selected_family": None}
    best_index = max(range(len(rows)), key=lambda index: rows[index]["common_held_sum"])
    return {
        "selectable": True,
        "reason": None,
        "selected_family": rows[best_index]["family"],
        "common_held_sum": rows[best_index]["common_held_sum"],
    }


def validate_family_results(index, paths):
    rows = []
    session = None
    for expected_family, path in zip(FAMILY_ORDER, paths, strict=True):
        path = Path(path)
        receipt_path = path.with_suffix(".receipt.json")
        receipt = json.loads(receipt_path.read_text())
        if (receipt.get("exit_code") != 0 or receipt.get("index") != index
                or receipt.get("family") != expected_family):
            raise ValueError("family terminal receipt mismatch")
        if receipt.get("run_sha256") != digest(HERE / "run.py"):
            raise ValueError("family receipt runner binding mismatch")
        if receipt.get("protocol_sha256") != digest(HERE / "PROTOCOL.md"):
            raise ValueError("family receipt protocol binding mismatch")
        row = json.loads(path.read_text())
        if row.get("schema") != "ds11-source-loo-exact-family/v1":
            raise ValueError("family result schema mismatch")
        if row.get("index") != index or row.get("family") != expected_family:
            raise ValueError("family result identity mismatch")
        session = row["session_id"] if session is None else session
        if row["session_id"] != session:
            raise ValueError("family result session mismatch")
        for source, expected in row["sources"].items():
            if digest(source) != expected:
                raise ValueError(f"family result source changed: {source}")
        row["_receipt_path"] = str(receipt_path)
        rows.append(row)
    return rows


def run_family(index, family_name, output):
    if index not in CURRENT_RUN_INDICES:
        raise ValueError("this frozen runner version permits only the index-0 pilot")
    if family_name not in FAMILY_ORDER:
        raise ValueError("unknown family")
    started = time.monotonic()
    fast.baseline.profile = fast.profile
    diagnose_path = HILL / "source_loo" / "diagnose.py"
    exact_path = HILL / "source_loo" / "exact_audit.py"
    diagnose = load_module("ds11_source_loo_exact_diagnose", diagnose_path)
    exact = load_module("ds11_source_loo_exact_helpers", exact_path)
    plan_path, plan, entry, documents, sidecar_path, candidate_norad = diagnose.validate_inputs(index)
    source_path = HILL / "source_balance" / "model.py"
    robust_path = HILL / "robust" / "model.py"
    source_module = diagnose.load_module("ds11_source_loo_exact_source_model", source_path)
    robust_module = diagnose.load_module("ds11_source_loo_exact_robust_model", robust_path)
    modules = {"source": source_module, "robust": robust_module}
    iid_family = diagnose.FAMILIES["iid_t4_scale100"]
    iid_path, iid_receipt, iid, iid_x, _, iid_embedded = diagnose.load_endpoint(
        "iid_t4_scale100", iid_family, index, entry["session_id"]
    )
    assignments = source_module.freeze_assignments(
        documents, plan["config"], iid_x, candidate_norad
    )
    groups = eligible_groups(assignments)
    if not groups:
        raise ValueError("scan has no eligible repeated physical-NORAD source")
    family = diagnose.FAMILIES[family_name]
    endpoint_path, endpoint_receipt, endpoint_result, full_x, endpoint_score, embedded = diagnose.load_endpoint(
        family_name, family, index, entry["session_id"]
    )
    del endpoint_result, endpoint_score
    full_weights = source_module.derive_weights(assignments, "source_receiver_equal")
    folds = []
    for norad, expected_omitted in groups.items():
        fold_started = time.monotonic()
        subset = retained_fold(assignments, full_weights, norad)
        if subset["omitted_indices"] != expected_omitted:
            raise ValueError("eligible group and retained fold disagree")
        retained_doc = diagnose.subset_document(documents[0], subset["retained_indices"])
        if family["kind"] == "source":
            retained_weights = subset["retained_weights"]
            retained_assignments = subset["retained_assignments"]
        else:
            retained_weights = retained_assignments = None
        try:
            model = diagnose.build_evaluator(
                family["kind"], family["variant"], retained_doc, plan["config"], modules,
                weights=retained_weights, assignments=retained_assignments,
            )
            result, qualification = fit_local(
                model, full_x, diagnose.BOUNDS, exact.qualify
            )
            exact_x = np.asarray(result.x, dtype=float)
            held = exact.common_held_score(
                documents[0], subset["omitted_indices"], exact_x, plan["config"]
            )
            fold = {
                "norad": norad,
                "track_indices": subset["omitted_indices"],
                "track_ids": [assignments[i]["track_id"] for i in subset["omitted_indices"]],
                "training_observation_count": int(sum(
                    np.asarray(documents[0]["tracks"][i]["mask"], dtype=bool).sum()
                    for i in subset["omitted_indices"]
                )),
                "held_observation_count": held["held_observation_count"],
                "retained_track_count": len(subset["retained_indices"]),
                "weights_preserved_without_renormalization": family["kind"] == "source",
                "x": exact_x.tolist(),
                "retained_score": float(-result.fun),
                "common_held_score": held["score"],
                "optimizer": {**qualification, "nfev": int(result.nfev), "nit": int(result.nit)},
                "elapsed_s": time.monotonic() - fold_started,
            }
        except Exception as exc:  # preserve a numerical fold failure and continue its family census
            fold = {
                "norad": norad,
                "track_indices": subset["omitted_indices"],
                "track_ids": [assignments[i]["track_id"] for i in subset["omitted_indices"]],
                "training_observation_count": int(sum(
                    np.asarray(documents[0]["tracks"][i]["mask"], dtype=bool).sum()
                    for i in subset["omitted_indices"]
                )),
                "held_observation_count": int(sum(
                    (~np.asarray(documents[0]["tracks"][i]["mask"], dtype=bool)).sum()
                    for i in subset["omitted_indices"]
                )),
                "retained_track_count": len(subset["retained_indices"]),
                "weights_preserved_without_renormalization": family["kind"] == "source",
                "optimizer": {"qualified": False},
                "failure": f"{type(exc).__name__}: {exc}",
                "elapsed_s": time.monotonic() - fold_started,
            }
        folds.append(fold)
    qualified = all(fold["optimizer"]["qualified"] for fold in folds)
    common_sum = (float(sum(fold["common_held_score"] for fold in folds)) if qualified else None)
    coverage = [
        {"norad": fold["norad"], "track_ids": fold["track_ids"],
         "held_observation_count": fold["held_observation_count"]}
        for fold in folds
    ]
    sources = {
        str(HERE / "run.py"): digest(HERE / "run.py"),
        str(HERE / "PROTOCOL.md"): digest(HERE / "PROTOCOL.md"),
        str(diagnose_path): digest(diagnose_path),
        str(exact_path): digest(exact_path),
        str(plan_path): digest(plan_path),
        str(sidecar_path): digest(sidecar_path),
        str(source_path): digest(source_path),
        str(robust_path): digest(robust_path),
        str(TOOLS / "ds7_baseline_adapter.py"): digest(TOOLS / "ds7_baseline_adapter.py"),
        str(TOOLS / "ds7_fast_baseline_adapter.py"): digest(TOOLS / "ds7_fast_baseline_adapter.py"),
        str(iid_path): digest(iid_path),
        str(iid_receipt): digest(iid_receipt),
        str(endpoint_path): digest(endpoint_path),
        str(endpoint_receipt): digest(endpoint_receipt),
        **iid_embedded,
        **embedded,
    }
    record = {
        "schema": "ds11-source-loo-exact-family/v1",
        "index": index,
        "session_id": entry["session_id"],
        "family": family_name,
        "variant": family["variant"],
        "reference_used": False,
        "full_endpoint_x": full_x.tolist(),
        "eligible_source_count": len(groups),
        "family_qualified": qualified,
        "common_held_sum": common_sum,
        "coverage": coverage,
        "assignments": [
            {"track_id": row["track_id"], "track_index": row["track_index"],
             "receiver_id": row["receiver_id"], "rf_hz": row["rf_hz"],
             "norad": row["norad"], "confidence": row["confidence"],
             "unambiguous": row["unambiguous"],
             "source_receiver_equal_weight": float(full_weights[i])}
            for i, row in enumerate(assignments)
        ],
        "folds": folds,
        "sources": sources,
        "elapsed_s": time.monotonic() - started,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
    print(json.dumps({"index": index, "family": family_name, "folds": len(folds),
                      "qualified_folds": sum(fold["optimizer"]["qualified"] for fold in folds),
                      "elapsed_s": record["elapsed_s"]}), flush=True)


def launch(index, family):
    folder = HERE / "runs" / "pilot"
    folder.mkdir(parents=True, exist_ok=True)
    base = folder / f"{index:02d}_{family}"
    output = base.with_suffix(".json")
    log = base.with_suffix(".log")
    receipt = base.with_suffix(".receipt.json")
    if receipt.exists():
        return {"existing": True, **json.loads(receipt.read_text())}
    if output.exists() or log.exists():
        raise RuntimeError(f"unreceipted family attempt requires review: {base}")
    command = [
        "sudo", "-n", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
        "MKL_NUM_THREADS=1", "timeout", "--kill-after=5s", "90s", "nice", "-n", "19",
        PYTHON, str(HERE / "run.py"), "one", str(index), family, str(output),
    ]
    started = time.monotonic()
    with log.open("x") as stream:
        completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    row = {
        "index": index, "family": family, "exit_code": completed.returncode,
        "wall_s": time.monotonic() - started, "command": command,
        "run_sha256": digest(HERE / "run.py"),
        "protocol_sha256": digest(HERE / "PROTOCOL.md"),
    }
    with receipt.open("x") as stream:
        json.dump(row, stream, indent=2)
    return row


def pilot():
    for family in FAMILY_ORDER:
        print(json.dumps(launch(PILOT_INDEX, family)), flush=True)


def summarize(index, output):
    folder = HERE / "runs" / "pilot"
    paths = [folder / f"{index:02d}_{family}.json" for family in FAMILY_ORDER]
    rows = validate_family_results(index, paths)
    result = {
        "schema": "ds11-source-loo-exact-scan-selection/v1",
        "index": index,
        "reference_used": False,
        "selection": select_family(rows),
        "families": [
            {"family": row["family"], "eligible_source_count": row["eligible_source_count"],
             "family_qualified": row["family_qualified"],
             "common_held_sum": row["common_held_sum"], "elapsed_s": row["elapsed_s"]}
            for row in rows
        ],
        "sources": {
            source: digest(source)
            for row, path in zip(rows, paths, strict=True)
            for source in (str(path), row["_receipt_path"])
        },
    }
    with Path(output).open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result["selection"]), flush=True)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("one")
    one.add_argument("index", type=int, choices=CURRENT_RUN_INDICES)
    one.add_argument("family", choices=FAMILY_ORDER)
    one.add_argument("output")
    commands.add_parser("pilot")
    summary = commands.add_parser("summarize")
    summary.add_argument("index", type=int, choices=CURRENT_RUN_INDICES)
    summary.add_argument("output")
    args = parser.parse_args()
    if args.command == "one":
        run_family(args.index, args.family, args.output)
    elif args.command == "pilot":
        pilot()
    else:
        summarize(args.index, args.output)


if __name__ == "__main__":
    main()
