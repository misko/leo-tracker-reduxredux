#!/usr/bin/env python3
"""Freeze the 111-row DS11 waveform plan without opening IQ."""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BULK = Path("/srv/bulk/leo")
SESSION = "scan-fw-a32c07775a887379"
TARGETS = (
    "sha256:42e1cbd0cd4522d6be56fc76d372d1f0b87d9e122399591ec87d72221ea4536a",
    "sha256:e29fedf1addb57d03352652128a4a79908a56d92107f393487fea997b0c88691",
)


def read(path: Path):
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def alias_mapping(measured_hz: float, actual_rf_hz: float, cached_hz: float):
    native = float(measured_hz * actual_rf_hz / 11.2e9)
    alias_float = (native - cached_hz) * 4.4e-6
    alias = int(round(alias_float))
    if abs(alias_float - alias) >= 1e-8:
        raise ValueError("nonintegral deployed alias mapping")
    return native, alias


def select_training_rows(tracks: list[dict]) -> list[dict]:
    selected = []
    by_id = {track["track_id"]: track for track in tracks}
    if set(TARGETS) - set(by_id):
        raise ValueError("target track absent")
    for track_id in TARGETS:
        track = by_id[track_id]
        for index, is_training in enumerate(track["training_mask"]):
            if is_training:
                selected.append(
                    {
                        "track_id": track_id,
                        "observation_index": index,
                        "visit": track["visits"][index],
                        "time_s": track["times_s"][index],
                        "measured_hz": track["measured_hz"][index],
                    }
                )
    return selected


