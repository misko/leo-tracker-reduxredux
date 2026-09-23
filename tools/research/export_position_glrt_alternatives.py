#!/usr/bin/env python3
"""Export saved GLRT alternatives for source groups used by position research."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from dataclasses import asdict
from pathlib import Path

from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.digests import canonical_digest
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

CANONICAL_RF_HZ = 11_200_000_000.0
PILOT_ALIAS_HZ = 1.0 / 4.4e-6


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def source_group_id(source, probe) -> str:
    return canonical_digest(
        {
            "capture": source.input_manifest_sha256,
            "visit": probe.visit_index,
            "rx": probe.receiver_id,
            "probe": probe.probe_index,
        }
    )


def wrap_alias_hz(value: float) -> float:
    return (value + PILOT_ALIAS_HZ / 2) % PILOT_ALIAS_HZ - PILOT_ALIAS_HZ / 2


def alternative_diagnostics(groups: list[dict]) -> dict:
    duplicate_count = 0
    groups_with_multiple = 0
    offsets = []
    for group in groups:
        unique = []
        for candidate in group["candidates"]:
            if not candidate["passed_fractional_margin_gate"]:
                continue
            epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
            if any(
                abs(candidate["fractional_tracking_cfo_hz"] - row[0]) < 0.01
                and abs(epoch - row[1]) < 0.01
                for row in unique
            ):
                duplicate_count += 1
                continue
            unique.append((candidate["fractional_tracking_cfo_hz"], epoch))
        groups_with_multiple += len(unique) > 1
        selected = group["selected_raw_candidate_cfo_hz"]
        offsets.extend(
            abs(wrap_alias_hz(frequency - selected))
            for frequency, _epoch in unique
            if abs(wrap_alias_hz(frequency - selected)) >= 0.01
        )
    return {
        "duplicate_passing_candidate_count": duplicate_count,
        "source_groups_with_multiple_unique_passing_candidates": groups_with_multiple,
        "nonzero_unique_circular_alternative_count": len(offsets),
        "median_nonzero_unique_circular_offset_hz": (
            statistics.median(offsets) if offsets else None
        ),
        "duplicate_equivalence": {
            "maximum_abs_native_cfo_difference_hz": 0.01,
            "maximum_abs_total_epoch_difference_samples": 0.01,
        },
    }


def export_session(source, shard: dict, *, projector=project_scanner_candidates) -> dict:
    session = shard["session"]
    if (
        shard.get("schema") != "position-research-rf-shard-v1"
        or session["session_id"] != source.session_id
        or session["input_manifest_sha256"] != source.input_manifest_sha256
        or session["analysis_manifest_sha256"] != source.analysis_manifest_sha256
        or session["raw_recording_authority_digest"] != source.raw_recording_authority_digest
    ):
        raise ValueError("RF shard and public tracking input authority differ")
    probes = {}
    for probe in source.probes:
        identity = source_group_id(source, probe)
        if identity in probes:
            raise ValueError("duplicate public source-group identity")
        probes[identity] = probe
    selected = {}
    for track in shard["tracks"]:
        for observation in track["observations"]:
            identity = observation["source_group_id"]
            if identity in selected:
                raise ValueError("RF shard reuses a selected source group")
            selected[identity] = observation
    projected = {
        (candidate.source_group_id, candidate.candidate_rank): candidate
        for candidate in projector(source)
    }
    groups = []
    selected_passing = 0
    selected_all = 0
    for identity, observation in sorted(selected.items()):
        probe = probes.get(identity)
        if probe is None:
            raise ValueError("selected source group absent from public tracking input")
        candidates = [asdict(candidate) for candidate in probe.candidates]
        raw = next(
            (
                candidate
                for candidate in candidates
                if candidate["candidate_rank"] == observation["fractional_candidate_rank"]
            ),
            None,
        )
        if raw is None or any(
            float(raw[key]) != float(observation[key])
            for key in (
                "fractional_exact_score",
                "fractional_control_score",
                "fractional_margin",
            )
        ):
            raise ValueError("selected RF row differs from its saved GLRT candidate")
        projected_selected = projected.get((identity, observation["fractional_candidate_rank"]))
        support_fields = (
            "source_sample_start",
            "source_sample_end",
            "support_start_utc_ns",
            "support_center_utc_ns",
            "support_end_utc_ns",
        )
        if projected_selected is None or any(
            getattr(projected_selected, key) != observation[key] for key in support_fields
        ):
            raise ValueError("selected RF row differs from public probe time/support")
        scale = CANONICAL_RF_HZ / probe.actual_rf_hz
        alias_spacing = PILOT_ALIAS_HZ * scale
        selected_native = observation["measured_cfo_hz"] / scale
        alias_value = (projected_selected.measured_cfo_hz - selected_native) / PILOT_ALIAS_HZ
        alias_index = round(alias_value)
        alias_closure_hz = abs(
            projected_selected.measured_cfo_hz - selected_native - alias_index * PILOT_ALIAS_HZ
        )
        if alias_closure_hz > 1e-5:
            raise ValueError("selected trajectory CFO is not an integer-alias transform")
        selected_all += len(candidates)
        selected_passing += sum(row["passed_fractional_margin_gate"] for row in candidates)
        groups.append(
            {
                "source_group_id": identity,
                "selected_candidate_rank": observation["fractional_candidate_rank"],
                "selected_trajectory_cfo_hz": observation["measured_cfo_hz"],
                "selected_raw_candidate_cfo_hz": projected_selected.measured_cfo_hz,
                "canonical_rf_scale": scale,
                "canonical_alias_spacing_hz": alias_spacing,
                "selected_relative_alias_index": alias_index,
                "selected_alias_closure_error_hz": alias_closure_hz,
                "visit_index": probe.visit_index,
                "receiver_id": probe.receiver_id,
                "probe_index": probe.probe_index,
                "channel": probe.channel,
                "edge": probe.edge,
                "actual_rf_hz": probe.actual_rf_hz,
                "candidates": candidates,
            }
        )
    all_candidates = sum(len(probe.candidates) for probe in source.probes)
    all_passing = sum(
        candidate.passed_fractional_margin_gate
        for probe in source.probes
        for candidate in probe.candidates
    )
    accounting = shard["accounting"]
    if (
        len(source.probes) != accounting["saved_probe_count"]
        or all_candidates != accounting["saved_fractional_candidate_count"]
        or all_passing != accounting["margin_passing_candidate_count"]
        or len(groups) != accounting["exported_observation_count"]
    ):
        raise ValueError("public tracking inventory differs from sealed shard accounting")
    document = {
        "session_id": source.session_id,
        "input_manifest_sha256": source.input_manifest_sha256,
        "analysis_manifest_sha256": source.analysis_manifest_sha256,
        "raw_recording_authority_digest": source.raw_recording_authority_digest,
        "source_probe_count": len(source.probes),
        "public_port_complete_analysis_verified": True,
        "source_fractional_candidate_count": all_candidates,
        "source_passing_candidate_count": all_passing,
        "selected_source_group_count": len(groups),
        "selected_group_fractional_candidate_count": selected_all,
        "selected_group_passing_candidate_count": selected_passing,
        "groups": groups,
        "alternative_diagnostics": alternative_diagnostics(groups),
        "selected_cfo_transformation": (
            "selected_trajectory_cfo_hz / canonical_rf_scale = "
            "selected_raw_candidate_cfo_hz - integer * (1 / 4.4us)"
        ),
    }
    document["content_digest"] = canonical_digest(document)
    return document


def run(root: Path, shards: Path, output: Path, sessions: list[str]) -> dict:
    if output.exists():
        raise FileExistsError(output)
    store = ScannerTrackingInputStore(root)
    try:
        documents = []
        for session_id in sessions:
            shard_path = shards / f"{session_id}.json"
            shard = json.loads(shard_path.read_text())
            document = export_session(store.load(session_id), shard)
            document["source_shard_file_digest"] = file_digest(shard_path)
            documents.append(document)
    finally:
        store.close()
    result = {
        "schema": "position-selected-glrt-alternatives/v1",
        "truth_accessed": False,
        "inference_performed": False,
        "sessions": documents,
        "accounting": {
            "session_count": len(documents),
            "selected_source_group_count": sum(
                row["selected_source_group_count"] for row in documents
            ),
            "selected_group_fractional_candidate_count": sum(
                row["selected_group_fractional_candidate_count"] for row in documents
            ),
            "selected_group_passing_candidate_count": sum(
                row["selected_group_passing_candidate_count"] for row in documents
            ),
            "source_probe_count": sum(row["source_probe_count"] for row in documents),
            "source_fractional_candidate_count": sum(
                row["source_fractional_candidate_count"] for row in documents
            ),
            "source_passing_candidate_count": sum(
                row["source_passing_candidate_count"] for row in documents
            ),
        },
    }
    all_groups = [group for session in documents for group in session["groups"]]
    result["alternative_diagnostics"] = alternative_diagnostics(all_groups)
    result["content_digest"] = canonical_digest(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--shards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--session", action="append", required=True)
    args = parser.parse_args()
    result = run(args.root, args.shards, args.output, args.session)
    print(json.dumps(result["accounting"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
