#!/usr/bin/env python3
"""Build the reviewed, digest-bound exact source-holdout screen plan."""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np


HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
HILL = HERE.parents[1]
ROOT = HERE.parents[3]
BASE = HILL.parent / "2026_09_30_ds11_single10"
SCREEN = (0, 4, 8, 12, 16, 20, 24, 28)
FAMILIES = (
    "iid_t4_scale100",
    "source_receiver_equal",
    "robust_t8_scale100",
    "robust_t4_scale200",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


class Sources:
    def __init__(self):
        self.rows = {}

    def add(self, path, expected=None):
        path = Path(path).resolve()
        actual = digest(path)
        if expected is not None and actual != str(expected).removeprefix("sha256:"):
            raise ValueError(f"source hash mismatch: {path}")
        prior = self.rows.get(str(path))
        if prior is not None and prior != actual:
            raise ValueError(f"conflicting source hash: {path}")
        self.rows[str(path)] = actual
        return path

    def add_map(self, rows):
        for path, expected in rows.items():
            self.add(path, expected)


def read(path):
    return json.loads(Path(path).read_text())


def normalize(assignments, weights):
    return [
        {
            "track_id": row["track_id"],
            "track_index": row["track_index"],
            "receiver_id": row["receiver_id"],
            "rf_hz": row["rf_hz"],
            "norad": row["norad"],
            "confidence": row["confidence"],
            "unambiguous": row["unambiguous"],
            "source_receiver_equal_weight": float(weights[index]),
        }
        for index, row in enumerate(assignments)
    ]


def source_groups(assignments, document):
    counts = Counter(row["norad"] for row in assignments if row["unambiguous"])
    groups, coverage = {}, {}
    for norad in sorted(int(n) for n, count in counts.items() if count >= 2):
        indices = [
            i for i, row in enumerate(assignments)
            if row["unambiguous"] and row["norad"] == norad
        ]
        groups[norad] = [assignments[i]["track_id"] for i in indices]
        coverage[norad] = {
            "training_observation_count": int(sum(
                np.asarray(document["tracks"][i]["mask"], dtype=bool).sum() for i in indices
            )),
            "held_observation_count": int(sum(
                (~np.asarray(document["tracks"][i]["mask"], dtype=bool)).sum() for i in indices
            )),
        }
    return groups, coverage


def validate_phase_assignments(index, canonical, sources):
    path = HILL / "source_loo" / "runs" / "phase1" / f"{index:02d}.json"
    receipt_path = path.with_suffix(".receipt.json")
    phase = read(sources.add(path))
    receipt = read(sources.add(receipt_path))
    if (
        phase.get("schema") != "ds11-source-loo-influence-phase1/v1"
        or phase.get("index") != index
        or phase.get("reference_used") is not False
        or phase.get("assignments") != canonical
        or receipt.get("index") != index
        or receipt.get("exit_code") != 0
    ):
        raise ValueError(f"phase assignment mismatch for index {index}")
    sources.add_map(phase["sources"])
    return path, phase


def cache_receipt(path, kind, index, family, norad, sources):
    receipt_path = sources.add(Path(path).with_suffix(".receipt.json"))
    receipt = read(receipt_path)
    if (
        receipt.get("index") != index
        or receipt.get("family") != family
        or receipt.get("exit_code") != 0
    ):
        raise ValueError(f"cache receipt identity mismatch: {receipt_path}")
    if kind in ("audit", "atomic") and receipt.get("norad") != norad:
        raise ValueError(f"cache receipt NORAD mismatch: {receipt_path}")
    if kind == "family":
        if (
            receipt.get("run_sha256") != digest(EXPERIMENT / "run.py")
            or receipt.get("protocol_sha256") != digest(EXPERIMENT / "PROTOCOL.md")
        ):
            raise ValueError("family cache receipt source mismatch")
    elif kind == "audit":
        if (
            receipt.get("exact_audit_sha256") != digest(HILL / "source_loo" / "exact_audit.py")
            or receipt.get("exact_protocol_sha256") != digest(HILL / "source_loo" / "EXACT_PROTOCOL.md")
        ):
            raise ValueError("audit cache receipt source mismatch")
    elif kind == "atomic":
        if (
            receipt.get("run_sha256") != digest(EXPERIMENT / "atomic" / "run.py")
            or receipt.get("plan_sha256") != digest(EXPERIMENT / "atomic" / "plan.json")
            or receipt.get("protocol_sha256") != digest(EXPERIMENT / "atomic" / "PLAN_PROTOCOL.md")
        ):
            raise ValueError("atomic cache receipt source mismatch")
    else:
        raise ValueError(f"unknown cache kind {kind}")
    return receipt_path


def require_bound_dependencies(row, family, plan_path, entry, index, sources):
    sources.add_map(row["sources"])
    plan_path = Path(plan_path).resolve()
    required = [plan_path]
    required += [
        (HILL / "source_loo" / "diagnose.py").resolve(),
        (HILL / "source_loo" / "exact_audit.py").resolve(),
    ]
    if family == "source_receiver_equal":
        required.append((HILL / "source_balance" / "model.py").resolve())
    elif family.startswith("robust_"):
        required.append((HILL / "robust" / "model.py").resolve())
    else:
        required += [
            (ROOT / "tools" / "ds7_baseline_adapter.py").resolve(),
            (ROOT / "tools" / "ds7_fast_baseline_adapter.py").resolve(),
        ]
    for path in required:
        if row["sources"].get(str(path)) != digest(path):
            raise ValueError(f"cache omits bound dependency: {path}")
    bound_plan = read(plan_path)
    if index >= len(bound_plan.get("inputs", [])) or bound_plan["inputs"][index] != entry:
        raise ValueError("cache-bound plan does not contain the validated scan entry")
    for artifact in entry["artifacts"]:
        path = Path(artifact["path"]).resolve()
        actual = digest(path)
        if artifact["sha256"] != "sha256:" + actual:
            raise ValueError(f"cache-bound plan artifact digest mismatch: {path}")
        direct = row["sources"].get(str(path))
        if direct is not None and direct != actual:
            raise ValueError(f"cache direct artifact digest mismatch: {path}")


def validate_cache(kind, result_path, *, index, family, norad, endpoint_x,
                   track_ids, coverage, canonical, plan_path, entry, sources):
    result_path = sources.add(result_path)
    receipt_path = cache_receipt(result_path, kind, index, family, norad, sources)
    row = read(result_path)
    dependency_row = row
    if kind == "audit":
        phase_path, phase = validate_phase_assignments(index, canonical, sources)
        if row["sources"].get(str(phase_path.resolve())) != digest(phase_path):
            raise ValueError("audit cache does not bind canonical assignments")
        # Exact audit records bind the phase result, which binds the model code.
        # Validate both maps before constructing this explicit one-hop closure.
        sources.add_map(row["sources"])
        dependency_row = {**row, "sources": {**phase["sources"], **row["sources"]}}
    require_bound_dependencies(dependency_row, family, plan_path, entry, index, sources)
    if row.get("session_id") != entry["session_id"]:
        raise ValueError(f"cache session mismatch: {result_path}")
    if kind == "family":
        if (
            row.get("schema") != "ds11-source-loo-exact-family/v1"
            or row.get("index") != index
            or row.get("family") != family
            or row.get("full_endpoint_x") != endpoint_x
            or row.get("assignments") != canonical
            or row.get("reference_used") is not False
            or not row.get("family_qualified")
        ):
            raise ValueError(f"family cache identity mismatch: {result_path}")
        matches = [fold for fold in row["folds"] if fold["norad"] == norad]
        if len(matches) != 1:
            raise ValueError("family cache fold multiplicity mismatch")
        fold = matches[0]
        cached_ids = fold["track_ids"]
        cached_coverage = {
            "training_observation_count": fold["training_observation_count"],
            "held_observation_count": fold["held_observation_count"],
        }
    elif kind == "audit":
        if (
            row.get("schema") != "ds11-source-loo-exact-audit/v1"
            or row.get("index") != index
            or row.get("family") != family
            or row.get("norad") != norad
            or row.get("full_endpoint_x") != endpoint_x
            or row.get("reference_used") is not False
        ):
            raise ValueError(f"audit cache identity mismatch: {result_path}")
        fold = {
            "optimizer": row["optimizer"],
            "common_held_score": row["exact_common_held"]["score"],
        }
        cached_ids = row["source_track_ids"]
        cached_coverage = {
            "training_observation_count": coverage["training_observation_count"],
            "held_observation_count": row["exact_common_held"]["held_observation_count"],
        }
    elif kind == "atomic":
        if (
            row.get("schema") != "ds11-source-loo-atomic-fold/v1"
            or row.get("index") != index
            or row.get("family") != family
            or row.get("norad") != norad
            or row.get("full_endpoint_x") != endpoint_x
            or row.get("reference_used") is not False
        ):
            raise ValueError(f"atomic cache identity mismatch: {result_path}")
        fold = row["fold"]
        cached_ids = fold["track_ids"]
        cached_coverage = {
            "training_observation_count": fold["training_observation_count"],
            "held_observation_count": fold["held_observation_count"],
        }
    else:
        raise ValueError(f"unknown cache kind {kind}")
    if (
        cached_ids != track_ids
        or cached_coverage != coverage
        or not fold["optimizer"]["qualified"]
        or not isinstance(fold.get("common_held_score"), (int, float))
    ):
        raise ValueError(f"cache membership, coverage, or qualification mismatch: {result_path}")
    if family == "source_receiver_equal":
        flag = (
            fold.get("weights_preserved_without_renormalization")
            if kind == "family"
            else row.get("source_weights_preserved_without_renormalization")
        )
        if not flag:
            raise ValueError("source cache did not preserve frozen weights")
    return {"kind": kind, "path": str(result_path)}, str(receipt_path)


def index_zero_caches(sources):
    selection_path = sources.add(EXPERIMENT / "atomic" / "selection.json")
    selection = read(selection_path)
    if (
        selection.get("schema") != "ds11-source-loo-atomic-selection/v1"
        or selection.get("index") != 0
        or selection.get("reference_used") is not False
        or selection.get("planned_folds") != 56
        or selection.get("qualified_folds") != 56
        or not selection.get("selectable")
    ):
        raise ValueError("index-0 atomic selection is incomplete")
    sources.add_map(selection["sources"])
    caches = {}
    for fold in selection["folds"]:
        path = Path(fold["evidence_path"]).resolve()
        text = str(path)
        if "/runs/pilot/" in text:
            kind = "family"
        elif "/source_loo/runs/exact_audit/" in text:
            kind = "audit"
        elif "/source_loo_exact/atomic/runs/" in text:
            kind = "atomic"
        else:
            raise ValueError(f"unknown index-0 evidence: {path}")
        key = (fold["family"], fold["norad"])
        if key in caches or not fold["qualified"]:
            raise ValueError("duplicate or unqualified index-0 cache")
        caches[key] = (kind, path)
    if len(caches) != 56:
        raise ValueError("index-0 cache census mismatch")
    return caches


def index_sixteen_caches(sources):
    phase_path = sources.add(HILL / "source_loo" / "runs" / "phase1" / "16.json")
    phase = read(phase_path)
    sources.add(phase_path.with_suffix(".receipt.json"))
    caches = {}
    for family in phase["families"]:
        selection = family["selection"]
        if not selection.get("selection_complete"):
            raise ValueError("index-16 exact-audit selection incomplete")
        for key in ("largest_norad", "lower_median_norad"):
            norad = selection[key]
            result = HILL / "source_loo" / "runs" / "exact_audit" / (
                f"16_{family['family']}_{norad}.json"
            )
            caches[(family["family"], norad)] = ("audit", result)
    if len(caches) != 8:
        raise ValueError("index-16 cache census mismatch")
    return caches


def build_plan():
    started = time.monotonic()
    sources = Sources()
    dependencies = [
        HERE / "input_context.py", HERE / "prepare.py", HERE / "PROTOCOL.md",
        EXPERIMENT / "run.py", EXPERIMENT / "PROTOCOL.md",
        EXPERIMENT / "atomic" / "run.py", EXPERIMENT / "atomic" / "PLAN_PROTOCOL.md",
        EXPERIMENT / "atomic" / "plan.json", EXPERIMENT / "atomic" / "selection.json",
        HILL / "source_loo" / "diagnose.py", HILL / "source_loo" / "exact_audit.py",
        HILL / "source_loo" / "PROTOCOL.md", HILL / "source_loo" / "EXACT_PROTOCOL.md",
        HILL / "source_balance" / "model.py", HILL / "robust" / "model.py",
        ROOT / "tools" / "ds7_baseline_adapter.py",
        ROOT / "tools" / "ds7_fast_baseline_adapter.py",
    ]
    dependencies += [path for path in (HERE / "run.py", HERE / "assess.py", HERE / "test_run.py",
                                       HERE / "test_assess.py", HERE / "test_prepare.py")
                     if path.exists()]
    for path in dependencies:
        sources.add(path)
    context = load_module("ds11_screen_context_prepare", HERE / "input_context.py")
    diagnose = load_module("ds11_screen_diagnose_prepare", HILL / "source_loo" / "diagnose.py")
    source_model = load_module(
        "ds11_screen_source_prepare", HILL / "source_balance" / "model.py"
    )
    source_model.fast.baseline.profile = source_model.fast.profile
    cache_maps = {0: index_zero_caches(sources), 16: index_sixteen_caches(sources)}
    jobs, scans, cache_receipts = [], [], []

    for index in SCREEN:
        plan_path, baseline_plan, entry, documents, sidecar_path, norad_map = context.load_scan(index)
        sources.add(plan_path)
        sources.add(sidecar_path)
        for artifact in entry["artifacts"]:
            sources.add(artifact["path"], artifact["sha256"])
        endpoints, endpoint_paths = {}, {}
        for family_name in FAMILIES:
            family = diagnose.FAMILIES[family_name]
            endpoint_path, receipt_path, _, x, _, embedded = diagnose.load_endpoint(
                family_name, family, index, entry["session_id"]
            )
            sources.add(endpoint_path)
            sources.add(receipt_path)
            sources.add_map(embedded)
            endpoints[family_name] = x.tolist()
            endpoint_paths[family_name] = str(endpoint_path.resolve())
        assignments = source_model.freeze_assignments(
            documents, baseline_plan["config"],
            np.asarray(endpoints["iid_t4_scale100"]), norad_map,
        )
        weights = source_model.derive_weights(assignments, "source_receiver_equal")
        canonical = normalize(assignments, weights)
        groups, coverage = source_groups(assignments, documents[0])
        if index in (0, 16):
            validate_phase_assignments(index, canonical, sources)
        validated = 0
        cache_map = cache_maps.get(index, {})
        for family in FAMILIES:
            for norad in sorted(groups):
                cache = None
                if (family, norad) in cache_map:
                    kind, path = cache_map[(family, norad)]
                    cache, receipt_path = validate_cache(
                        kind, path, index=index, family=family, norad=norad,
                        endpoint_x=endpoints[family], track_ids=groups[norad],
                        coverage=coverage[norad], canonical=canonical,
                        plan_path=plan_path, entry=entry, sources=sources,
                    )
                    cache_receipts.append(receipt_path)
                    validated += 1
                jobs.append({
                    "index": index,
                    "family": family,
                    "norad": norad,
                    "source_track_ids": groups[norad],
                    "full_endpoint_x": endpoints[family],
                    "cache": cache,
                })
        if validated != (56 if index == 0 else 8 if index == 16 else 0):
            raise ValueError(f"cache count mismatch for index {index}")
        scans.append({
            "index": index,
            "session_id": entry["session_id"],
            "eligible_source_count": len(groups),
            "norad_order": sorted(groups),
            "endpoint_paths": endpoint_paths,
            "assignments": canonical,
            "coverage": {str(norad): coverage[norad] for norad in sorted(coverage)},
            "cached_job_count": validated,
        })

    expected = sum(scan["eligible_source_count"] * 4 for scan in scans)
    keys = [(job["index"], job["family"], job["norad"]) for job in jobs]
    if len(jobs) != expected or len(keys) != len(set(keys)):
        raise ValueError("job count or uniqueness mismatch")
    if keys != sorted(keys, key=lambda key: (
        SCREEN.index(key[0]), FAMILIES.index(key[1]), key[2]
    )):
        raise ValueError("job ordering mismatch")
    cached = sum(job["cache"] is not None for job in jobs)
    if cached != 64:
        raise ValueError("cache count must equal 56 index-0 plus 8 index-16 jobs")
    return {
        "schema": "ds11-source-loo-exact-screen-plan/v1",
        "reference_used": False,
        "screen_indices": list(SCREEN),
        "family_order": list(FAMILIES),
        "job_order": "index, family order, ascending physical NORAD",
        "job_count": len(jobs),
        "cached_job_count": cached,
        "pending_job_count": len(jobs) - cached,
        "execution": {
            "one_index_at_a_time": True,
            "atomic_cap_s": 90,
            "max_workers": 3,
            "blas_threads_per_worker": 1,
            "starts_per_job": 1,
            "within_job_retries": 0,
            "stop_after_unselectable_index": True,
        },
        "selection": {
            "requires_all_eight_selectable": True,
            "requires_all_family_folds_qualified": True,
            "requires_identical_coverage": True,
            "score": "sum common original-IID t4/100 held score over every source",
            "tie_order": list(FAMILIES),
            "geographic_gate": {
                "minimum_wins_over_iid": 5,
                "minimum_median_error_reduction_fraction": 0.10,
                "p90_must_be_nonworse": True,
            },
            "geographic_errors_before_all_selections_sealed": False,
        },
        "common_held_rule": {
            "model": "original IID Student-t4 scale100",
            "cfo_profile": "training observations only per track and candidate",
            "score": "joint-minus-training log mixture density with same CFO",
            "implementation_path": str((HILL / "source_loo" / "exact_audit.py").resolve()),
            "implementation_sha256": digest(HILL / "source_loo" / "exact_audit.py"),
        },
        "scans": scans,
        "jobs": jobs,
        "validated_cache_receipts": sorted(set(cache_receipts)),
        "sources": dict(sorted(sources.rows.items())),
        "preparation_elapsed_s": time.monotonic() - started,
    }


def main():
    output = HERE / "plan.json"
    plan = build_plan()
    with output.open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)
    print(json.dumps({
        "schema": plan["schema"],
        "jobs": plan["job_count"],
        "cached": plan["cached_job_count"],
        "pending": plan["pending_job_count"],
        "elapsed_s": plan["preparation_elapsed_s"],
    }))


if __name__ == "__main__":
    main()
