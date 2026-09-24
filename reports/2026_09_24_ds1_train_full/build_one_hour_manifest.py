#!/usr/bin/env python3
"""Build the bounded, TRAIN-only DS1 one-hour method-comparison manifest.

This is intentionally separate from ``build_manifest.py``.  The latter is a
coverage harness; it enumerates every singleton and several overlapping blocks.
This builder encodes the much smaller, predeclared comparison protocol.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmark import METHODS, PRIORS, canonical_json, validate_task

HERE = Path(__file__).resolve().parent
DEFAULT_DATASET = HERE.parent / "2026_09_24_ds1" / "dataset.json"
SCHEMA = "ds1-train-one-hour-benchmark-manifest/v1"
TASK_SCHEMA = "ds1-train-full-inference-task/v1"
CACHE_ROOTS = {
    "20260921_00": "/tmp/leo-long-training-cache-full8h",
    "20260921_16": "/tmp/leo-long-training-cache-second8h",
}

# The order and membership are fixed before inference.  Prefix-6 is the
# smallest historical multi-scan DS1 view, while its first scan provides the
# requested single-scan comparison.  No truth-dependent sampling occurs.
VIEW_SPECS = (
    ("first-singleton", 1, "representative_singleton"),
    ("prefix-6", 6, "representative_multi_prefix"),
)
CORE_METHODS = (
    "baseline",
    "global_time",
    "per_scan_time",
    "independent_per_track_time",
    "soft_association",
    "soft_association_plus_global_time",
)
ORBIT_METHODS = (
    "causal_per_norad_orbit_rate",
    "global_time_plus_per_norad_orbit_rate",
)


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def train_groups(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    _require(dataset.get("schema") == "ds1-benchmark/v1", "unexpected DS1 dataset schema")
    groups = [row for row in dataset.get("groups", []) if row.get("partition") == "train"]
    _require(
        [row.get("group_id") for row in groups] == list(CACHE_ROOTS),
        "DS1 TRAIN groups changed",
    )
    for group in groups:
        ids = group.get("session_ids")
        _require(isinstance(ids, list) and len(ids) >= 6, "TRAIN group lacks prefix-6")
        _require(all(isinstance(session_id, str) for session_id in ids), "invalid session ID")
    return groups


def _common_options(method: str) -> dict[str, Any]:
    options: dict[str, Any] = {
        "observation_policy": "all_qualified_observations",
        "within_track_holdout": "forbidden",
        "frequency_loss_cap_hz": 800.0,
        "minimum_track_duration_s": 3.0,
        "altitude_m": 0.0,
        "causal_cache_validation": {
            "require_cache_receipt": True,
            "require_session_id_match": True,
            "require_receipt_cache_digest_match": True,
        },
        # The same fixed geometry is used for every method and prior.  This is
        # a method comparison at 12.5-km grid resolution, not a fine-position
        # accuracy claim.
        "geographic_levels_km": [100.0, 50.0, 25.0, 12.5],
        "search_levels_km": [100.0, 50.0, 25.0, 12.5],
        "beam_width": 2,
    }
    if method in {"global_time", "per_scan_time", "independent_per_track_time"}:
        # The timing runner supports symmetric grids.  The compact +/-2 s,
        # 0.5-s grid is deliberately fixed rather than tuned against truth.
        options.update({"tau_limit_s": 2.0, "tau_step_s": 0.5})
    if method == "global_time_plus_per_norad_orbit_rate":
        options["tau_grid_s"] = [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0]
    if method in ORBIT_METHODS:
        # One RF-selected basin receives exact SGP4 fitting.  This bounds the
        # expensive stage without using the reference coordinate to choose it.
        options.update({"exact_rate_finalists": 1, "exact_rate_workers": 1})
    return options


def build_manifest(dataset: dict[str, Any], source_digest: str) -> dict[str, Any]:
    groups = train_groups(dataset)
    cases: list[dict[str, Any]] = []
    for group in groups:
        for view_name, count, selection_kind in VIEW_SPECS:
            sessions = list(group["session_ids"][:count])
            cases.append(
                {
                    "case_id": f"train-{group['group_id']}--{view_name}",
                    "group_id": group["group_id"],
                    "session_ids": sessions,
                    "scan_count": count,
                    "mode": "single" if count == 1 else "multi",
                    "selection_kinds": [selection_kind],
                }
            )
    tasks: list[dict[str, Any]] = []
    for case in cases:
        for method in (*CORE_METHODS, *ORBIT_METHODS):
            _require(METHODS[method].get("supported", True), f"unsupported method: {method}")
            tier = "core" if method in CORE_METHODS else "extended"
            for prior_name, prior in PRIORS.items():
                task_id = f"one-hour--{case['case_id']}--{prior_name}--{method}"
                tasks.append(
                    {
                        "schema": TASK_SCHEMA,
                        "task_id": task_id,
                        "partition": "train",
                        "tier": tier,
                        "stage": "screening_comparison" if tier == "core" else "exact_orbit",
                        "group_id": case["group_id"],
                        "case_id": case["case_id"],
                        "selection_kinds": case["selection_kinds"],
                        "session_ids": case["session_ids"],
                        "scan_count": case["scan_count"],
                        "prior": {"name": prior_name, **prior},
                        "method": method,
                        "options": _common_options(method),
                        "input_scans": [
                            {
                                "session_id": session_id,
                                "group_id": case["group_id"],
                                "causal_state_cache_root": CACHE_ROOTS[case["group_id"]],
                            }
                            for session_id in case["session_ids"]
                        ],
                        "estimated_cost": {
                            "work_units": round(
                                case["scan_count"] * METHODS[method]["cost_per_scan"], 3
                            ),
                            "relative_per_scan": METHODS[method]["cost_per_scan"],
                        },
                        "output_path": f"artifacts/one-hour/{method}/{task_id}.json",
                    }
                )
    _require(len(cases) == 4, "expected four frozen views")
    _require(len(tasks) == 64, "expected 64 method/prior tasks")
    _require(len({task["task_id"] for task in tasks}) == len(tasks), "duplicate task ID")
    return {
        "schema": SCHEMA,
        "name": "DS1 TRAIN one-hour full-observation method comparison",
        "version": 1,
        "source_dataset_sha256": source_digest,
        "partitions_permitted": ["train"],
        "position_evaluation": "post_seal_external_only",
        "reference_coordinate_in_manifest": False,
        "observation_policy": "all_qualified_observations",
        "within_track_holdout": "forbidden",
        "priors": PRIORS,
        "case_count": len(cases),
        "task_count": len(tasks),
        "stages": {
            "core": "48 timing and association tasks; complete and seal before orbit stage",
            "extended": "16 predeclared orbit tasks; no truth- or score-based promotion",
        },
        "methods": {name: METHODS[name] for name in (*CORE_METHODS, *ORBIT_METHODS)},
        "cases": cases,
        "tasks": sorted(tasks, key=lambda task: task["task_id"]),
    }


def write_atomic(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(payload)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=HERE / "one-hour-inference-manifest.json")
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    manifest = build_manifest(dataset, sha256_file(args.dataset))
    for task in manifest["tasks"]:
        validate_task(task, HERE)
    write_atomic(args.output, canonical_json(manifest))
    write_atomic(args.output.with_suffix(".sha256"), sha256_file(args.output) + "\n")
    print(json.dumps({"cases": len(manifest["cases"]), "tasks": len(manifest["tasks"])}))


if __name__ == "__main__":
    main()
