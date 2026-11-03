#!/usr/bin/env python3
"""Export corrected native receipts through the public C3/C4 contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import time
from pathlib import Path

GATE = 0.025
HEADER = (
    "candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\t"
    "support_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\t"
    "measured_cfo_hz\texact_score\tcontrol_score\tmargin"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def prepare_output_dir(path: Path) -> None:
    """Remove prior success products before an attempted non-transactional export."""

    path.mkdir(parents=True, exist_ok=True)
    for name in (
        "algorithm.json",
        "candidates.tsv",
        "graph-candidates.tsv",
        "tracks.tsv",
        "report.json",
    ):
        (path / name).unlink(missing_ok=True)
    (path / "status.json").write_text(
        json.dumps({"status": "running", "success_products_valid": False}) + "\n"
    )


def load_sources(path: Path) -> dict[tuple[int, int, int], dict]:
    """Read only the public source object; candidate answers are never retained."""

    sources = {}
    for line in path.read_text().splitlines():
        source = json.loads(line)["source"]
        key = source["visit"], source["receiver"], source["probe_index"]
        previous = sources.setdefault(key, source)
        if previous != source:
            raise ValueError(f"conflicting source authority: {key}")
    return sources


def validate_source_inventory(
    sources: dict[tuple[int, int, int], dict],
    expected_visits: int,
    expected_globals: dict | None = None,
) -> None:
    expected = {(visit, receiver, 0) for visit in range(expected_visits) for receiver in (0, 1)}
    if set(sources) != expected:
        raise ValueError("public source authority coverage differs")
    for key, source in sources.items():
        if key != (source["visit"], source["receiver"], source["probe_index"]):
            raise ValueError(f"public source identity differs at {key}")
    constant_fields = (
        "rate",
        "anchor_counter",
        "anchor_utc_ns",
        "generation",
        "utc_bracket_width_ns",
        "input_digest",
        "continuity_qualified",
    )
    for field in constant_fields:
        if len({source[field] for source in sources.values()}) != 1:
            raise ValueError(f"public source {field} authority is inconsistent")
        if (
            expected_globals is not None
            and next(iter(sources.values()))[field] != expected_globals[field]
        ):
            raise ValueError(f"public source {field} differs from recording manifest")
    for visit in range(expected_visits):
        left, right = sources[visit, 0, 0], sources[visit, 1, 0]
        if {key: value for key, value in left.items() if key != "receiver"} != {
            key: value for key, value in right.items() if key != "receiver"
        }:
            raise ValueError(f"receiver source authority differs at visit {visit}")


def load_public_event_authority(
    bulk_root: str, session_id: str, expected_visits: int
) -> tuple[str, dict, dict[int, dict]]:
    """Re-read the public store and derive geometry without candidate answers."""

    from leo.contracts.starlink_frequency import starlink_edge_rf_center_frequency_hz
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    from leo.analysis.starlink.templates import edge_frequencies_hz

    store = AdaptiveHopIqStore(bulk_root, read_only=True)
    session = store.inspect(session_id)
    geometry = session.manifest.receipt.plan.geometry
    result = {}
    with store.reader(session_id, expected=session) as reader:
        for visit_index in range(expected_visits):
            visit, _values = reader.read_visit_ci16(visit_index)
            event = visit.event
            if event.visit_index != visit_index:
                raise ValueError("public store visit ordering changed")
            offsets = edge_frequencies_hz(event.target.edge)
            pilot_if_hz = (
                starlink_edge_rf_center_frequency_hz(event.target.channel, event.target.edge)
                - geometry.lnb_lo_hz
            )
            center_hz = float(pilot_if_hz - event.actual_lo_frequency_hz)
            half_usable_hz = min(geometry.sample_rate_hz, geometry.bandwidth_hz) / 2.0
            observable_hz = min(
                center_hz + float(offsets.min()) + half_usable_hz,
                half_usable_hz - center_hz - float(offsets.max()),
            )
            if not math.isfinite(observable_hz) or observable_hz <= 0:
                raise ValueError("public event geometry is not observable")
            half_width_hz = min(800_000.0, observable_hz)
            result[visit_index] = {
                "recording_event_sha256": canonical_digest(
                    event.model_dump(mode="json")
                ).removeprefix("sha256:"),
                "valid_start_counter": event.valid_start_counter,
                "channel": event.target.channel,
                "edge": event.target.edge.value,
                "actual_rf_hz": event.target.rf_center_hz,
                "actual_lo_frequency_hz": event.actual_lo_frequency_hz,
                "receiver_center_hz": [center_hz, center_hz],
                "residual_cfo_min_hz": -half_width_hz,
                "residual_cfo_max_hz": half_width_hz,
            }
    timing = session.manifest.timing
    source_globals = {
        "rate": geometry.sample_rate_hz,
        "anchor_counter": timing.session_start_device_sample_counter,
        "anchor_utc_ns": timing.first_sample_estimate_utc_ns,
        "generation": session.manifest.receipt.stream_generation,
        "utc_bracket_width_ns": timing.first_sample_bracket_width_ns,
        "input_digest": session.manifest_sha256,
        "continuity_qualified": timing.qualified,
    }
    return session.manifest_sha256, source_globals, result


def projection_record(source: dict, analysis_digest: str, candidate: dict) -> str:
    complete = candidate["fractional_status"] == "complete"
    values = [
        source[key]
        for key in (
            "rate",
            "anchor_counter",
            "anchor_utc_ns",
            "generation",
            "visit",
            "window_counter",
            "probe_index",
            "receiver",
            "channel",
            "upper_edge",
            "actual_rf_hz",
            "utc_bracket_width_ns",
            "input_digest",
        )
    ]
    values.extend(
        (
            analysis_digest,
            source["continuity_qualified"],
            candidate["rank"],
            candidate["integer_epoch"],
            candidate["fractional_offset"] if complete else 0,
            candidate["tracking_cfo_hz"] if complete else 0,
            candidate["exact_score"] if complete else 0,
            candidate["control_score"] if complete else 0,
            candidate["margin"] if complete else 0,
            complete,
        )
    )
    return "\t".join(str(int(value)) if isinstance(value, bool) else str(value) for value in values)


def graph_row(projected_fields: list[str]) -> str:
    """Preserve projector-owned moment lexemes exactly for partition identity."""

    return "\t".join(
        [
            projected_fields[0],
            *projected_fields[2:5],
            "1.0",
            "0.0",
            projected_fields[7],
            projected_fields[8],
        ]
    )


def load_native_inventory(
    replay_output: Path,
    expected_visits: int,
    sources: dict[tuple[int, int, int], dict],
    public_events: dict[int, dict],
) -> tuple[list[tuple[dict, dict]], dict]:
    expected = set(range(expected_visits))
    paths = sorted((replay_output / "visits").glob("visit-*.json"))
    visits, records, bindings = set(), [], []
    task_digests = set()
    for path in paths:
        receipt = json.loads(path.read_text())
        visit = receipt["visit"]
        if receipt["status"] != "pass" or visit in visits:
            raise ValueError(f"invalid or duplicate visit receipt: {visit}")
        visits.add(visit)
        task_digests.add(receipt["task_digest"])
        authority = receipt["source_authority"]
        event = public_events[visit]
        if authority["source_store"]["read_only"] is not True:
            raise ValueError("detector receipt does not bind a read-only source")
        if authority["recording_manifest_sha256"] != sources[(visit, 0, 0)]["input_digest"]:
            raise ValueError(f"recording authority differs at visit {visit}")
        if receipt["channel"] != sources[(visit, 0, 0)]["channel"]:
            raise ValueError(f"channel authority differs at visit {visit}")
        if (receipt["edge"] == "upper") != sources[(visit, 0, 0)]["upper_edge"]:
            raise ValueError(f"edge authority differs at visit {visit}")
        for key in (
            "recording_event_sha256",
            "actual_lo_frequency_hz",
            "receiver_center_hz",
            "residual_cfo_min_hz",
            "residual_cfo_max_hz",
        ):
            if authority[key] != event[key]:
                raise ValueError(f"public event {key} differs at visit {visit}")
        for receiver in (0, 1):
            source = sources[(visit, receiver, 0)]
            if (
                source["window_counter"] != event["valid_start_counter"]
                or source["channel"] != event["channel"]
                or source["upper_edge"] != (event["edge"] == "upper")
                or source["actual_rf_hz"] != event["actual_rf_hz"]
            ):
                raise ValueError(f"public timing/RF authority differs at {(visit, receiver)}")
        native = receipt["native"]
        if set(native) != {"0", "1"}:
            raise ValueError(f"receiver inventory differs at visit {visit}")
        for receiver in (0, 1):
            source = sources[(visit, receiver, 0)]
            candidates = native[str(receiver)]
            if len(candidates) != 8:
                raise ValueError(f"candidate inventory differs at {(visit, receiver)}")
            for rank, candidate in enumerate(candidates):
                if candidate["rank"] != rank:
                    raise ValueError(f"candidate rank differs at {(visit, receiver, rank)}")
                records.append((source, candidate))
        # This provenance hash may bind comparison bytes, but it never enters
        # analysis_digest or any projected candidate identity.
        bindings.append({"visit": visit, "receipt_sha256": sha256(path)})
    if visits != expected:
        raise ValueError(
            f"visit coverage differs: missing={len(expected - visits)} "
            f"extra={len(visits - expected)}"
        )
    if len(task_digests) != 1:
        raise ValueError("detector receipts do not share one task digest")
    native_identity = [{"source": source, "candidate": candidate} for source, candidate in records]
    return records, {
        "task_digest": next(iter(task_digests)),
        "receipt_bindings": bindings,
        "native_identity_sha256": canonical_digest(native_identity),
    }


def main() -> None:
    here = Path(__file__).resolve().parent
    root = here.parents[3]
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-output", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-visits", type=int, required=True)
    parser.add_argument("--projector", type=Path, required=True)
    parser.add_argument("--tracking", type=Path, required=True)
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
        raise ValueError("detector replay aggregate does not bind the visit receipts")
    detector_dependencies = replay_summary["dependencies"]
    source_inventory = [sources[key] for key in sorted(sources)]
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
        "projector_sha256": sha256(args.projector),
        "tracking_sha256": sha256(args.tracking),
    }
    analysis_digest = canonical_digest(algorithm)
    projection_input = "\n".join(
        projection_record(source, analysis_digest, candidate) for source, candidate in records
    )
    projected = subprocess.run(
        [str(args.projector)],
        input=projection_input + ("\n" if projection_input else ""),
        text=True,
        capture_output=True,
        check=True,
        timeout=180,
    )
    lines = projected.stdout.splitlines()
    if len(lines) != len(records):
        raise ValueError("projector candidate accounting incomplete")
    observations, graph_rows = [], []
    for line, (source, candidate) in zip(lines, records, strict=True):
        available = candidate["fractional_status"] == "complete" and candidate["margin"] >= GATE
        if (line != "unavailable") != available:
            raise ValueError("projector availability differs")
        if not available:
            continue
        fields = line.split("\t")
        if float(fields[5]) != candidate["tracking_cfo_hz"]:
            raise ValueError("projector CFO differs")
        window_start = source["anchor_utc_ns"] + round(
            (source["window_counter"] - source["anchor_counter"]) * 1e9 / source["rate"]
        )
        window_end = source["anchor_utc_ns"] + round(
            (source["window_counter"] - source["anchor_counter"] + source["rate"] // 50)
            * 1e9
            / source["rate"]
        )
        support_start, support_center, support_end = map(int, fields[2:5])
        if not (window_start <= support_start <= support_center < support_end <= window_end):
            raise ValueError("projected support escaped the authoritative IQ window")
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
        graph_rows.append(graph_row(fields))
    candidates_path = args.output_dir / "candidates.tsv"
    candidates_path.write_text(
        HEADER + "\n" + "\n".join(observations) + ("\n" if observations else "")
    )
    graph_path = args.output_dir / "graph-candidates.tsv"
    anchor_utc_ns = min(source["anchor_utc_ns"] for source in source_inventory)
    graph_path.write_text(
        f"META\t{args.session}\t{source_inventory[0]['input_digest']}\t"
        f"{anchor_utc_ns}\n"
        "candidate_id\tsupport_start_utc_ns\tsupport_center_utc_ns\t"
        "support_end_utc_ns\tmoment0\tmoment1\tmoment2\tmoment3\n"
        + "\n".join(graph_rows)
        + ("\n" if graph_rows else "")
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
        "schema": "org.leo.corrected-native-public-export/v1",
        "status": "pass",
        "visits": args.expected_visits,
        "native_candidates": len(records),
        "projected_observations": len(observations),
        "native_tracks": int(summary[3]),
        "analysis_digest": analysis_digest,
        "algorithm": algorithm,
        "detector_task_digest": provenance["task_digest"],
        "receipt_bindings": provenance["receipt_bindings"],
        "replay_summary_sha256": sha256(replay_summary_path),
        "source_authority_path": str(args.source_authority),
        "source_authority_file_sha256_evidence_only": sha256(args.source_authority),
        "persisted_or_current_server_candidate_values_used_in_projection_or_identity": False,
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
