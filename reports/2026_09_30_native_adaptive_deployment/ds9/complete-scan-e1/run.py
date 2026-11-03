#!/usr/bin/env python3
"""Bounded, read-only DS9 complete-recording native E1/C3 replay."""

import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

HEADER = (
    "candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\t"
    "support_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\t"
    "measured_cfo_hz\texact_score\tcontrol_score\tmargin"
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def load_sources(path):
    sources = {}
    for line in Path(path).read_text().splitlines():
        source = json.loads(line)["source"]
        key = (source["visit"], source["receiver"], source["probe_index"])
        previous = sources.setdefault(key, source)
        if previous != source:
            raise ValueError(f"conflicting source authority: {key}")
    return sources


def project_record(source, analysis_digest, rank, candidate):
    fractional = candidate["fractional_epoch"]
    complete = fractional["status"] == "complete"
    values = [
        source[k]
        for k in (
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
    values += [analysis_digest, source["continuity_qualified"], rank, candidate["epoch"]]
    values += [
        fractional[k] if complete else 0
        for k in ("offset_samples", "tracking_cfo_hz", "exact_score", "control_score", "margin")
    ]
    values.append(complete)
    return "\t".join(str(int(v)) if isinstance(v, bool) else str(v) for v in values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--detector", type=Path, required=True)
    parser.add_argument("--projector", type=Path, required=True)
    parser.add_argument("--tracking", type=Path, required=True)
    parser.add_argument("--source-authority", type=Path, required=True)
    parser.add_argument("--exact", type=Path, required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--session", default="scan-fw-3cfdaa6d75762cad")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--deadline-seconds", type=float, default=1200.0)
    args = parser.parse_args()
    started = time.monotonic()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sources = load_sources(args.source_authority)

    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    session = store.inspect(args.session)
    manifest = session.manifest
    visits = manifest.receipt.visits
    geometry = manifest.receipt.plan.geometry
    expected_keys = {(i, rx, 0) for i in range(len(visits)) for rx in geometry.receiver_ids}
    if set(sources) != expected_keys:
        missing, extra = expected_keys - set(sources), set(sources) - expected_keys
        raise ValueError(
            f"source authority coverage differs: missing={len(missing)} extra={len(extra)}"
        )
    if session.manifest_sha256 != next(iter(sources.values()))["input_digest"]:
        raise ValueError("recording digest differs from source authority")
    if geometry.sample_rate_hz != 7_500_000 or geometry.valid_visit_ms != 120:
        raise ValueError("unexpected recording geometry")

    detector_hash = sha256(args.detector)
    exact_hash, control_hash = sha256(args.exact), sha256(args.control)
    calls, raw_bindings = [], []
    native_path = args.output_dir / "native.jsonl"
    native_stream = native_path.open("w")
    read_seconds = detector_seconds = 0.0
    with store.reader(args.session, expected=session) as reader:
        for first in range(0, len(visits), args.batch_size):
            last = min(first + args.batch_size, len(visits))
            with tempfile.TemporaryDirectory(prefix="leo-ds9-complete-") as temporary:
                temporary = Path(temporary)
                schedule = []
                for sequence, visit_index in enumerate(range(first, last)):
                    before = time.monotonic()
                    visit, values = reader.read_visit_ci16(visit_index)
                    read_seconds += time.monotonic() - before
                    event = visit.event
                    if (
                        event.visit_index != visit_index
                        or event.valid_start_counter
                        != sources[(visit_index, 0, 0)]["window_counter"]
                    ):
                        raise ValueError(f"visit timing authority differs at {visit_index}")
                    for receiver in geometry.receiver_ids:
                        source = sources[(visit_index, receiver, 0)]
                        if (
                            source["window_counter"] != event.valid_start_counter
                            or source["channel"] != event.target.channel
                            or source["upper_edge"] != (event.target.edge.value == "upper")
                            or source["actual_rf_hz"] != event.target.rf_center_hz
                        ):
                            raise ValueError(
                                f"RF/timing authority differs at {(visit_index, receiver)}"
                            )
                    raw = temporary / f"visit-{visit_index:04d}.ci16"
                    raw.write_bytes(memoryview(values).cast("B"))
                    raw_hash = sha256(raw)
                    raw_bindings.append({"visit": visit_index, "sha256": raw_hash})
                    metadata = json.dumps(
                        {
                            "dataset_id": "DS9",
                            "session_id": args.session,
                            "visit_index": visit_index,
                            "raw_sha256": raw_hash,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    schedule.append(
                        "\t".join(
                            map(
                                str,
                                (
                                    sequence,
                                    geometry.sample_rate_hz,
                                    120,
                                    120,
                                    args.exact,
                                    args.control,
                                    raw,
                                    metadata,
                                ),
                            )
                        )
                    )
                schedule_path = temporary / "replay.tsv"
                schedule_path.write_text("\n".join(schedule) + "\n")
                before = time.monotonic()
                replay = subprocess.run(
                    [str(args.detector), "--manifest", str(schedule_path), "--fractional-epoch"],
                    text=True,
                    capture_output=True,
                    check=True,
                    timeout=180,
                )
                detector_seconds += time.monotonic() - before
                for line in replay.stdout.splitlines():
                    parsed = json.loads(line)
                    result = parsed.get("result", {})
                    if result.get("kind") == "call":
                        metadata = json.loads(result["metadata"])
                        if metadata["visit_index"] != first + result["sequence"]:
                            raise ValueError("detector replay sequence changed")
                        calls.append(result)
                    native_stream.write(
                        json.dumps({"batch_first_visit": first, **parsed}, separators=(",", ":"))
                        + "\n"
                    )
            completed = last
            elapsed = time.monotonic() - started
            if completed >= 64:
                projected = elapsed * len(visits) / completed
                print(
                    json.dumps(
                        {"visits": completed, "elapsed_s": elapsed, "projected_s": projected}
                    ),
                    flush=True,
                )
                if projected > args.deadline_seconds or elapsed > args.deadline_seconds:
                    raise TimeoutError(f"bounded replay projected {projected:.1f}s")
    native_stream.close()
    if len(calls) != len(visits):
        raise ValueError("detector call accounting incomplete")

    algorithm = {
        "detector_sha256": detector_hash,
        "mode": "ordinary-with-fractional-epoch",
        "exact_sha256": exact_hash,
        "control_sha256": control_hash,
        "recording_manifest_sha256": session.manifest_sha256,
        "raw_visits": raw_bindings,
    }
    analysis_digest = canonical_digest(algorithm)
    records, checks = [], []
    fractional_complete = 0
    for call in calls:
        metadata = json.loads(call["metadata"])
        visit_index = metadata["visit_index"]
        for row in call["rows"]:
            source = sources[(visit_index, row["receiver_id"], row["probe_index"])]
            for rank, candidate in enumerate(row["candidates"]):
                records.append(project_record(source, analysis_digest, rank, candidate))
                checks.append((source, rank, candidate["fractional_epoch"]))
                fractional_complete += candidate["fractional_epoch"]["status"] == "complete"
    projected = subprocess.run(
        [str(args.projector)],
        input=("\n".join(records) + "\n") if records else "",
        text=True,
        capture_output=True,
        check=True,
        timeout=180,
    )
    lines = projected.stdout.splitlines()
    if len(lines) != len(checks):
        raise ValueError("projector candidate accounting incomplete")
    observations, graph_rows = [], []
    for line, (source, _rank, fractional) in zip(lines, checks, strict=True):
        available = fractional["status"] == "complete" and fractional["margin"] >= 0.025
        if (line != "unavailable") != available:
            raise ValueError("projector availability differs")
        if not available:
            continue
        fields = line.split("\t")
        if float(fields[5]) != fractional["tracking_cfo_hz"]:
            raise ValueError("projector CFO differs")
        start = source["anchor_utc_ns"] + round(
            (source["window_counter"] - source["anchor_counter"]) * 1e9 / source["rate"]
        )
        end = source["anchor_utc_ns"] + round(
            (source["window_counter"] - source["anchor_counter"] + source["rate"] // 50)
            * 1e9
            / source["rate"]
        )
        left, center, right = map(int, fields[2:5])
        if not start <= left <= center < right <= end:
            raise ValueError("projected support escaped IQ window")
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
                    str(fractional["exact_score"]),
                    str(fractional["control_score"]),
                    str(fractional["margin"]),
                ]
            )
        )
        graph_rows.append("\t".join([fields[0], *fields[2:5], "1.0", "0.0", fields[7], fields[8]]))

    candidates_path = args.output_dir / "candidates.tsv"
    candidates_path.write_text(
        HEADER + "\n" + "\n".join(observations) + ("\n" if observations else "")
    )
    graph_path = args.output_dir / "graph-candidates.tsv"
    anchor_utc_ns = min(source["anchor_utc_ns"] for source in sources.values())
    graph_path.write_text(
        f"META\t{args.session}\t{session.manifest_sha256}\t{anchor_utc_ns}\n"
        "candidate_id\tsupport_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\t"
        "moment0\tmoment1\tmoment2\tmoment3\n"
        + "\n".join(graph_rows)
        + ("\n" if graph_rows else "")
    )
    tracking_started = time.monotonic()
    tracking = subprocess.run(
        [str(args.tracking), str(candidates_path)],
        text=True,
        capture_output=True,
        check=True,
        timeout=180,
    )
    tracking_seconds = time.monotonic() - tracking_started
    tracks_path = args.output_dir / "tracks.tsv"
    tracks_path.write_text(tracking.stdout)
    summary = next(
        line for line in tracking.stdout.splitlines() if line.startswith("SUMMARY\t")
    ).split("\t")
    track_count = int(summary[3])
    wall = time.monotonic() - started
    report = {
        "schema": "org.leo.native-adaptive-complete-scan-e1/v1",
        "status": "pass",
        "complete_scan": True,
        "session_id": args.session,
        "visits": len(visits),
        "source_windows": len(sources),
        "source_authority_missing": 0,
        "compressed_bytes_verified": manifest.compressed_bytes,
        "uncompressed_bytes_verified": manifest.uncompressed_bytes,
        "manifest_sha256": session.manifest_sha256,
        "session_uncompressed_sha256": manifest.uncompressed_sha256,
        "detector_sha256": detector_hash,
        "projector_sha256": sha256(args.projector),
        "tracking_sha256": sha256(args.tracking),
        "analysis_digest": analysis_digest,
        "native_candidates": len(records),
        "fractional_complete": fractional_complete,
        "projected_observations": len(observations),
        "native_tracks": track_count,
        "timing_s": {
            "wall": wall,
            "read_decode_hash": read_seconds,
            "detector_processes": detector_seconds,
            "tracking": tracking_seconds,
        },
        "bounded_deadline_s": args.deadline_seconds,
        "server_parity_qualified": False,
        "location_status": "not_run",
        "limitations": [
            "Production native fractional detection is not server-parity qualified.",
            "C6 scoring and C7 search are explicit downstream commands over "
            "the emitted graph authority.",
        ],
    }
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (args.output_dir / "algorithm.json").write_text(json.dumps(algorithm, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
