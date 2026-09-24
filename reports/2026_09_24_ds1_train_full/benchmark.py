"""Build the sealed, TRAIN-only input contract for DS1 full-observation fits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "ds1-train-full-benchmark-manifest/v1"
TASK_SCHEMA = "ds1-train-full-inference-task/v1"
RESULT_SCHEMA = "ds1-train-full-inference-result/v1"

# Existing strict-causal state caches for DS1 TRAIN only.
TRAIN_CACHE_ROOTS = {
    "20260921_00": "/tmp/leo-long-training-cache-full8h",
    "20260921_16": "/tmp/leo-long-training-cache-second8h",
}
PRIORS = {
    "sacramento": {"latitude_deg": 38.5816, "longitude_deg": -121.4944, "radius_km": 250.0},
    "reno": {"latitude_deg": 39.5296, "longitude_deg": -119.8138, "radius_km": 500.0},
}
METHODS: dict[str, dict[str, Any]] = {
    "baseline": {
        "tiers": ["core"],
        "modes": ["single", "multi"],
        "cost_per_scan": 1.0,
        "fitted_parameters": [
            "receiver_position",
            "satellite_identity_per_track",
            "constant_cfo_per_track",
        ],
    },
    "global_time": {
        "tiers": ["core"],
        "modes": ["single", "multi"],
        "cost_per_scan": 1.25,
        "fitted_parameters": [
            "receiver_position",
            "satellite_identity_per_track",
            "constant_cfo_per_track",
            "global_time_offset",
        ],
    },
    "per_scan_time": {
        "tiers": ["extended"],
        "modes": ["multi"],
        "cost_per_scan": 1.8,
        "fitted_parameters": [
            "receiver_position",
            "satellite_identity_per_track",
            "constant_cfo_per_track",
            "global_time_offset",
            "scan_time_residual",
        ],
    },
    "independent_per_track_time": {
        "tiers": ["extended", "expansion"],
        "modes": ["single", "multi"],
        "cost_per_scan": 2.0,
        "fitted_parameters": [
            "receiver_position",
            "satellite_identity_per_track",
            "constant_cfo_per_track",
            "independent_track_time_offset",
        ],
    },
    "causal_per_norad_orbit_rate": {
        "tiers": ["extended", "expansion"],
        "modes": ["single", "multi"],
        "cost_per_scan": 2.4,
        "fitted_parameters": [
            "receiver_position",
            "satellite_identity_per_track",
            "constant_cfo_per_track",
            "norad_orbit_phase_rate",
        ],
    },
    "global_time_plus_per_norad_orbit_rate": {
        "tiers": ["extended", "expansion"],
        "modes": ["single", "multi"],
        "cost_per_scan": 2.8,
        "fitted_parameters": [
            "receiver_position",
            "satellite_identity_per_track",
            "constant_cfo_per_track",
            "global_time_offset",
            "norad_orbit_phase_rate",
        ],
    },
    "soft_association": {
        "tiers": ["extended", "expansion"],
        "modes": ["single", "multi"],
        "cost_per_scan": 2.0,
        "fitted_parameters": [
            "receiver_position",
            "candidate_probability_per_track",
            "constant_cfo_per_track",
        ],
    },
    "soft_association_plus_global_time": {
        "tiers": ["extended", "expansion"],
        "modes": ["single", "multi"],
        "cost_per_scan": 2.5,
        "fitted_parameters": [
            "receiver_position",
            "candidate_probability_per_track",
            "constant_cfo_per_track",
            "global_time_offset",
        ],
    },
    "soft_association_plus_global_time_orbit_rate": {
        "supported": False,
        "tiers": ["extended", "expansion"],
        "modes": ["single", "multi"],
        "cost_per_scan": 3.2,
        "fitted_parameters": [
            "receiver_position",
            "candidate_probability_per_track",
            "constant_cfo_per_track",
            "global_time_offset",
            "norad_orbit_phase_rate",
        ],
    },
}


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _train_groups(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    _require(dataset.get("schema") == "ds1-benchmark/v1", "unexpected DS1 dataset schema")
    groups = dataset.get("groups")
    _require(isinstance(groups, list), "dataset groups missing")
    all_sessions: set[str] = set()
    train: list[dict[str, Any]] = []
    for group in groups:
        partition, ids = group.get("partition"), group.get("session_ids")
        _require(partition in {"train", "validation", "test"}, "unknown dataset partition")
        _require(
            isinstance(ids, list) and ids and all(isinstance(x, str) for x in ids),
            "invalid session IDs",
        )
        _require(not all_sessions.intersection(ids), "session belongs to multiple partitions")
        all_sessions.update(ids)
        if partition == "train":
            train.append(group)
    _require(train, "DS1 has no TRAIN groups")
    _require(
        all(g["group_id"] in TRAIN_CACHE_ROOTS for g in train), "TRAIN cache root not declared"
    )
    return train


def _add_case(
    cases: dict[tuple[str, ...], dict[str, Any]],
    group_id: str,
    ids: list[str],
    kind: str,
    label: str,
) -> None:
    key = tuple(ids)
    if key in cases:
        cases[key]["selection_kinds"].append(kind)
        return
    cases[key] = {
        "case_id": f"train-{group_id}--{label}",
        "group_id": group_id,
        "session_ids": ids,
        "scan_count": len(ids),
        "mode": "single" if len(ids) == 1 else "multi",
        "selection_kinds": [kind],
    }


def build_cases(dataset: dict[str, Any], singleton_bins: int = 8) -> list[dict[str, Any]]:
    """Use recorded order only: all singles, prefixes, disjoint blocks, and full groups."""
    _require(singleton_bins >= 2, "singleton_bins must be at least two")
    train = _train_groups(dataset)
    cases: dict[tuple[str, ...], dict[str, Any]] = {}
    for group in train:
        group_id, ids = group["group_id"], list(group["session_ids"])
        for index, sid in enumerate(ids):
            _add_case(cases, group_id, [sid], "every_single_scan", f"single-{index:03d}")
        for count in (2, 4, 8, 16, 32):
            if count > len(ids):
                continue
            _add_case(cases, group_id, ids[:count], "nested_prefix", f"prefix-{count:03d}")
            for start in range(0, len(ids) - count + 1, count):
                _add_case(
                    cases,
                    group_id,
                    ids[start : start + count],
                    "disjoint_block",
                    f"block-{count:03d}-{start // count:03d}",
                )
        _add_case(cases, group_id, ids, "full_train_group", "all")
    _add_case(
        cases,
        "combined_train",
        [sid for group in train for sid in group["session_ids"]],
        "combined_train_groups",
        "all",
    )
    stratified = {
        group["group_id"]: {
            group["session_ids"][round(i * (len(group["session_ids"]) - 1) / (singleton_bins - 1))]
            for i in range(singleton_bins)
        }
        for group in train
    }
    result = list(cases.values())
    for case in result:
        case["chronology_stratified_singleton"] = (
            case["mode"] == "single"
            and case["group_id"] in stratified
            and case["session_ids"][0] in stratified[case["group_id"]]
        )
    return sorted(result, key=lambda row: (row["group_id"], row["scan_count"], row["case_id"]))


def _eligible(spec: dict[str, Any], case: dict[str, Any], tier: str) -> bool:
    if tier not in spec["tiers"] or case["mode"] not in spec["modes"]:
        return False
    if tier == "extended" and case["mode"] == "single":
        return case["chronology_stratified_singleton"]
    return tier != "expansion" or (
        case["mode"] == "single" and not case["chronology_stratified_singleton"]
    )


def build_manifest(
    dataset: dict[str, Any],
    source_digest: str,
    singleton_bins: int = 8,
    include_expansion: bool = False,
) -> dict[str, Any]:
    cases, tasks = build_cases(dataset, singleton_bins), []
    for case in cases:
        for method, spec in METHODS.items():
            if spec.get("supported", True) is False:
                continue
            for tier in spec["tiers"]:
                if tier == "expansion" and not include_expansion:
                    continue
                if not _eligible(spec, case, tier):
                    continue
                for prior_name, prior in PRIORS.items():
                    task_id = f"{case['case_id']}--{prior_name}--{method}--{tier}"
                    scan_inputs = [
                        {
                            "session_id": session_id,
                            "group_id": group["group_id"],
                            "causal_state_cache_root": TRAIN_CACHE_ROOTS[group["group_id"]],
                        }
                        for group in _train_groups(dataset)
                        for session_id in group["session_ids"]
                        if session_id in case["session_ids"]
                    ]
                    tasks.append(
                        {
                            "schema": TASK_SCHEMA,
                            "task_id": task_id,
                            "partition": "train",
                            "tier": tier,
                            "group_id": case["group_id"],
                            "case_id": case["case_id"],
                            "selection_kinds": case["selection_kinds"],
                            "session_ids": case["session_ids"],
                            "scan_count": case["scan_count"],
                            "prior": {"name": prior_name, **prior},
                            "method": method,
                            "options": {
                                "observation_policy": "all_qualified_observations",
                                "within_track_holdout": "forbidden",
                                "frequency_loss_cap_hz": 800.0,
                                "minimum_track_duration_s": 3.0,
                                "altitude_m": 0.0,
                                "fitted_parameters": spec["fitted_parameters"],
                                "geographic_sharding": {
                                    "runner_may_partition": True,
                                    "selection": "rf_objective_only",
                                },
                                "causal_cache_validation": {
                                    "require_cache_receipt": True,
                                    "require_session_id_match": True,
                                    "require_receipt_cache_digest_match": True,
                                },
                            },
                            "input_scans": scan_inputs,
                            "estimated_cost": {
                                "work_units": round(case["scan_count"] * spec["cost_per_scan"], 3),
                                "relative_per_scan": spec["cost_per_scan"],
                            },
                            "output_path": f"artifacts/{method}/{task_id}.json",
                        }
                    )
    _require(len({task["task_id"] for task in tasks}) == len(tasks), "duplicate task ID")
    return {
        "schema": SCHEMA,
        "name": "DS1 TRAIN full-observation development benchmark",
        "version": 1,
        "source_dataset_sha256": source_digest,
        "partitions_permitted": ["train"],
        "position_evaluation": "post_seal_external_only",
        "reference_coordinate_in_manifest": False,
        "priors": PRIORS,
        "methods": METHODS,
        "case_count": len(cases),
        "task_count": len(tasks),
        "tiers": {
            "core": (
                "baseline and global time on every TRAIN singleton and declared multi-scan case"
            ),
            "extended": (
                "expensive methods on chronology-stratified singletons and every "
                "declared multi-scan case"
            ),
            "expansion": "remaining expensive singleton tasks after runtime review",
        },
        "expansion_included": include_expansion,
        "tasks": sorted(tasks, key=lambda row: row["task_id"]),
    }


def validate_task(task: dict[str, Any], report_root: Path) -> None:
    _require(task.get("schema") == TASK_SCHEMA, "unexpected task schema")
    _require(task.get("partition") == "train", "only TRAIN inference tasks are permitted")
    _require(task.get("method") in METHODS, "unknown method")
    _require(task.get("prior", {}).get("name") in PRIORS, "unknown prior")
    _require(
        task.get("scan_count") == len(task.get("session_ids", [])) and task["scan_count"] > 0,
        "invalid scan count",
    )
    options = task.get("options", {})
    _require(
        options.get("observation_policy") == "all_qualified_observations",
        "full-observation policy required",
    )
    _require(options.get("within_track_holdout") == "forbidden", "within-track holdout prohibited")
    cache_validation = options.get("causal_cache_validation", {})
    _require(
        all(
            cache_validation.get(key) is True
            for key in (
                "require_cache_receipt",
                "require_session_id_match",
                "require_receipt_cache_digest_match",
            )
        ),
        "strict causal cache validation required",
    )
    inputs = task.get("input_scans")
    _require(
        isinstance(inputs, list)
        and [row.get("session_id") for row in inputs] == task["session_ids"],
        "input scan order mismatch",
    )
    _require(
        all(
            row.get("group_id") in TRAIN_CACHE_ROOTS
            and row.get("causal_state_cache_root") == TRAIN_CACHE_ROOTS[row["group_id"]]
            for row in inputs
        ),
        "non-TRAIN cache root",
    )
    root, output = report_root.resolve(), (report_root / task.get("output_path", "")).resolve()
    _require(output.is_relative_to(root / "artifacts"), "output must remain under report artifacts")
    _require(output.suffix == ".json", "output must be JSON")


def validate_result(task: dict[str, Any], result: dict[str, Any]) -> None:
    _require(result.get("schema") == RESULT_SCHEMA, "unexpected result schema")
    _require(result.get("task_id") == task["task_id"], "result task ID mismatch")
    _require(result.get("partition") == "train", "result partition must be TRAIN")
    _require(
        result.get("reference_used_for_fit") is False,
        "runner must attest that no reference was used",
    )
    usage = result.get("observation_use", {})
    _require(
        usage.get("policy") == "all_qualified_observations",
        "result did not use all qualified observations",
    )
    _require(usage.get("heldout_observation_count") == 0, "held-out observations are prohibited")
    estimate = result.get("estimated_position", {})
    _require(isinstance(estimate.get("latitude_deg"), (int, float)), "missing estimated latitude")
    _require(isinstance(estimate.get("longitude_deg"), (int, float)), "missing estimated longitude")
    forbidden = {
        "reference_coordinate",
        "truth_coordinate",
        "ground_truth_coordinate",
        "reference_error_km",
    }
    _require(
        not forbidden.intersection(result), "inference result contains post-seal reference data"
    )
