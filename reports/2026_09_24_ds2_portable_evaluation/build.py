#!/usr/bin/env python3
"""Freeze all Sept-24 DS2 sessions and portable-development tasks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
PRIOR = {
    "name": "sacramento-250km-predeclared",
    "lat": 38.5816,
    "lon": -121.4944,
    "radius_km": 250.0,
    "reference_used_for_selection": False,
}


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_sealed(path: Path, value: Any) -> None:
    content = canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


def product_receipt(endpoint: str, session_id: str) -> dict[str, Any]:
    with urlopen(f"{endpoint.rstrip('/')}/{session_id}", timeout=20) as response:  # noqa: S310
        status = json.load(response)
    product = status.get("product") if isinstance(status.get("product"), dict) else {}
    if status.get("state") != "complete" or product.get("analysis_id") != (
        "scanner-shared-tracking-v14"
    ):
        raise RuntimeError(f"authoritative V14 tracking is incomplete: {session_id}")
    return {
        "state": "complete",
        "analysis_id": product["analysis_id"],
        "analysis_manifest_sha256": product["analysis_manifest_sha256"],
        "input_manifest_sha256": product["input_manifest_sha256"],
        "configuration_digest": product["configuration_digest"],
        "candidate_policy_digest": product["tle_match_config_digest"],
        "tracklet_count": len(product.get("tracklets", [])),
    }


def cache_receipt(cache_root: Path, session_id: str) -> dict[str, Any]:
    root = cache_root / session_id
    receipt_path, cache_path = root / "cache_receipt.json", root / "state_cache.npz"
    if not receipt_path.is_file() or not cache_path.is_file():
        raise RuntimeError(f"causal cache is absent: {session_id}")
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("session_id") != session_id:
        raise ValueError(f"cache session binding mismatch: {session_id}")
    if receipt.get("bindings", {}).get("state_cache") != digest(cache_path):
        raise ValueError(f"cache digest mismatch: {session_id}")
    evidence = receipt["prepared_evidence"]
    return {
        "receipt_sha256": digest(receipt_path),
        "state_cache_sha256": digest(cache_path),
        "candidate_policy": receipt["candidate_policy"],
        "candidate_count": receipt["candidate_counts"]["regional_grid_retained"],
        "eligible_track_count": evidence["eligible_track_count"],
        "eligible_observation_count": evidence["eligible_observation_count"],
        "snapshot_digest": evidence["snapshot_digest"],
        "snapshot_collected_utc_ns": evidence["snapshot_collected_utc_ns"],
    }


def task(
    task_id: str,
    sessions: list[str],
    method: str,
    output: Path,
    *,
    joint: bool = False,
) -> dict[str, Any]:
    levels = [100.0, 25.0, 6.25] if not joint else [100.0, 25.0, 6.25, 1.5625]
    options: dict[str, Any] = {
        "observation_policy": "all_qualified_observations",
        "within_track_holdout": "forbidden",
        "minimum_track_duration_s": 3.0,
        "frequency_loss_cap_hz": 800.0,
        "tau_grid_s": [-5.0, -3.0, -1.0, 0.0, 1.0, 3.0, 5.0],
        "geographic_levels_km": levels,
        "search_levels_km": levels,
        "beam_width": 3,
        "exact_rate_finalists": 2,
        "exact_rate_workers": 2,
        "equal_session_weight": joint,
        "per_scan_sigma_s": 1.0,
        "per_scan_penalty_weight": 0.01,
        "per_scan_delta_limit_s": 5.0,
    }
    return {
        "task_id": task_id,
        "partition": "development",
        "group_id": "ds2-sept24-all" if joint else f"ds2-single-{sessions[0]}",
        "session_ids": sessions,
        "prior": PRIOR,
        "method": method,
        "output_path": str(output.resolve()),
        "options": options,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory", type=Path, default=HERE.parent / "2026_09_24_ds2_inventory/manifest.json"
    )
    parser.add_argument(
        "--final-manifest",
        type=Path,
        default=HERE.parent / "2026_09_24_ds2_final_manifest/manifest.json",
    )
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument(
        "--endpoint", default="http://127.0.0.1:8090/api/v1/scanner/tracking"
    )
    parser.add_argument("--output", type=Path, default=HERE)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text())
    scans = [
        row for row in inventory["scans"] if row["inclusion"]["raw_capture_eligible"] is True
    ]
    if len(scans) != 20 or len({row["session_id"] for row in scans}) != 20:
        raise ValueError(
            "frozen DS2 inventory must contain exactly 20 unique raw-eligible sessions"
        )
    final_manifest = json.loads(args.final_manifest.read_text())
    final_ids = {row["session_id"] for row in final_manifest["sessions"]}
    if final_ids != {row["session_id"] for row in scans}:
        raise ValueError("portable dataset differs from the sealed final DS2 corpus")
    sessions = []
    for scan in scans:
        sid = scan["session_id"]
        sessions.append(
            {
                "session_id": sid,
                "captured_at": scan["captured_at"],
                "radio_id": scan["radio_id"],
                "sample_rate_hz": scan["sample_rate_hz"],
                "tracking": product_receipt(args.endpoint, sid),
                "cache": cache_receipt(args.cache_root, sid),
            }
        )
    dataset = {
        "schema": "ds2-portable-development-dataset/v1",
        "name": "DS2",
        "development_evaluation": True,
        "whole_session_policy": "all 20 frozen Sept-24 raw-eligible captures; no split excluded",
        "reference_coordinate_present": False,
        "position_evaluation": "post_seal_external_only",
        "prior": PRIOR,
        "inventory_sha256": digest(args.inventory),
        "final_manifest_sha256": digest(args.final_manifest),
        "cache_root_runtime_only": str(args.cache_root.resolve()),
        "sessions": sessions,
    }
    write_sealed(args.output / "dataset.json", dataset)
    output_root = args.output / "inference"
    tasks = []
    for row in sessions:
        sid = row["session_id"]
        for label, method in (
            ("baseline", "baseline"),
            ("shared-time", "shared_global_tau"),
            ("causal-rate", "causal_per_norad_orbit_rate"),
            ("independent-track-time", "independent_per_track_tau"),
            ("soft-identity", "soft_joint_association"),
        ):
            tasks.append(
                task(
                    f"single__{sid}__{label}",
                    [sid],
                    method,
                    output_root / f"single__{sid}__{label}.json",
                )
            )
    all_ids = [row["session_id"] for row in sessions]
    for label, method in (
        ("baseline", "baseline"),
        ("shared-time", "shared_global_tau"),
        ("regularized-per-scan-time", "regularized_per_scan_tau"),
        ("independent-track-time", "independent_per_track_tau"),
        ("soft-identity", "soft_association_global_tau"),
        ("equal-weight-joint-rate", "global_tau_per_norad_orbit_rate"),
    ):
        tasks.append(
            task(
                f"joint-all20__{label}",
                all_ids,
                method,
                output_root / f"joint-all20__{label}.json",
                joint=True,
            )
        )
    plan = {
        "schema": "ds2-portable-development-plan/v1",
        "dataset_sha256": digest(args.output / "dataset.json"),
        "reference_coordinate_present": False,
        "task_count": len(tasks),
        "single_scan_task_count": 100,
        "joint_task_count": 6,
        "tasks": tasks,
    }
    write_sealed(args.output / "plan.json", plan)
    tasks_dir = args.output / "tasks"
    tasks_dir.mkdir(exist_ok=True)
    for row in tasks:
        write_sealed(tasks_dir / f"{row['task_id']}.json", row)
    print(canonical({"dataset_sessions": len(sessions), "tasks": len(tasks)}), end="")


if __name__ == "__main__":
    main()
