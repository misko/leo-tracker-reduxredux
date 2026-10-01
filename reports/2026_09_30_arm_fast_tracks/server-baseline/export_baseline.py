#!/usr/bin/env python3
"""Project fresh full-scan detector outputs and run the maintained server tracker."""

from __future__ import annotations

import argparse
import dataclasses
import enum
import hashlib
import json
import math
import os
import time
from pathlib import Path
from types import SimpleNamespace

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopCfoCandidate,
    PersistentHopTrajectoryConfig,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.persistent_hop_trajectory import fractional_glrt64_support_geometry
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.digests import canonical_digest
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.contracts.states import StarlinkEdge
from leo.storage.adaptive_hop import AdaptiveHopIqStore


SESSION = "scan-fw-f363c7f29141d0b1"
MANIFEST = "sha256:b74c950fb172433dab804ddd14b46a3f4c6c1d2e85a09855b0bfdff5da78e015"
OBSERVATION_HEADER = (
    "candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\t"
    "support_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\t"
    "measured_cfo_hz\texact_score\tcontrol_score\tmargin"
)
MAP_HEADER = (
    "candidate_id\tsource_group_id\tvisit\treceiver_id\tprobe_index\t"
    "candidate_rank\tepoch_kind\tdetector_side"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_value(value):
    if hasattr(value, "model_dump"):
        return json_value(value.model_dump(mode="json"))
    if dataclasses.is_dataclass(value):
        return {field.name: json_value(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, tuple):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    return value


def write_json(path: Path, value) -> None:
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(json.dumps(json_value(value), indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.replace(temporary, path)


def digest_files(paths: list[Path]) -> str:
    return canonical_digest([(str(path), sha256(path)) for path in paths])


def load_server(server: Path, events, analysis_digest: str) -> tuple[TrackingProbe, ...]:
    receipts = sorted((server / "visits").glob("visit-*.json"))
    if len(receipts) != len(events):
        raise ValueError("server visit coverage differs from recording")
    probes: list[TrackingProbe] = []
    payload_start = 0
    for visit, (path, event) in enumerate(zip(receipts, events, strict=True)):
        document = json.loads(path.read_text())
        if (
            document["status"] != "pass"
            or document["visit"] != visit
            or document["source"]["event"] != event.model_dump(mode="json")
        ):
            raise ValueError(f"server source authority differs at visit {visit}")
        for receiver in (0, 1):
            candidates = []
            for row in document["candidates"][str(receiver)]:
                if row["fractional_status"] != "complete":
                    continue
                values = (
                    row["fractional_offset_samples"],
                    row["fractional_tracking_cfo_hz"],
                    row["fractional_exact_score"],
                    row["fractional_control_score"],
                    row["fractional_margin"],
                )
                if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
                    raise ValueError(f"nonfinite server candidate at {(visit, receiver, row['rank'])}")
                candidates.append(
                    TrackingCandidate(
                        candidate_rank=row["rank"],
                        integer_epoch_sample=row["epoch"],
                        fractional_epoch_offset_samples=row["fractional_offset_samples"],
                        fractional_tracking_cfo_hz=row["fractional_tracking_cfo_hz"],
                        fractional_exact_score=row["fractional_exact_score"],
                        fractional_control_score=row["fractional_control_score"],
                        fractional_margin=row["fractional_margin"],
                        passed_fractional_margin_gate=row["passed_fractional_margin_gate"],
                    )
                )
            probes.append(
                TrackingProbe(
                    visit_index=visit,
                    receiver_id=receiver,
                    probe_index=0,
                    probe_start_ms=0,
                    channel=event.target.channel,
                    edge=event.target.edge.value,
                    actual_rf_hz=float(event.target.rf_center_hz - event.actual_if_offset_hz),
                    valid_start_counter=event.valid_start_counter,
                    payload_start_sample=payload_start,
                    candidates=tuple(candidates),
                )
            )
        payload_start += event.valid_end_counter_exclusive - event.valid_start_counter
    return tuple(probes)


def server_projection(server: Path, published) -> tuple[tuple[PersistentHopCfoCandidate, ...], str]:
    summary = json.loads((server / "summary.json").read_text())
    if summary["status"] != "pass" or summary["visits"] != 2215:
        raise ValueError("fresh server detector summary is not complete")
    analysis_digest = canonical_digest(
        {
            "algorithm_version": "fresh-standard-server-full-scan-analysis-v1",
            "recording_manifest_sha256": MANIFEST,
            "server_task_digest": summary["task_digest"],
            "server_visits_jsonl_sha256": sha256(server / "server-visits.jsonl"),
            "server_harness_sha256": summary["dependencies"]["harness_sha256"],
        }
    )
    manifest, receipt = published.manifest, published.manifest.receipt
    probes = load_server(server, receipt.events, analysis_digest)
    source = TrackingInput(
        session_id=SESSION,
        capture_mode="adaptive",
        sample_rate_hz=receipt.plan.geometry.sample_rate_hz,
        radio_id=receipt.radio_id,
        stream_generation=(
            f"adaptive-iio-{receipt.stream_generation:016x}" if receipt.stream_generation else ""
        ),
        input_manifest_sha256=MANIFEST,
        analysis_manifest_sha256=analysis_digest,
        raw_recording_authority_digest=canonical_digest(
            {"capture": MANIFEST, "iq": manifest.uncompressed_sha256}
        ),
        timing=manifest.timing,
        qualified=receipt.terminal.state == "completed" and receipt.source_span_attested,
        probes=probes,
        probe_ms=20,
        capture_start_utc_ns=manifest.timing.first_sample_estimate_utc_ns,
        capture_end_utc_ns=(
            manifest.timing.first_sample_estimate_utc_ns
            + round(
                (receipt.terminal.final_counter - receipt.terminal.first_counter)
                * 1e9
                / receipt.plan.geometry.sample_rate_hz
            )
        ),
    )
    candidates = project_scanner_candidates(source)
    return candidates, analysis_digest


def load_arm(arm: Path, published) -> tuple[tuple[PersistentHopCfoCandidate, ...], str]:
    completion = json.loads((arm / "completion.json").read_text())
    inventory = json.loads((arm / "inventory.json").read_text())
    if completion["status"] != "PASS" or completion["visits"] != 2215 or len(inventory) != 2215:
        raise ValueError("ARM full scan is incomplete")
    batches = sorted(arm.glob("batch-*.jsonl"))
    analysis_digest = canonical_digest(
        {
            "algorithm_version": "optimized-ordinary-arm-full-scan-analysis-v1",
            "recording_manifest_sha256": MANIFEST,
            "completion_sha256": sha256(arm / "completion.json"),
            "inventory_sha256": sha256(arm / "inventory.json"),
            "batch_set_digest": digest_files(batches),
            "installed_hashes_sha256": sha256(arm / "installed-hashes.log"),
        }
    )
    manifest, receipt = published.manifest, published.manifest.receipt
    timing = manifest.timing
    fs = receipt.plan.geometry.sample_rate_hz
    uncertainty = math.hypot(400.0, 15_000.0 * timing.first_sample_bracket_width_ns / 2e9)
    raw_authority = canonical_digest({"capture": MANIFEST, "iq": manifest.uncompressed_sha256})
    stream_generation = f"adaptive-iio-{receipt.stream_generation:016x}"
    calls: dict[int, dict] = {}
    for path in batches:
        begin = int(path.stem.split("-")[1])
        rows = [item["result"] for line in path.read_text().splitlines() if "result" in (item := json.loads(line))]
        for local, call in enumerate(rows):
            visit = begin + local
            if call["sequence"] != local or visit in calls:
                raise ValueError("ARM batch-local sequence differs")
            calls[visit] = call
    if set(calls) != set(range(2215)):
        raise ValueError("ARM call coverage differs")
    output: list[PersistentHopCfoCandidate] = []
    payload_start = 0
    for visit, event in enumerate(receipt.events):
        source = inventory[visit]
        if source["visit"] != visit or source["event"] != event.model_dump(mode="json"):
            raise ValueError(f"ARM source authority differs at visit {visit}")
        call = calls[visit]
        for row in call["rows"]:
            receiver = row["receiver_id"]
            group_id = canonical_digest(
                {"capture": MANIFEST, "visit": visit, "rx": receiver, "probe": 0}
            )
            for rank, candidate in enumerate(row["candidates"]):
                if rank != candidate.get("rank", rank) or candidate["margin"] < 0.025:
                    continue
                geometry = fractional_glrt64_support_geometry(
                    SimpleNamespace(
                        integer_epoch_sample=candidate["epoch"],
                        fractional_epoch_offset_samples=0.0,
                    ),
                    sample_rate_hz=fs,
                    probe_sample_count=fs // 50,
                )
                relative = event.valid_start_counter - timing.session_start_device_sample_counter

                def utc(local: float) -> int:
                    return timing.first_sample_estimate_utc_ns + round((relative + local) * 1e9 / fs)

                candidate_id = canonical_digest(
                    {"group": group_id, "rank": rank, "analysis": analysis_digest}
                )
                output.append(
                    PersistentHopCfoCandidate(
                        candidate_id=candidate_id,
                        source_group_id=group_id,
                        candidate_rank=rank,
                        session_id=SESSION,
                        input_manifest_digest=MANIFEST,
                        raw_recording_authority_digest=raw_authority,
                        radio_id=receipt.radio_id,
                        stream_generation=stream_generation,
                        receiver_id=receiver,
                        visit_index=visit,
                        probe_index=0,
                        channel=event.target.channel,
                        edge=StarlinkEdge(event.target.edge.value),
                        actual_rf_hz=float(event.target.rf_center_hz - event.actual_if_offset_hz),
                        source_sample_start=payload_start + geometry.source_start_in_probe,
                        source_sample_end=payload_start + geometry.source_end_in_probe,
                        support_start_utc_ns=utc(geometry.source_start_in_probe),
                        support_center_utc_ns=utc(geometry.center_in_probe_samples),
                        support_end_utc_ns=utc(geometry.source_end_in_probe),
                        measured_cfo_hz=candidate["tracking_cfo_hz"],
                        standard_uncertainty_hz=uncertainty,
                        factorial_support_moments_s=geometry.factorial_support_moments_s,
                        exact_score=candidate["exact_score"],
                        control_score=candidate["control_score"],
                        margin=candidate["margin"],
                    )
                )
        payload_start += event.valid_end_counter_exclusive - event.valid_start_counter
    return tuple(output), analysis_digest


def write_observations(output: Path, label: str, candidates) -> None:
    rows = [OBSERVATION_HEADER]
    mapping = [MAP_HEADER]
    for item in candidates:
        rows.append(
            "\t".join(
                map(
                    str,
                    (
                        item.candidate_id,
                        item.source_group_id,
                        item.receiver_id,
                        item.channel,
                        item.edge.value,
                        item.actual_rf_hz,
                        item.support_start_utc_ns,
                        item.support_center_utc_ns,
                        item.support_end_utc_ns,
                        item.measured_cfo_hz,
                        item.exact_score,
                        item.control_score,
                        item.margin,
                    ),
                )
            )
        )
        mapping.append(
            "\t".join(
                map(
                    str,
                    (
                        item.candidate_id,
                        item.source_group_id,
                        item.visit_index,
                        item.receiver_id,
                        item.probe_index,
                        item.candidate_rank,
                        "fractional" if label == "server" else "integer",
                        label,
                    ),
                )
            )
        )
    (output / f"{label}-observations.tsv").write_text("\n".join(rows) + "\n")
    (output / f"{label}-candidate-map.tsv").write_text("\n".join(mapping) + "\n")


def write_tracks_tsv(output: Path, trajectory, by_candidate) -> None:
    lines = [
        f"SUMMARY\t{trajectory.input_candidate_count}\t{trajectory.used_candidate_count}\t"
        f"{len(trajectory.tracklets)}",
        f"CONFIG\t{trajectory.config_digest}",
    ]

    def number(value: float) -> str:
        return format(value, ".17g")

    for track_index, tracklet in enumerate(trajectory.tracklets):
        channel, edge, receiver, actual_rf = tracklet.lane_key
        point_ids = [point.candidate_id for point in tracklet.points]
        segment_id = "sha256:" + hashlib.sha256(
            ("weighted_hough\0" + "\0".join(point_ids)).encode("utf-8")
        ).hexdigest()
        lines.append(
            "\t".join(
                (
                    "TRACK",
                    str(track_index),
                    segment_id,
                    tracklet.tracklet_id,
                    str(receiver),
                    str(channel),
                    edge.value,
                    number(actual_rf),
                    str(tracklet.start_utc_ns),
                    str(tracklet.end_utc_ns),
                    str(tracklet.reference_utc_ns),
                    number(tracklet.normalized_rate_hz_per_s),
                    number(tracklet.normalized_intercept_hz),
                    number(tracklet.residual_rms_hz),
                    number(tracklet.residual_max_hz),
                    number(tracklet.weighted_support),
                    str(len(tracklet.points)),
                )
            )
        )
        for point in tracklet.points:
            source = by_candidate[point.candidate_id]
            lines.append(
                "\t".join(
                    (
                        "POINT",
                        str(track_index),
                        point.candidate_id,
                        source.source_group_id,
                        str(point.relative_alias_index),
                        number(point.normalized_raw_cfo_hz),
                        number(point.normalized_dealiased_cfo_hz),
                    )
                )
            )
    (output / "server-tracks.tsv").write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--arm", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    store = AdaptiveHopIqStore(args.bulk_root, read_only=True)
    try:
        published = store.inspect(SESSION)
        if published.manifest_sha256 != MANIFEST:
            raise ValueError("recording manifest differs")
        projection_started = time.monotonic()
        server, server_analysis_digest = server_projection(args.server, published)
        arm, arm_analysis_digest = load_arm(args.arm, published)
        projection_seconds = time.monotonic() - projection_started
    finally:
        store.close()
    if len(server) != 10_066:
        raise ValueError(f"server projected count differs: {len(server)}")
    write_observations(args.output, "server", server)
    write_observations(args.output, "arm", arm)
    print(
        json.dumps(
            {
                "kind": "projection_complete",
                "server_observations": len(server),
                "arm_observations": len(arm),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    tracking_started = time.monotonic()
    config = PersistentHopTrajectoryConfig()
    trajectory = reconstruct_persistent_hop_trajectories(server, config=config)
    tracking_seconds = time.monotonic() - tracking_started
    write_json(args.output / "server-tracks.json", trajectory)
    by_candidate = {item.candidate_id: item for item in server}
    write_tracks_tsv(args.output, trajectory, by_candidate)
    lines = [
        "tracklet_id\tchannel\tedge\treceiver_id\tactual_rf_hz\tstart_utc_ns\t"
        "end_utc_ns\treference_utc_ns\tnormalized_rate_hz_per_s\t"
        "normalized_intercept_hz\tresidual_rms_hz\tresidual_max_hz\t"
        "weighted_support\tcandidate_id\tsource_group_id\tvisit\tcandidate_rank\t"
        "relative_alias_index"
    ]
    for tracklet in trajectory.tracklets:
        channel, edge, receiver, actual_rf = tracklet.lane_key
        for point in tracklet.points:
            source = by_candidate[point.candidate_id]
            lines.append(
                "\t".join(
                    map(
                        str,
                        (
                            tracklet.tracklet_id,
                            channel,
                            edge.value,
                            receiver,
                            actual_rf,
                            tracklet.start_utc_ns,
                            tracklet.end_utc_ns,
                            tracklet.reference_utc_ns,
                            tracklet.normalized_rate_hz_per_s,
                            tracklet.normalized_intercept_hz,
                            tracklet.residual_rms_hz,
                            tracklet.residual_max_hz,
                            tracklet.weighted_support,
                            point.candidate_id,
                            source.source_group_id,
                            source.visit_index,
                            source.candidate_rank,
                            point.relative_alias_index,
                        ),
                    )
                )
            )
    (args.output / "server-track-members.tsv").write_text("\n".join(lines) + "\n")
    report = {
        "schema": "org.leo.arm-fast-tracks-server-baseline/v1",
        "status": "pass",
        "session_id": SESSION,
        "recording_manifest_sha256": MANIFEST,
        "server_analysis_digest": server_analysis_digest,
        "arm_analysis_digest": arm_analysis_digest,
        "server_projected_observations": len(server),
        "arm_projected_observations": len(arm),
        "server_tracklets": len(trajectory.tracklets),
        "server_physical_groups": len(trajectory.physical_groups),
        "server_hypotheses": len(trajectory.hypotheses),
        "server_used_observations": trajectory.used_candidate_count,
        "trajectory_config_digest": trajectory.config_digest,
        "projection_semantics": "leo.application.scanner_trajectory.project_scanner_candidates",
        "tracking_semantics": "leo.analysis.persistent_hop_trajectory.reconstruct_persistent_hop_trajectories",
        "arm_projection_semantics": (
            "maintained fractional_glrt64_support_geometry at integer epoch with exact zero offset; "
            "integer ordinary score/CFO and unchanged 0.025 gate"
        ),
        "timing_s": {
            "both_projections": projection_seconds,
            "server_tracking": tracking_seconds,
            "whole": time.monotonic() - started,
        },
    }
    write_json(args.output / "report.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
