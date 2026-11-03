#!/usr/bin/env python3
"""Export corrected native receipts with the explicit server-support profile."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from export_public_contract import (
    GATE,
    HEADER,
    canonical_digest,
    graph_row,
    load_native_inventory,
    load_public_event_authority,
    load_sources,
    prepare_output_dir,
    projection_record,
    sha256,
    validate_source_inventory,
)


def main() -> None:
    here = Path(__file__).resolve().parent
    root = here.parents[3]
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-output", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-visits", type=int, required=True)
    parser.add_argument("--projector", type=Path, required=True)
    parser.add_argument("--tracking", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--bulk-root", default="/srv/bulk/leo")
    parser.add_argument("--session", default="scan-fw-3cfdaa6d75762cad")
    parser.add_argument(
        "--source-authority",
        type=Path,
        default=root
        / "reports/2026_09_30_native_adaptive_deployment/tracking/projection-inputs.jsonl",
    )
    args = parser.parse_args()
    started = time.monotonic()
    prepare_output_dir(args.output_dir)

    profile = json.loads(args.profile.read_text())
    if profile.get("schema") != "org.leo.support-derivation-profile/v1":
        raise ValueError("unsupported support profile")
    sources = load_sources(args.source_authority)
    recording_manifest, source_globals, public_events = load_public_event_authority(
        args.bulk_root, args.session, args.expected_visits
    )
    validate_source_inventory(sources, args.expected_visits, source_globals)
    if recording_manifest != next(iter(sources.values()))["input_digest"]:
        raise ValueError("public store manifest differs from source authority")
    records, provenance = load_native_inventory(
        args.replay_output, args.expected_visits, sources, public_events
    )
    replay_summary_path = args.replay_output / "summary.json"
    replay_summary = json.loads(replay_summary_path.read_text())
    if (
        replay_summary["status"] != "pass"
        or replay_summary["visits"] != args.expected_visits
        or replay_summary["task_digest"] != provenance["task_digest"]
    ):
        raise ValueError("detector replay aggregate does not bind visit receipts")

    source_inventory = [sources[key] for key in sorted(sources)]
    detector_dependencies = replay_summary["dependencies"]
    algorithm = {
        "schema": "org.leo.corrected-native-public-export-algorithm/v1",
        "mode": "deployed-server-interval-fractional",
        "candidate_budget_per_receiver": 8,
        "recording_manifest_sha256": source_inventory[0]["input_digest"],
        "detector_sha256": detector_dependencies["detector_sha256"],
        "exact_template_sha256": detector_dependencies["exact_template_sha256"],
        "control_template_sha256": detector_dependencies["control_template_sha256"],
        "source_inventory_sha256": canonical_digest(source_inventory),
        "native_identity_sha256": provenance["native_identity_sha256"],
        "support_profile_name": profile["name"],
        "support_profile_manifest_digest": "sha256:" + sha256(args.profile),
        "profiled_projector_sha256": sha256(args.projector),
        "tracking_sha256": sha256(args.tracking),
    }
    analysis_digest = canonical_digest(algorithm)
    projection_lines = [
        projection_record(source, analysis_digest, candidate) for source, candidate in records
    ]
    projection_input_path = args.output_dir / "projection-inputs.tsv"
    projection_input_path.write_text("\n".join(projection_lines) + "\n")
    projected = subprocess.run(
        [str(args.projector)],
        input="\n".join(projection_lines) + "\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=300,
    )
    lines = projected.stdout.splitlines()
    if len(lines) != len(records):
        raise ValueError("profiled projector candidate accounting incomplete")

    observations: list[str] = []
    graph: list[str] = []
    for line, (source, candidate) in zip(lines, records, strict=True):
        available = candidate["fractional_status"] == "complete" and candidate["margin"] >= GATE
        if (line != "unavailable") != available:
            raise ValueError("profiled projector availability differs")
        if not available:
            continue
        fields = line.split("\t")
        if len(fields) != 9 or float(fields[5]) != candidate["tracking_cfo_hz"]:
            raise ValueError("profiled projector row differs")
        observations.append(
            "\t".join(
                fields[:2]
                + [
                    str(source["receiver"]),
                    str(source["channel"]),
                    "upper" if source["upper_edge"] else "lower",
                    str(source["actual_rf_hz"]),
                ]
                + fields[2:6]
                + [
                    str(candidate["exact_score"]),
                    str(candidate["control_score"]),
                    str(candidate["margin"]),
                ]
            )
        )
        graph.append(graph_row(fields))

    candidates_path = args.output_dir / "candidates.tsv"
    candidates_path.write_text(HEADER + "\n" + "\n".join(observations) + "\n")
    graph_path = args.output_dir / "graph-candidates.tsv"
    graph_path.write_text(
        f"META\t{args.session}\t{source_inventory[0]['input_digest']}\t"
        f"{source_inventory[0]['anchor_utc_ns']}\n"
        "candidate_id\tsupport_start_utc_ns\tsupport_center_utc_ns\t"
        "support_end_utc_ns\tmoment0\tmoment1\tmoment2\tmoment3\n" + "\n".join(graph) + "\n"
    )
    tracking = subprocess.run(
        [str(args.tracking), str(candidates_path)],
        text=True,
        capture_output=True,
        check=True,
        timeout=300,
    )
    (args.output_dir / "tracks.tsv").write_text(tracking.stdout)
    summary = next(
        line for line in tracking.stdout.splitlines() if line.startswith("SUMMARY\t")
    ).split("\t")
    report = {
        "schema": "org.leo.corrected-native-server-support-export/v1",
        "status": "pass",
        "visits": args.expected_visits,
        "native_candidates": len(records),
        "projected_observations": len(observations),
        "native_tracks": int(summary[3]),
        "analysis_digest": analysis_digest,
        "algorithm": algorithm,
        "detector_task_digest": provenance["task_digest"],
        "replay_summary_sha256": sha256(replay_summary_path),
        "projection_input_sha256": sha256(projection_input_path),
        "persisted_or_current_server_candidate_values_used_in_projection_or_identity": False,
        "reference_analysis_digest_used": False,
        "reference_support_moments_used": False,
        "timing_s": {"wall": time.monotonic() - started},
    }
    (args.output_dir / "algorithm.json").write_text(
        json.dumps(algorithm, indent=2, sort_keys=True) + "\n"
    )
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    (args.output_dir / "status.json").write_text(
        json.dumps({"status": "pass", "success_products_valid": True}) + "\n"
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
