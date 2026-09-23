#!/usr/bin/env python3
"""Verify full-8h frozen TRAIN search inputs, seal, and post-seal accounting."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--search", type=Path, required=True)
    parser.add_argument("--single-tool", type=Path, required=True)
    parser.add_argument("--fast-loader", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    group = manifest["source_group"]
    sessions = group["session_ids"]
    if group["utc_8h_start"] != "2026-09-21T00:00:00+00:00" or len(sessions) != 72:
        raise ValueError("expected the frozen 72-scan Sep21 00Z TRAIN group")
    if len(set(sessions)) != len(sessions):
        raise ValueError("frozen session IDs are not unique")

    inference_path = args.results / "inference.json"
    sealed_sha = (args.results / "inference.sha256").read_text().strip()
    actual_sha = hashlib.sha256(inference_path.read_bytes()).hexdigest()
    if sealed_sha != actual_sha:
        raise ValueError("inference seal does not match inference.json")
    inference = json.loads(inference_path.read_text())
    result = json.loads((args.results / "results.json").read_text())
    if inference["position_truth_used"] or inference["reserved_rows_used"]:
        raise ValueError("inference was not TRAIN-only blind scoring")
    if inference["session_ids"] != sessions or inference["scan_count"] != 72:
        raise ValueError("inference session list differs from frozen manifest")
    bindings = inference["bindings"]
    expected = {
        "manifest": digest(args.manifest),
        "tool": digest(args.search),
        "single_tool": digest(args.single_tool),
        "fast_loader": digest(args.fast_loader),
    }
    if {key: bindings[key] for key in expected} != expected:
        raise ValueError("source binding digest mismatch")
    if len(bindings["sessions"]) != 72:
        raise ValueError("inference lacks cache bindings")

    tracks = observations = cache_bytes = 0
    for bound, session in zip(bindings["sessions"], sessions, strict=True):
        if bound["session_id"] != session:
            raise ValueError("cache binding order differs from manifest")
        directory = args.cache_root / session
        receipt_path = directory / "cache_receipt.json"
        cache_path = directory / "state_cache.npz"
        if digest(receipt_path) != bound["receipt"] or digest(cache_path) != bound["cache"]:
            raise ValueError(f"cache digest mismatch for {session}")
        receipt = json.loads(receipt_path.read_text())
        if receipt["session_id"] != session:
            raise ValueError(f"receipt session mismatch for {session}")
        evidence = receipt["prepared_evidence"]
        tracks += evidence["eligible_track_count"]
        observations += evidence["eligible_observation_count"]
        cache_bytes += cache_path.stat().st_size

    qualifying = json.loads(args.qualification.read_text())
    qgroup = next(
        row
        for row in qualifying["groups"]
        if [scan["session_id"] for scan in row["scans"]] == sessions
    )
    if qgroup["failure_count"] or qgroup["position_input_ready_count"] != 72:
        raise ValueError("qualification is incomplete")
    if (
        tracks != qgroup["eligible_3s_track_count"]
        or observations != qgroup["eligible_observation_count"]
    ):
        raise ValueError("cache evidence count differs from qualification")

    if len(result["searches"]) != len(inference["searches"]) or len(result["searches"]) != 2:
        raise ValueError("expected both sealed prior results")
    for sealed, held in zip(inference["searches"], result["searches"], strict=True):
        retained = {key: held["selected"][key] for key in sealed["selected"]}
        if sealed["prior"] != held["prior"] or sealed["selected"] != retained:
            raise ValueError("held result changed a sealed selected inference")
        if len(held["selected"]["scans"]) != 72:
            raise ValueError("held scoring does not cover all frozen scans")

    payload = {
        "schema": "long-training-full8h-position-accounting/v1",
        "frozen_group": group["utc_8h_start"],
        "session_count": len(sessions),
        "all_sessions_unique": True,
        "cache_verified_count": len(sessions),
        "cache_state_bytes": cache_bytes,
        "eligible_track_count": tracks,
        "eligible_observation_count": observations,
        "qualification": {
            "summed_capture_duration_s": qgroup["summed_capture_duration_s"],
            "elapsed_capture_span_s": qgroup["elapsed_capture_span_s"],
            "max_inter_capture_start_gap_s": qgroup["max_inter_capture_start_gap_s"],
            "failure_count": qgroup["failure_count"],
        },
        "inference_seal_sha256": "sha256:" + actual_sha,
        "results_sha256": digest(args.results / "results.json"),
        "preparation_s": inference["preparation_s"],
        "search_s": inference["runtime_s"],
        "total_runtime_s": inference["preparation_s"] + inference["runtime_s"],
        "source_bindings": expected,
        "training_only_inference": True,
        "held_scoring_after_seal": True,
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
