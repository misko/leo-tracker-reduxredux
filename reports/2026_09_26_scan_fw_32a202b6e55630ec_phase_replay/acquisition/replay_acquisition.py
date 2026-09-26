#!/usr/bin/env python3
"""Audit and export the scan's persisted corrected GLRT acquisition census.

The persisted product is admitted only with an explicit producer revision and
content verification.  Frequency columns keep mixer, residual, and
pilot-relative/display coordinates separate.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import zstandard

from leo.analysis.starlink.pilot_search_geometry import canonicalize_pilot_cfo
from leo.contracts.digests import canonical_json_bytes, sha256_digest

SESSION_ID = "scan-fw-32a202b6e55630ec"
INPUT_MANIFEST_SHA256 = "sha256:b381f62da5b5490e43790b69e2947919ad9fee6441b642ac04e7af1be487993a"
ANALYSIS_BINDING_SHA256 = "sha256:5808b8a9d1729e606dbee610f9af5cbd93c87caa8579b7672e4f6c7e404a2336"
PRODUCER_REVISION = "2c30eaf50064623a666e1c078c56a02cb3223a70"
PINNED_REPLAY_REVISION = "e1a24b200d4bb68d4f38484dc591e9b9616a2e70"
AUTHORITATIVE_SELECTION_SHA256 = (
    "sha256:b73c0d5322a6a70c6ee851ee80ad99ef62ca13b190ae4bdeb35ce95ce2030115"
)


def _load_envelope(path: Path) -> tuple[dict[str, Any], str]:
    payload = path.read_bytes()
    if path.suffix == ".zst":
        payload = zstandard.ZstdDecompressor().decompress(payload)
    envelope = json.loads(payload)
    document = envelope["document"]
    observed = sha256_digest(canonical_json_bytes(document))
    if envelope["sha256"] != observed:
        raise ValueError(f"content digest mismatch: {path}")
    return document, observed


def _binding_directory(root: Path) -> Path:
    return (
        root
        / "scanner-adaptive-analysis"
        / SESSION_ID
        / ANALYSIS_BINDING_SHA256.removeprefix("sha256:")
    )


def export_inventory(root: Path, output: Path) -> None:
    base = _binding_directory(root)
    binding, binding_digest = _load_envelope(base / "binding.v8.json")
    if binding_digest != ANALYSIS_BINDING_SHA256:
        raise ValueError("analysis directory name differs from binding content digest")
    if binding["input_manifest_sha256"] != INPUT_MANIFEST_SHA256:
        raise ValueError("persisted analysis differs from pinned input manifest")
    config = binding["configuration"]
    if (config["sample_rate_hz"], config["probe_ms"], config["probe_stride_ms"]) != (
        10_000_000,
        20,
        120,
    ):
        raise ValueError("persisted census is not the pinned native-10 sparse schedule")

    events = binding["receipt"]["events"]
    origin = int(binding["receipt"]["terminal"]["first_counter"])
    end = int(binding["receipt"]["terminal"]["final_counter"])
    span = end - origin
    output.mkdir(parents=True, exist_ok=True)
    candidate_path = output / "candidate-inventory.csv"
    visit_path = output / "visit-inventory.csv"
    candidate_fields = (
        "visit_index",
        "target_index",
        "channel",
        "edge",
        "receiver_id",
        "probe_start_sample",
        "candidate_rank",
        "integer_epoch_sample",
        "fractional_epoch_offset_samples",
        "acquired_absolute_baseband_cfo_hz",
        "glrt_residual_cfo_hz",
        "tracking_absolute_baseband_cfo_hz",
        "pilot_nominal_baseband_hz",
        "pilot_relative_raw_cfo_hz",
        "pilot_relative_canonical_display_cfo_hz",
        "pilot_alias_lift",
        "fractional_exact_score",
        "fractional_control_score",
        "fractional_margin",
        "passed_0p025_comparison_gate",
        "integer_device_sample_counter",
    )
    visit_fields = (
        "visit_index",
        "target_index",
        "channel",
        "edge",
        "valid_start_counter",
        "time_block",
        "rx0_best_margin",
        "rx1_best_margin",
        "rx0_passed",
        "rx1_passed",
        "both_passed",
        "candidate_count",
        "visit_artifact_sha256",
    )
    counts: Counter[str] = Counter()
    with (
        candidate_path.open("w", newline="") as candidate_file,
        visit_path.open("w", newline="") as visit_file,
    ):
        candidate_writer = csv.DictWriter(candidate_file, fieldnames=candidate_fields)
        visit_writer = csv.DictWriter(visit_file, fieldnames=visit_fields)
        candidate_writer.writeheader()
        visit_writer.writeheader()
        for visit_index, event in enumerate(events):
            document, artifact_digest = _load_envelope(
                base / f"visit-{visit_index:06d}.v8.json.zst"
            )
            if document["visit_index"] != visit_index:
                raise ValueError(f"visit ordinal mismatch at {visit_index}")
            probe_by_rx = {probe["receiver_id"]: probe for probe in document["probes"]}
            best: dict[int, float] = {}
            total_candidates = 0
            for receiver_id, probe in sorted(probe_by_rx.items()):
                total_candidates += len(probe["candidates"])
                if probe["candidates"]:
                    best[receiver_id] = max(
                        float(row["fractional_margin"]) for row in probe["candidates"]
                    )
                for row in probe["candidates"]:
                    tracking = float(row["fractional_tracking_cfo_hz"])
                    coordinate = canonicalize_pilot_cfo(
                        tracking,
                        starlink_channel=event["target"]["channel"],
                        edge=event["target"]["edge"],
                        tuned_center_frequency_hz=event["actual_lo_frequency_hz"],
                        lnb_lo_hz=binding["receipt"]["plan"]["geometry"]["lnb_lo_hz"],
                    )
                    candidate_writer.writerow(
                        {
                            "visit_index": visit_index,
                            "target_index": event["target_index"],
                            "channel": event["target"]["channel"],
                            "edge": event["target"]["edge"],
                            "receiver_id": receiver_id,
                            "probe_start_sample": probe["probe_start_ms"] * 10_000,
                            "candidate_rank": row["candidate_rank"],
                            "integer_epoch_sample": row["integer_epoch_sample"],
                            "fractional_epoch_offset_samples": row[
                                "fractional_epoch_offset_samples"
                            ],
                            "acquired_absolute_baseband_cfo_hz": row["acquired_cfo_hz"],
                            "glrt_residual_cfo_hz": row["fractional_residual_cfo_hz"],
                            "tracking_absolute_baseband_cfo_hz": tracking,
                            "pilot_nominal_baseband_hz": coordinate.nominal_pilot_baseband_hz,
                            "pilot_relative_raw_cfo_hz": coordinate.raw_residual_cfo_hz,
                            "pilot_relative_canonical_display_cfo_hz": (
                                coordinate.canonical_residual_cfo_hz
                            ),
                            "pilot_alias_lift": coordinate.alias_lift,
                            "fractional_exact_score": row["fractional_exact_score"],
                            "fractional_control_score": row["fractional_control_score"],
                            "fractional_margin": row["fractional_margin"],
                            "passed_0p025_comparison_gate": row["passed_fractional_margin_gate"],
                            "integer_device_sample_counter": row["integer_device_sample_counter"],
                        }
                    )
            passed = {receiver: best.get(receiver, float("-inf")) >= 0.025 for receiver in (0, 1)}
            block = min(7, 8 * (int(event["valid_start_counter"]) - origin) // span)
            visit_writer.writerow(
                {
                    "visit_index": visit_index,
                    "target_index": event["target_index"],
                    "channel": event["target"]["channel"],
                    "edge": event["target"]["edge"],
                    "valid_start_counter": event["valid_start_counter"],
                    "time_block": block,
                    "rx0_best_margin": best.get(0, ""),
                    "rx1_best_margin": best.get(1, ""),
                    "rx0_passed": passed[0],
                    "rx1_passed": passed[1],
                    "both_passed": passed[0] and passed[1],
                    "candidate_count": total_candidates,
                    "visit_artifact_sha256": artifact_digest,
                }
            )
            counts["visits"] += 1
            counts["candidates"] += total_candidates
            counts["rx0_passed"] += passed[0]
            counts["rx1_passed"] += passed[1]
            counts["both_passed"] += passed[0] and passed[1]
            counts["neither_passed"] += not passed[0] and not passed[1]

    audit = {
        "session_id": SESSION_ID,
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "analysis_binding_sha256": binding_digest,
        "producer_revision": PRODUCER_REVISION,
        "pinned_replay_revision": PINNED_REPLAY_REVISION,
        "producer_resolution": {
            "systemd_unit": "leo-adaptive-analysis-worker@.service",
            "immutable_runtime_path": f"/opt/leo-tracker/releases/{PRODUCER_REVISION}",
            "release_source_tree": "2327b562456f09d3227c1acbbd53fb5605111a33",
            "deployment_evidence": {
                "unit_execstart_inspected_utc": "2026-09-26",
                "worker_process_start_utc": "2026-09-26T06:22:42Z..2026-09-26T06:22:49Z",
                "session_import_journal_utc": "2026-09-26T12:30:18Z",
                "session_queue_journal_utc": "2026-09-26T12:31:01Z",
                "binding_file_birth_utc": "2026-09-26T12:31:03.972899310Z",
                "evidence_commands": [
                    "systemctl cat leo-adaptive-analysis-worker@.service",
                    "systemctl show leo-adaptive-analysis-worker@0..16.service -p ExecStart",
                    "journalctl --since 2026-09-26T12:30:00Z",
                    "stat binding.v8.json",
                    f"cat /opt/leo-tracker/releases/{PRODUCER_REVISION}/.leo-release-source.json",
                ],
            },
            "geometry_fix_is_ancestor": True,
            "current_numerical_source_differs": False,
        },
        "persisted_schedule": {
            "sample_rate_hz": 10_000_000,
            "probe_ms": 20,
            "probe_stride_ms": 120,
        },
        "counts": dict(counts),
        "authoritative_selection_sha256": AUTHORITATIVE_SELECTION_SHA256,
        "scientific_scope": (
            "corrected sparse first-20-ms acquisition census; "
            "gate 0.025 is comparison-only"
        ),
    }
    (output / "glrt-audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    export_track_inventory(root, output)


def export_track_inventory(root: Path, output: Path) -> None:
    path = root / "scanner-shared-tracking-v14" / SESSION_ID / "manifest.json"
    document, digest = _load_envelope(path)
    if document["input_manifest_sha256"] != INPUT_MANIFEST_SHA256:
        raise ValueError("track authority differs from pinned capture")
    expected_analysis = "sha256:615a9fa91be411d7cef1c4faf056d7947607a24c787d5d858b3dff96733ed962"
    if document["analysis_manifest_sha256"] != expected_analysis:
        raise ValueError("track authority differs from pinned GLRT metrics")
    inventory = {
        "schema": "scan-phase-replay-track-inventory/v1",
        "source_manifest_sha256": digest,
        "analysis_manifest_sha256": expected_analysis,
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "candidate_only": document["candidate_only"],
        "identity_claimed": document["identity_claimed"],
        "trajectory_time_basis": document["trajectory_time_basis"],
        "trajectory_state": document["trajectory_state"],
        "tracklets": document["tracklets"],
        "track_reviews": document["track_reviews"],
        "coordinate_policy": (
            "Original track CFO fields are preserved verbatim. Canonical display coordinates "
            "in candidate-inventory.csv must not replace them for coherent mixing."
        ),
    }
    (output / "track-inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    export_inventory(args.bulk_root, args.output)


if __name__ == "__main__":
    main()
