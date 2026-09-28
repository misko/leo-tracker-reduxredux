#!/usr/bin/env python3
"""Freeze a small both-receiver DS7 CFO comparison without reading IQ."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def freeze(raw, baseline: dict, prepared, *, visits_per_partition: int = 2) -> dict:
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )
    from leo.application.scanner_trajectory import project_scanner_candidates

    projected = project_scanner_candidates(raw)
    points = {point.candidate_id: point for point in projected}
    graph = reconstruct_persistent_hop_trajectories(
        projected,
        config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6),
    )
    observation_ids = {
        track.tracklet_id: tuple(point.candidate_id for point in track.points)
        for track in graph.tracklets
    }
    rows = []
    for track in baseline["tracks"]:
        for candidate_id, training in zip(
            observation_ids[track["track_id"]], track["training_mask"], strict=True
        ):
            point = points[candidate_id]
            rows.append((point.visit_index, point.receiver_id, candidate_id, training, point))
    visits_by_rx = {receiver: {row[0] for row in rows if row[1] == receiver} for receiver in (0, 1)}
    common = sorted(visits_by_rx[0] & visits_by_rx[1])
    chosen_visits = []
    for partition in (True, False):
        eligible = []
        for visit in common:
            masks = {row[3] for row in rows if row[0] == visit and row[1] in (0, 1)}
            receivers = {row[1] for row in rows if row[0] == visit and row[3] is partition}
            if masks == {partition} and receivers == {0, 1}:
                eligible.append(visit)
        chosen_visits.extend(eligible[:visits_per_partition])
    selected = []
    for visit in chosen_visits:
        for receiver in (0, 1):
            choices = sorted(
                (row for row in rows if row[0] == visit and row[1] == receiver),
                key=lambda row: row[2],
            )
            if not choices:
                continue
            _, _, candidate_id, training, point = choices[0]
            selected.append(
                {
                    "candidate_id": candidate_id,
                    "receiver_id": receiver,
                    "visit_index": visit,
                    "probe_index": point.probe_index,
                    "channel": point.channel,
                    "edge": point.edge.value,
                    "actual_rf_hz": point.actual_rf_hz,
                    "source_sample_start": point.source_sample_start,
                    "source_sample_end": point.source_sample_end,
                    "support_start_utc_ns": point.support_start_utc_ns,
                    "support_center_utc_ns": point.support_center_utc_ns,
                    "support_end_utc_ns": point.support_end_utc_ns,
                    "acquisition_bound_cfo_hz": point.measured_cfo_hz,
                    "standard_uncertainty_hz": point.standard_uncertainty_hz,
                    "exact_score": point.exact_score,
                    "control_score": point.control_score,
                    "margin": point.margin,
                    "fractional_epoch_used": point.fractional_epoch_used,
                    "baseline_training_mask": bool(training),
                }
            )
    byte_count = sum(
        (row["source_sample_end"] - row["source_sample_start"]) * 4 for row in selected
    )
    return {
        "schema": "ds7-cfo-wave2-read-spec/v1",
        "session_id": raw.session_id,
        "manifest_sha256": raw.input_manifest_sha256,
        "analysis_manifest_sha256": raw.analysis_manifest_sha256,
        "raw_recording_authority_sha256": raw.raw_recording_authority_digest,
        "sample_rate_hz": raw.sample_rate_hz,
        "probe_ms": raw.probe_ms,
        "selection": (
            "earliest two all-training and earliest two all-held common visits; "
            "one deterministic candidate per receiver/visit"
        ),
        "methods": ["baseline", "ordinary_profile", "robust_profile", "differential_phase"],
        "frequency_policy": "all refinements remain in each acquisition-bound CFO basin",
        "held_policy": (
            "fit train windows only; predict held-window CFO from the train-window "
            "receiver line without fitting held frequencies; every method emits "
            "supported/rejected/inapplicable"
        ),
        "windows": selected,
        "planned_iq_bytes": byte_count,
        "iq_limit_bytes": 512 * 1024 * 1024,
        "compute_limit_seconds": 120,
        "reference_audit": "reference_excluded",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

    from leo.operations.tle_archive import TleArchiveReader

    baseline = json.loads(args.baseline.read_text())
    store = ScannerTrackingInputStore(args.bulk_root)
    try:
        raw = store.load(baseline["session_id"])

        class Inputs:
            def load(self, session_id):
                if session_id != raw.session_id:
                    raise ValueError("unexpected session")
                return raw

        prepared = prepare_adaptive_tle_position_inputs(
            raw.session_id, inputs=Inputs(), archive=TleArchiveReader(Path("/var/lib/leo/tle"))
        )
        result = freeze(raw, baseline, prepared)
    finally:
        store.close()
    result["baseline_export_sha256"] = (
        "sha256:" + hashlib.sha256(args.baseline.read_bytes()).hexdigest()
    )
    if not result["windows"] or {row["receiver_id"] for row in result["windows"]} != {0, 1}:
        raise RuntimeError("both-receiver matched support is unavailable")
    if result["planned_iq_bytes"] > result["iq_limit_bytes"]:
        raise RuntimeError("frozen read exceeds IQ limit")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
