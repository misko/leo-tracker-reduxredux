#!/usr/bin/env python3
"""Freeze the scan-16 124-row waveform replication without opening IQ."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import inspect
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
HILL = HERE.parent
BULK = Path("/srv/bulk/leo")
SESSION = "scan-fw-6a8bd0ca578b58eb"
DENOMINATOR = 124
SELECTION = HILL / "waveform_position_replication16/target_selection.json"


def read(path: Path):
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_old_prepare():
    path = HILL / "norad65512_waveform/prepare.py"
    spec = importlib.util.spec_from_file_location("waveform_replication16_old_prepare", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def validate_selection(selection: dict) -> tuple[str, ...]:
    if (
        selection.get("schema") != "ds11-waveform-replication-target-selection/v1"
        or selection.get("index") != 16
        or selection.get("session_id") != SESSION
        or selection.get("reference_used") is not False
        or len(selection.get("candidates", [])) != 18
    ):
        raise ValueError("invalid frozen target selection")
    for name, expected in selection["sources"].items():
        if digest(Path(name)) != expected:
            raise ValueError(f"target-selection source mismatch: {name}")
    candidates = selection["candidates"]
    if len({row["norad"] for row in candidates}) != 18:
        raise ValueError("target-selection candidate coverage is not unique")
    winner = min(candidates, key=lambda row: (-row["en_movement_m"], row["norad"]))
    if winner != selection["selected"] or winner["norad"] != 67103:
        raise ValueError("target-selection rule does not select NORAD 67103")
    return tuple(selection["selected"]["track_ids"])


def select_training_rows(tracks: list[dict], targets: tuple[str, ...]) -> list[dict]:
    by_id = {track["track_id"]: track for track in tracks}
    if len(by_id) != len(tracks) or set(targets) - set(by_id):
        raise ValueError("target track coverage mismatch")
    selected = []
    for track_id in targets:
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


def duplicate_groups(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[tuple(row[key] for key in keys)].append(row["ordinal"])
    return [
        {"identity": list(identity), "ordinals": ordinals}
        for identity, ordinals in sorted(grouped.items())
        if len(ordinals) > 1
    ]


def main() -> None:
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    old = load_old_prepare()
    selection = read(SELECTION)
    targets = validate_selection(selection)
    ds11_manifest_path = ROOT / "reports/2026_09_30_ds11_post_ds10/local/manifest.json"
    observations_path = ROOT / "reports/2026_09_30_ds11_single10/exports/DS11-F045/observations.json"
    phase_path = HILL / "source_loo/runs/phase1/16.json"
    ds11, observations, phase = map(read, (ds11_manifest_path, observations_path, phase_path))
    capture = next(row for row in ds11["captures"] if row["session_id"] == SESSION)
    if (
        capture["sample_rate_hz"] != 5_000_000
        or capture["visits"] <= 0
        or capture["exclusion_reasons"]
        or observations["session_id"] != SESSION
        or observations["manifest_sha256"] != capture["manifest_sha256"]
        or phase["index"] != 16
        or phase["session_id"] != SESSION
        or phase["reference_used"] is not False
    ):
        raise ValueError("DS11 scan-16 authority mismatch")
    phase_observations = [row for row in phase["input_artifacts"] if row["kind"] == "observations"]
    if (
        len(phase_observations) != 1
        or Path(phase_observations[0]["path"]).resolve() != observations_path.resolve()
        or phase_observations[0]["sha256"] != f"sha256:{digest(observations_path)}"
    ):
        raise ValueError("source diagnosis observations binding mismatch")
    assignments = {row["track_id"]: row for row in phase["assignments"]}
    if set(targets) != {
        row["track_id"]
        for row in phase["assignments"]
        if row.get("norad") == 67103 and row.get("unambiguous")
    }:
        raise ValueError("selected physical-source membership mismatch")
    for track_id in targets:
        row = assignments[track_id]
        if row["confidence"] < 0.9 or not row["unambiguous"]:
            raise ValueError("selected source assignment is ambiguous")

    planned = select_training_rows(observations["tracks"], targets)
    expected_counts = {
        "sha256:f7bbef3aaef711c99500ad9360f05dc17ba8604064e4f67a298642b576750a3a": 22,
        "sha256:b6c1f80802c86ce471ff9a873a47e42b8ce46e86fb73691001673481347f470c": 56,
        "sha256:aa3959381600b5c74b2e866983f188b79172a94e650b137628ab5ea43d186dad": 46,
    }
    if len(planned) != DENOMINATOR or Counter(r["track_id"] for r in planned) != expected_counts:
        raise ValueError("expected 124 frozen training rows")
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
        candidate = next(row for row in probe.candidates if row.candidate_rank == point.candidate_rank)
        if (
            point.receiver_id != track_doc["receiver_id"]
            or point.visit_index != planned_row["visit"]
            or probe.actual_rf_hz != track_doc["rf_hz"]
            or point.channel != track_doc["channel"]
            or not track_doc["training_mask"][planned_row["observation_index"]]
        ):
            raise ValueError("selected point RF or training binding mismatch")
        native, alias = old.alias_mapping(
            planned_row["measured_hz"], probe.actual_rf_hz, candidate.fractional_tracking_cfo_hz
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

    visit_duplicates = duplicate_groups(rows, ("visit",))
    receiver_visit_duplicates = duplicate_groups(rows, ("visit", "receiver_id"))
    acquisition_duplicates = duplicate_groups(
        rows, ("visit", "receiver_id", "probe_index", "candidate_rank")
    )
    if receiver_visit_duplicates or acquisition_duplicates:
        raise ValueError("selected rows repeat an RX visit or exact acquisition identity")

    track_freeze = []
    for track_id in targets:
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
                "localization_held_count": len(track["training_mask"]) - sum(track["training_mask"]),
            }
        )

    dependencies = [
        HERE / "README.md",
        HERE / "PROTOCOL.md",
        HERE / "prepare.py",
        HERE / "run.py",
        HERE / "test_prepare.py",
        HERE / "test_run.py",
        SELECTION,
        ds11_manifest_path,
        observations_path,
        phase_path,
        HILL / "norad65512_waveform/prepare.py",
        HILL / "norad65512_waveform/run.py",
        ROOT / "reports/2026_09_29_training_waveform/estimator.py",
        ROOT / "reports/2026_09_29_training_waveform/convention.py",
        ROOT / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template/sssVec.mat",
        ROOT / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template/referenceTemplate.mat",
        ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json",
    ]
    dependencies += [Path(path) for path in selection["sources"]]
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
        "schema": "ds11-waveform-replication16-plan/v1",
        "session_id": SESSION,
        "scan_index": 16,
        "conditional_norad": 67103,
        "target_selection_path": str(SELECTION.resolve()),
        "target_selection_sha256": digest(SELECTION),
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
        "identity_audit": {
            "row_count": len(rows),
            "distinct_visits": len({row["visit"] for row in rows}),
            "repeated_visit_groups": visit_duplicates,
            "distinct_receiver_visits": len({(row["visit"], row["receiver_id"]) for row in rows}),
            "repeated_receiver_visit_groups": receiver_visit_duplicates,
            "distinct_acquisition_identities": len(
                {(row["visit"], row["receiver_id"], row["probe_index"], row["candidate_rank"]) for row in rows}
            ),
            "repeated_acquisition_identity_groups": acquisition_duplicates,
        },
        "denominator": DENOMINATOR,
        "training_rows": DENOMINATOR,
        "localization_held_rows": 81,
        "decoded_read_byte_cap": 595_200_000,
        "saved_excerpt_data_byte_cap": 49_600_000,
        "selection_policy": "frozen exact-IID max source-deletion EN movement; all training-mask rows",
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
    print(json.dumps({"rows": len(rows), "distinct_visits": output["identity_audit"]["distinct_visits"], "sources": len(sources)}))


if __name__ == "__main__":
    main()
