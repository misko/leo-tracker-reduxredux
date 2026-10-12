"""Bounded corpus preparation and merging census with pinned membership and code."""

import argparse
import hashlib
import json
import runpy
import signal
import time
from collections import Counter
from dataclasses import asdict, is_dataclass
from pathlib import Path

import numpy as np

from leo.analysis.continuous_track_merge import ContinuousMergeConfiguration
from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
from leo.application.continuous_merge_inputs import merged_position_inputs
from leo.application.regional_position_inputs import prepare_position_windows
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_12_continuous_track_merge"
LOCAL = REPORT / "local"
AUTHORITIES = {
    "DS20": Path(
        "/srv/bulk/leo-dev/leo-ds20-eight-channel/reports/2026_10_12_ds20_eight_channel/manifest.json"
    ),
    "DS16": Path(
        "/home/mouse9911/gits/leo-hard60-default/reports/2026_10_08_ds16_last16h/manifest.json"
    ),
}
LOADER = Path("/opt/leo-fast-auto/20261011-r3/bin/fast_scan_standard_pipeline.py")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plain(value), indent=2, allow_nan=False) + "\n")


def mint():
    if (REPORT / "membership.json").exists():
        raise ValueError("study membership already exists")
    members, authorities = [], {}
    for dataset, path in AUTHORITIES.items():
        data = json.loads(path.read_bytes())
        authorities[dataset] = {"path": str(path), "sha256": sha(path)}
        population = data["members"] if dataset == "DS20" else data["captures"]
        population = sorted(population, key=lambda m: m["session_id"])
        order = np.random.default_rng(20261012).permutation(len(population))
        validation = set(order[: int(np.ceil(len(population) / 3))].tolist())
        for i, member in enumerate(population):
            entry = {
                "dataset": dataset,
                "session_id": member["session_id"],
                "role": "validation" if i in validation else "development",
                "selection": "whole recording; independent of readiness and position accuracy",
            }
            if dataset == "DS20":
                if member["tracking_inputs"]:
                    entry["tracking_input"] = member["tracking_inputs"][0]
                else:
                    recovery = path.parent / "recovery" / member["session_id"]
                    receipt_path = recovery / "recovery-receipt.json"
                    if receipt_path.exists():
                        receipt = json.loads(receipt_path.read_bytes())
                        entry["tracking_input"] = {
                            "path": str(recovery / "tracking-input.json"),
                            "sha256": receipt["tracking_input_sha256"],
                            "recovery_receipt": str(receipt_path),
                            "recovery_receipt_sha256": sha(receipt_path),
                            "qualification": receipt["qualification"],
                        }
                    else:
                        entry["input_unavailable"] = "no published or sealed recovered GLRT input"
            else:
                entry["recording_manifest_sha256"] = member["recording_manifest_sha256"]
            members.append(entry)
    write(
        REPORT / "membership.json",
        {
            "authorities": authorities,
            "members": members,
            "seed": 20261012,
            "generator": "numpy.PCG64",
            "missing_authority": ["DS15"],
            "scope": (
                "DS20 and DS16 are exposed development corpora; randomized whole-recording split"
            ),
        },
    )
    bindings = {}
    for directory, patterns in (
        (ROOT / "src/leo/analysis", ["*.py"]),
        (ROOT / "src/leo/application", ["*.py"]),
        (ROOT / "src/leo/contracts", ["*.py"]),
    ):
        for pattern in patterns:
            for source in directory.glob(pattern):
                bindings[str(source)] = sha(source)
    bindings[str(Path(__file__))] = sha(Path(__file__))
    bindings[str(LOADER)] = sha(LOADER)
    write(
        REPORT / "protocol.json",
        {
            "membership_sha256": sha(REPORT / "membership.json"),
            "source_bindings": bindings,
            "merge": asdict(ContinuousMergeConfiguration()),
            "variants": ["replace-guard", "append-guard", "replace-no-guard"],
            "position_ablation": (
                "baseline versus each variant, matched initial bank/prior/search budget"
            ),
            "c_ablation": (
                "c=0 versus fitted c with common fitted-c upstream conditioning per variant"
            ),
            "reference_usage": (
                "only evaluation after receipts sealed; never joins or model selection"
            ),
            "collection": "none; existing GLRT inputs only",
            "per_recording_limit_s": 45,
        },
    )
    print(
        json.dumps(
            {"members": len(members), "datasets": dict(Counter(m["dataset"] for m in members))}
        )
    )


class CaseTimeout(Exception):
    pass


def expired(*_):
    raise CaseTimeout("45-second per-recording preparation limit")