def main() -> None:
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    ds11_manifest_path = ROOT / "reports/2026_09_30_ds11_post_ds10/local/manifest.json"
    observations_path = (
        ROOT / "reports/2026_09_30_ds11_single10/exports/DS11-F001/observations.json"
    )
    phase_path = (
        ROOT / "reports/2026_09_30_ds11_hillclimb/source_loo/runs/phase1/00.json"
    )
    ds11 = read(ds11_manifest_path)
    observations = read(observations_path)
    phase = read(phase_path)
    capture = next(row for row in ds11["captures"] if row["session_id"] == SESSION)
    if (
        capture["sample_rate_hz"] != 5_000_000
        or capture["visits"] != 2218
        or capture["exclusion_reasons"]
        or observations["session_id"] != SESSION
        or observations["manifest_sha256"] != capture["manifest_sha256"]
    ):
        raise ValueError("DS11 scan-0 authority mismatch")
    phase_observations = [
        row for row in phase["input_artifacts"] if row["kind"] == "observations"
    ]
    if (
        len(phase_observations) != 1
        or Path(phase_observations[0]["path"]).resolve() != observations_path.resolve()
        or phase_observations[0]["sha256"] != f"sha256:{digest(observations_path)}"
    ):
        raise ValueError("source diagnosis observations binding mismatch")
    assignments = {row["track_id"]: row for row in phase["assignments"]}
    for track_id in TARGETS:
        row = assignments[track_id]
        if (
            row["norad"] != 65512
            or row["receiver_id"] != 0
            or row["confidence"] < 0.9
            or not row["unambiguous"]
        ):
            raise ValueError("frozen source assignment mismatch")

    planned = select_training_rows(observations["tracks"])
    if len(planned) != 111 or len({row["visit"] for row in planned}) != 111:
        raise ValueError("expected 111 distinct training visits")
    track_docs = {row["track_id"]: row for row in observations["tracks"]}

    source = ScannerTrackingInputStore(BULK)
    try:
        raw = source.load(SESSION)
    finally:
        source.close()
    if (
        raw.input_manifest_sha256 != capture["manifest_sha256"]
        or raw.analysis_manifest_sha256 != observations["analysis_manifest_sha256"]
        or raw.sample_rate_hz != 5_000_000
    ):
        raise ValueError("public tracking source binding mismatch")
    points_list = project_scanner_candidates(raw)
    points = {point.candidate_id: point for point in points_list}
    graph = reconstruct_persistent_hop_trajectories(
        points_list,
        config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6),
    )
    tracks = {track.tracklet_id: track for track in graph.tracklets}
    probes = {(p.receiver_id, p.visit_index, p.probe_index): p for p in raw.probes}

    rows = []
    for ordinal, planned_row in enumerate(planned):
        track_doc = track_docs[planned_row["track_id"]]
        track = tracks[planned_row["track_id"]]
        matched = [points[point.candidate_id] for point in track.points]
        if [point.visit_index for point in matched] != track_doc["visits"]:
            raise ValueError("public track visit sequence changed")
        timestamps = [
            (point.support_center_utc_ns - observations["start_utc_ns"]) / 1e9
            for point in matched
        ]
        if len(timestamps) != len(track_doc["times_s"]) or any(
            abs(a - b) >= 1e-9 for a, b in zip(timestamps, track_doc["times_s"], strict=True)
        ):
            raise ValueError("public track support-center timestamps changed")
        point = matched[planned_row["observation_index"]]
        probe = probes[point.receiver_id, point.visit_index, point.probe_index]
        candidate = next(
            row for row in probe.candidates if row.candidate_rank == point.candidate_rank
        )
        if (
            point.receiver_id != track_doc["receiver_id"]
            or point.visit_index != planned_row["visit"]
            or probe.actual_rf_hz != track_doc["rf_hz"]
            or point.channel != track_doc["channel"]
            or not track_doc["training_mask"][planned_row["observation_index"]]
        ):
            raise ValueError("selected point RF or training binding mismatch")
        native, alias = alias_mapping(
            planned_row["measured_hz"],
            probe.actual_rf_hz,
            candidate.fractional_tracking_cfo_hz,
        )
        rows.append(
            {
                "ordinal": ordinal,
                **planned_row,
                "support_center_utc_ns": point.support_center_utc_ns,
                "receiver_id": point.receiver_id,
                "channel": point.channel,
                "probe_index": point.probe_index,
                "candidate_rank": point.candidate_rank,
                "probe_start_ms": probe.probe_start_ms,
                "edge": probe.edge,
                "actual_rf_hz": probe.actual_rf_hz,
                "candidate": dataclasses.asdict(candidate),
                "native_dealiased_hz": native,
                "additive_alias": alias,
            }
        )

    track_freeze = []
    for track_id in TARGETS:
        track = track_docs[track_id]
        track_freeze.append(
            {
                "track_id": track_id,
                "receiver_id": track["receiver_id"],
                "channel": track["channel"],
                "rf_hz": track["rf_hz"],
                "visits": track["visits"],
                "times_s": track["times_s"],
                "training_mask": track["training_mask"],
                "training_count": sum(track["training_mask"]),
                "localization_held_count": len(track["training_mask"])
                - sum(track["training_mask"]),
            }
        )

    dependencies = [
        HERE / "README.md",
        HERE / "PROTOCOL.md",
        HERE / "prepare.py",
        HERE / "run.py",
        HERE / "test_prepare.py",
        HERE / "test_run.py",
        ds11_manifest_path,
        observations_path,
        phase_path,
        ROOT / "reports/2026_09_29_training_waveform/estimator.py",
        ROOT / "reports/2026_09_29_training_waveform/convention.py",
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/"
        "reference-template/sssVec.mat",
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/"
        "reference-template/referenceTemplate.mat",
        ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json",
    ]
    dependencies += sorted((ROOT / "reports/2026_09_27_ds7_header").glob("*.py"))
    dependencies += [
        Path(inspect.getfile(obj))
        for obj in (
            ScannerTrackingInputStore,
            AdaptiveHopIqStore,
            project_scanner_candidates,
            reconstruct_persistent_hop_trajectories,
        )
    ]
    sources = {str(path.resolve()): digest(path) for path in dependencies}
    output = {
        "schema": "ds11-norad65512-waveform-plan/v1",
        "session_id": SESSION,
        "conditional_norad": 65512,
        "capture": {
            key: capture[key]
            for key in (
                "manifest_sha256",
                "analysis_evidence_sha256",
                "chunk_inventory_sha256",
                "uncompressed_sha256",
                "sample_rate_hz",
                "visits",
            )
        },
        "start_utc_ns": observations["start_utc_ns"],
        "analysis_manifest_sha256": observations["analysis_manifest_sha256"],
        "tracks": track_freeze,
        "rows": rows,
        "denominator": 111,
        "training_rows": 111,
        "localization_held_rows": 65,
        "decoded_read_byte_cap": 532_800_000,
        "saved_excerpt_data_byte_cap": 44_400_000,
        "selection_policy": "all frozen training-mask rows; track ID then observation index",
        "reference_used": False,
        "iq_opened_during_preparation": False,
        "sources": dict(sorted(sources.items())),
    }
    out = HERE / "manifest.json"
    owner = (HERE / "prepare.py").stat()
    with out.open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
        stream.write("\n")
    os.chown(out, owner.st_uid, owner.st_gid)
    print(json.dumps({"rows": len(rows), "sources": len(sources)}))


if __name__ == "__main__":
    main()
