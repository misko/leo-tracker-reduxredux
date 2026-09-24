#!/usr/bin/env python3
"""Replicate the frozen conditional joint-position method on disjoint scan groups."""

# ruff: noqa: E402
from __future__ import annotations

import os

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import hashlib
import importlib.util
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

TRUTH = (37.84903264307456, -122.4856541910174)


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _joint_module():
    path = Path(__file__).with_name("sixteen_joint_compare.py")
    spec = importlib.util.spec_from_file_location("frozen_sixteen_joint", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def _groups(inventory: dict) -> list[dict]:
    rows = inventory.get("groups", inventory.get("blocks"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("inventory requires a nonempty groups or blocks list")
    parsed = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        sessions = row.get("session_ids", row.get("sessions"))
        if (
            not isinstance(sessions, list)
            or not sessions
            or not all(isinstance(x, str) for x in sessions)
        ):
            raise ValueError("every group requires session_ids")
        if len(set(sessions)) != len(sessions) or seen.intersection(sessions):
            raise ValueError("replication groups must be internally unique and disjoint")
        seen.update(sessions)
        parsed.append(
            {
                "group_id": str(row.get("group_id", row.get("block_id", index))),
                "session_ids": sessions,
            }
        )
    return parsed


def _scan_summary(joint, session_id: str) -> dict:
    status = joint._fetch(f"/api/v1/scanner/tracking/{session_id}/adaptive-tle-position-v2")
    document = status["manifest"]["document"]
    if document["state"] != "diagnostic":
        raise ValueError(f"{session_id} lacks completed position evidence")
    diagnostics = document["diagnostics"]
    priors = {}
    by_name = {row["name"]: row for row in document["priors"]}
    for name in ("sacramento", "reno"):
        row = by_name[name]
        priors[name] = {
            "selected": row["selected"],
            "finest": row["finest"],
            "accounting": row["accounting"],
        }
    return {
        "session_id": session_id,
        "priors": priors,
        "input_manifest_sha256": document["input_manifest_sha256"],
        "analysis_manifest_sha256": document["analysis_manifest_sha256"],
        "snapshot_digest": diagnostics["snapshot_digest"],
    }


def _mean_control(joint, scans: list[dict], prior: str) -> dict:
    points = np.asarray(
        [
            [
                row["priors"][prior]["selected"]["latitude_deg"],
                row["priors"][prior]["selected"]["longitude_deg"],
            ]
            for row in scans
        ]
    )
    point = np.mean(points, axis=0)
    return {
        "method": f"mean-{prior}",
        "latitude_deg": float(point[0]),
        "longitude_deg": float(point[1]),
        "error_km": joint.haversine_km(tuple(point), TRUTH),
    }


def run(args) -> dict:
    if args.output.exists():
        raise FileExistsError("replication output must be fresh")
    inventory = json.loads(args.inventory.read_text())
    groups = _groups(inventory)
    frozen = {row["session_id"]: row for row in inventory.get("scans", [])}
    original_path = Path("reports/2026_09_23_sixteen_scan_position_resolution/selection.json")
    original = set(json.loads(original_path.read_text())["session_ids"])
    overlap = original.intersection(s for row in groups for s in row["session_ids"])
    if overlap:
        raise ValueError(f"replication inventory overlaps original frozen scans: {sorted(overlap)}")
    joint, joint_path = _joint_module()
    args.output.mkdir(parents=True)
    started = time.monotonic()

    def one_group(group):
        group_started = time.monotonic()
        directory = args.output / group["group_id"]
        scans = [_scan_summary(joint, sid) for sid in group["session_ids"]]
        for scan in scans:
            authority = frozen.get(scan["session_id"])
            if authority is None or authority.get("state") != "eligible":
                raise ValueError("group session lacks frozen eligible inventory authority")
            for key in ("input_manifest_sha256", "analysis_manifest_sha256"):
                if scan[key] != authority[key]:
                    raise ValueError(f"{scan['session_id']} changed after inventory freeze: {key}")
        # The reused cache builder accepts the original newest-first selection contract.
        selection = {
            "rule": "frozen disjoint replication group; reversed only for cache adapter",
            "session_ids": list(reversed(group["session_ids"])),
        }
        _write(directory / "selection.json", selection)
        _write(directory / "scans.json", scans)
        joint.build_cache(directory / "selection.json", directory / "cache")
        comparison = joint.compare(
            directory / "cache", directory / "scans.json", directory, args.budget_seconds
        )
        comparison["results"] = [
            row for row in comparison["results"] if row["scan_count"] <= len(scans)
        ]
        _write(directory / "results.json", comparison)
        full = next(row for row in comparison["results"] if row["scan_count"] == len(scans))
        controls = [_mean_control(joint, scans, name) for name in ("sacramento", "reno")]
        return {
            "group_id": group["group_id"],
            "session_ids": group["session_ids"],
            "scan_count": len(scans),
            "joint": full,
            "controls": controls,
            "complete_16_scan_block": len(scans) == 16,
            "continuity_note": (
                "contains a development-removal gap; not continuous IQ"
                if group["group_id"] == "block_04"
                else "chronological eligible scans; not continuous IQ"
            ),
            "runtime_s": time.monotonic() - group_started,
        }

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(one_group, groups))
    for row in results:
        _write(args.output / row["group_id"] / "replication_result.json", row)
    errors = [row["joint"]["best"]["error_km"] for row in results]
    complete_errors = [
        row["joint"]["best"]["error_km"] for row in results if row["complete_16_scan_block"]
    ]
    summary = {
        "schema": "day-position-independent-replication/v1",
        "inventory_sha256": "sha256:" + hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
        "original_session_overlap": 0,
        "groups_disjoint": True,
        "method_frozen_before_replication_truth_evaluation": True,
        "candidate_scope": "per-scan union of block-local production Sacramento/Reno selections",
        "validation_limit": (
            "production randomized evaluation rows were reused in candidate/location selection"
        ),
        "group_count": len(results),
        "results": results,
        "joint_error_km": {
            "values": errors,
            "median": float(np.median(errors)),
            "maximum": float(np.max(errors)),
            "within_0_3_km": int(np.sum(np.asarray(errors) <= 0.3)),
        },
        "complete_16_scan_joint_error_km": {
            "values": complete_errors,
            "median": float(np.median(complete_errors)),
            "maximum": float(np.max(complete_errors)),
            "within_0_3_km": int(np.sum(np.asarray(complete_errors) <= 0.3)),
        },
        "runtime_s": time.monotonic() - started,
        "source_digest": "sha256:" + hashlib.sha256(joint_path.read_bytes()).hexdigest(),
    }
    _write(args.output / "results.json", summary)
    fig = Figure(figsize=(8, 4), layout="constrained")
    ax = fig.subplots()
    x = np.arange(len(results))
    width = 0.25
    ax.bar(x - width, errors, width, label="Joint integer")
    ax.bar(x, [r["controls"][0]["error_km"] for r in results], width, label="Mean Sacramento")
    ax.bar(x + width, [r["controls"][1]["error_km"] for r in results], width, label="Mean Reno")
    ax.axhline(0.3, color="black", linestyle="--", linewidth=1, label="300 m")
    ax.set(
        xticks=x,
        xticklabels=[r["group_id"] for r in results],
        ylabel="Position error (km)",
        xlabel="Frozen disjoint scan group",
        title="Independent group replication",
    )
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.savefig(args.output / "replication.png", dpi=160)
    return summary


def summarize_existing(inventory_path: Path, output: Path) -> dict:
    inventory = json.loads(inventory_path.read_text())
    results = []
    for group in _groups(inventory):
        directory = output / group["group_id"]
        row = json.loads((directory / "replication_result.json").read_text())
        comparison_path = directory / "results.json"
        comparison = json.loads(comparison_path.read_text())
        comparison["results"] = [
            item for item in comparison["results"] if item["scan_count"] <= row["scan_count"]
        ]
        _write(comparison_path, comparison)
        ordered = sorted(comparison["results"], key=lambda item: item["scan_count"])
        fig = Figure(figsize=(9, 4), layout="constrained")
        axes = fig.subplots(1, 2)
        axes[0].plot(
            [x["scan_count"] for x in ordered], [x["best"]["rmse_hz"] for x in ordered], "o-"
        )
        axes[1].plot(
            [x["scan_count"] for x in ordered], [x["best"]["error_km"] for x in ordered], "o-"
        )
        axes[0].set(xlabel="Scans accumulated", ylabel="Selection RMS (Hz)")
        axes[1].set(xlabel="Scans accumulated", ylabel="Evaluation-only error (km)")
        for axis in axes:
            axis.grid(alpha=0.25)
            axis.set_xscale("log", base=2)
            axis.set_xticks([x["scan_count"] for x in ordered])
            axis.get_xaxis().set_major_formatter("{x:g}")
        fig.savefig(directory / "comparison.png", dpi=160)
        results.append(row)
    errors = [row["joint"]["best"]["error_km"] for row in results]
    complete = [
        row["joint"]["best"]["error_km"] for row in results if row["complete_16_scan_block"]
    ]
    summary = json.loads((output / "results.json").read_text())
    summary["results"] = results
    summary["joint_error_km"] = {
        "values": errors,
        "median": float(np.median(errors)),
        "maximum": float(np.max(errors)),
        "within_0_3_km": int(np.sum(np.asarray(errors) <= 0.3)),
    }
    summary["complete_16_scan_joint_error_km"] = {
        "values": complete,
        "median": float(np.median(complete)),
        "maximum": float(np.max(complete)),
        "within_0_3_km": int(np.sum(np.asarray(complete) <= 0.3)),
    }
    summary["source_digest"] = "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    _write(output / "results.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget-seconds", type=float, default=900)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--summarize-existing", action="store_true")
    args = parser.parse_args()
    result = (
        summarize_existing(args.inventory, args.output) if args.summarize_existing else run(args)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