def source_for(member):
    if member["dataset"] == "DS20":
        if "tracking_input" not in member:
            raise ValueError(member["input_unavailable"])
        receipt = member["tracking_input"]
        path = Path(receipt["path"])
        if "sha256:" + sha(path) != receipt["sha256"]:
            raise ValueError("DS20 pinned GLRT input changed")
        source = runpy.run_path(str(LOADER))["load_tracking_input"](
            json.loads(path.read_bytes())
        )
        if source.session_id != member["session_id"]:
            raise ValueError("DS20 session mismatch")
        return source
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = store.load(member["session_id"])
    finally:
        store.close()
    if source.input_manifest_sha256 != member["recording_manifest_sha256"]:
        raise ValueError("DS16 recording manifest changed")
    return source


def census(limit, maximum_seconds):
    protocol = json.loads((REPORT / "protocol.json").read_bytes())
    if sha(REPORT / "membership.json") != protocol["membership_sha256"]:
        raise ValueError("membership changed")
    for path, expected in protocol["source_bindings"].items():
        if sha(Path(path)) != expected:
            raise ValueError("bound source changed: " + path)
    membership = json.loads((REPORT / "membership.json").read_bytes())["members"]
    # Interleave datasets so bounded batches cover both rather than waiting on
    # an entire dataset. Order is fixed before any scientific score is read.
    groups = {name: [m for m in membership if m["dataset"] == name] for name in ("DS20", "DS16")}
    ordered = [
        groups[name][i]
        for i in range(max(map(len, groups.values())))
        for name in groups
        if i < len(groups[name])
    ]
    started, completed = time.monotonic(), 0
    previous_handler = signal.signal(signal.SIGALRM, expired)
    try:
        for member in ordered:
            case = LOCAL / member["dataset"] / member["session_id"]
            if (case / "census.json").exists():
                continue
            if completed >= limit or time.monotonic() - started > maximum_seconds - 45:
                break
            result = {"member": member, "status": "failed", "reference_usage": "none"}
            begin = time.monotonic()
            signal.setitimer(signal.ITIMER_REAL, 45)
            try:
                source = source_for(member)
                prepared = prepare_position_windows(source)
                by_id = {p.candidate_id: p for p in project_scanner_candidates(source)}
                candidates = tuple(by_id[i] for i in prepared.candidate_ids)
                trajectory = reconstruct_persistent_hop_trajectories(candidates)
                write(case / "source.json", source)
                write(case / "baseline.json", prepared)
                variants = {}
                for mode, guard in (("replace", True), ("append", True), ("replace", False)):
                    name = mode + ("-guard" if guard else "-no-guard")
                    merged, receipt = merged_position_inputs(
                        prepared, trajectory, candidates, mode=mode, residual_guard=guard
                    )
                    assert merged.observations is prepared.observations
                    write(case / (name + ".json"), merged)
                    variants[name] = receipt
                result.update(
                    status="complete",
                    windows=len(prepared.candidate_ids),
                    original_segments=len(trajectory.tracklets),
                    variants=variants,
                    input_manifest_sha256=source.input_manifest_sha256,
                    analysis_manifest_sha256=source.analysis_manifest_sha256,
                )
            except (ValueError, OSError, CaseTimeout) as error:
                result["reason"] = f"{type(error).__name__}: {error}"
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
            result["elapsed_s"] = time.monotonic() - begin
            write(case / "census.json", result)
            print(
                json.dumps(
                    {
                        "dataset": member["dataset"],
                        "session": member["session_id"],
                        "status": result["status"],
                        "elapsed_s": result["elapsed_s"],
                        "joins": result.get("variants", {})
                        .get("replace-guard", {})
                        .get("selected_join_count"),
                        "reason": result.get("reason"),
                    }
                ),
                flush=True,
            )
            completed += 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    rows = [json.loads(path.read_bytes()) for path in sorted(LOCAL.glob("*/*/census.json"))]
    write(
        REPORT / "census-summary.json",
        {
            "membership": len(membership),
            "processed": len(rows),
            "complete": sum(r["status"] == "complete" for r in rows),
            "failed": sum(r["status"] != "complete" for r in rows),
            "rows": [
                {k: r[k] for k in ("member", "status", "elapsed_s", "reason") if k in r}
                | (
                    {"guarded_joins": r["variants"]["replace-guard"]["selected_join_count"]}
                    if r["status"] == "complete"
                    else {}
                )
                for r in rows
            ],
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("mint", "census"))
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--maximum-seconds", type=float, default=420)
    args = parser.parse_args()
    mint() if args.command == "mint" else census(args.limit, args.maximum_seconds)
