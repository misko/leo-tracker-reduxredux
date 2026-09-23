"""Bind one predeclared TRAIN-only arc without opening reserved IQ."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from leo.analysis.persistent_hop_trajectory import (
    PersistentHopTrajectoryConfig,
    persistent_hop_tracklet_graph,
    reconstruct_persistent_hop_trajectories,
)
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.digests import canonical_digest
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

ROOT = Path(__file__).resolve().parents[2]
SESSION = "scan-hop-85afa91453f8847b"
SEED = 20260924
OUTPUT = ROOT / "reports/figures/2026_09_23_independent_phase/binding.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select_arc(tracks):
    """Longest support span, then lexical ID; no CFO, score, or position input."""
    return min(
        tracks, key=lambda row: (-(max(row["times_s"]) - min(row["times_s"])), row["track_id"])
    )


def random_visits(rows):
    if len({row["visit_index"] for row in rows}) != len(rows):
        raise ValueError("expected one observation per indivisible dwell")
    order = sorted(range(len(rows)), key=lambda index: rows[index]["time_s"])
    rng = np.random.default_rng(SEED)
    train = set()
    for block in np.array_split(np.asarray(order), 3):
        train.update(rng.permutation(block)[: (len(block) + 1) // 2].tolist())
    return [
        {"visit_index": row["visit_index"], "partition": "train" if index in train else "held"}
        for index, row in enumerate(rows)
    ]


def main():
    manifest_path = ROOT / "reports/2026_09_23_long_inventory_complete/manifest.json"
    receipt_path = ROOT / "reports/2026_09_23_long_cache_feasibility/results/cache_receipt.json"
    manifest = json.loads(manifest_path.read_text())
    if SESSION not in manifest["partitions"]["train"]["session_ids"]:
        raise ValueError("session must belong to frozen long-duration TRAIN partition")
    receipt = json.loads(receipt_path.read_text())
    if receipt["session_id"] != SESSION:
        raise ValueError("candidate cache session differs")
    evidence = receipt["prepared_evidence"]
    selected = select_arc(evidence["tracks"])
    wanted = {
        oid: (time, value)
        for oid, time, value, allowed in zip(
            selected["observation_ids"],
            selected["times_s"],
            selected["measured_hz"],
            selected["training_mask"],
            strict=True,
        )
        if allowed
    }
    source_store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        source = source_store.load(SESSION)
    finally:
        source_store.close()
    if (
        source.input_manifest_sha256 != evidence["input_manifest_sha256"]
        or source.analysis_manifest_sha256 != evidence["analysis_manifest_sha256"]
    ):
        raise ValueError("public source differs from frozen training cache")
    candidates = project_scanner_candidates(source)
    candidate_by_id = {row.candidate_id: row for row in candidates}
    trajectory = reconstruct_persistent_hop_trajectories(
        candidates, config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6)
    )
    if trajectory.config_digest != evidence["trajectory_digest"]:
        raise ValueError("trajectory reconstruction policy differs from training cache")
    track = next(row for row in trajectory.tracklets if row.tracklet_id == selected["track_id"])
    hypothesis = next(row for row in trajectory.hypotheses if track.tracklet_id in row.tracklet_ids)
    graph = persistent_hop_tracklet_graph(hypothesis, track.tracklet_id)
    by_binding = {row.source_binding_digest: row for row in graph.observations}
    probes = {(p.visit_index, p.receiver_id, p.probe_index): p for p in source.probes}
    rows = []
    for point in track.points:
        candidate = candidate_by_id[point.candidate_id]
        binding_id = canonical_digest(
            {
                "candidate_id": point.candidate_id,
                "actual_rf_hz": candidate.actual_rf_hz,
                "canonical_rf_hz": trajectory.canonical_rf_hz,
                "relative_alias_index": point.relative_alias_index,
                "fractional_epoch_used": True,
            }
        )
        observation = by_binding[binding_id]
        if observation.observation_id not in wanted:
            continue
        time, value = wanted[observation.observation_id]
        actual_time = (observation.support_center_utc_ns - evidence["start_utc_ns"]) / 1e9
        if abs(actual_time - time) > 1e-8 or abs(point.normalized_dealiased_cfo_hz - value) > 1e-5:
            raise ValueError("training observation differs from original track evidence")
        probe = probes[(candidate.visit_index, candidate.receiver_id, candidate.probe_index)]
        native = next(
            row for row in probe.candidates if row.candidate_rank == candidate.candidate_rank
        )
        rows.append(
            {
                "observation_id": observation.observation_id,
                "source_candidate_id": point.candidate_id,
                "time_s": time,
                "normalized_cfo_hz": value,
                "visit_index": candidate.visit_index,
                "receiver_id": candidate.receiver_id,
                "probe_index": candidate.probe_index,
                "probe_start_ms": probe.probe_start_ms,
                "channel": candidate.channel,
                "edge": candidate.edge.value,
                "source_actual_rf_hz": candidate.actual_rf_hz,
                "rf_normalization_scale": trajectory.canonical_rf_hz / candidate.actual_rf_hz,
                "dealiased_native_cfo_hz": value
                * candidate.actual_rf_hz
                / trajectory.canonical_rf_hz,
                "normalized_raw_cfo_hz": point.normalized_raw_cfo_hz,
                "relative_alias_index": point.relative_alias_index,
                "candidate_rank": candidate.candidate_rank,
                "integer_epoch_sample": native.integer_epoch_sample,
                "fractional_epoch_offset_samples": native.fractional_epoch_offset_samples,
                "fractional_tracking_cfo_hz": native.fractional_tracking_cfo_hz,
                "valid_start_counter": probe.valid_start_counter,
            }
        )
    if {row["observation_id"] for row in rows} != set(wanted):
        raise ValueError("training source binding is incomplete")
    iq_store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    analysis = AdaptiveHopAnalysisStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        published = iq_store.inspect(SESSION)
        capture = published.manifest.receipt
        product_binding = bind_actual_visit_analysis(
            capture, input_manifest_sha256=published.manifest_sha256, probe_stride_ms=120
        )
        ordinals = {row.event.visit_index: index for index, row in enumerate(capture.visits)}
        with analysis.job(product_binding) as job:
            for row in rows:
                row["iq_ordinal"] = ordinals[row["visit_index"]]
                product = job.read_visit(row["visit_index"])
                matches = [
                    candidate
                    for probe in product.probes
                    if probe.receiver_id == row["receiver_id"]
                    and probe.probe_index == row["probe_index"]
                    for candidate in probe.candidates
                    if candidate.candidate_rank == row["candidate_rank"]
                ]
                if len(matches) != 1:
                    raise ValueError("ambiguous public analysis source candidate")
                candidate = matches[0]
                if (
                    candidate.integer_epoch_sample != row["integer_epoch_sample"]
                    or abs(candidate.fractional_tracking_cfo_hz - row["fractional_tracking_cfo_hz"])
                    > 1e-7
                ):
                    raise ValueError("public analysis seed differs from source binding")
                row["acquired_cfo_hz"] = candidate.acquired_cfo_hz
                row["valid_sample_count"] = product.valid_end_counter - product.valid_start_counter
    finally:
        analysis.close()
        iq_store.close()
    output = {
        "schema": "independent-training-phase-binding/v1",
        "session_id": SESSION,
        "track_id": selected["track_id"],
        "selection": "longest support span in first frozen TRAIN session; lexical ID tie break",
        "sample_rate_hz": source.sample_rate_hz,
        "canonical_rf_hz": trajectory.canonical_rf_hz,
        "trajectory_config_digest": trajectory.config_digest,
        "input_manifest_sha256": source.input_manifest_sha256,
        "analysis_manifest_sha256": source.analysis_manifest_sha256,
        "source_first_counter": source.timing.session_start_device_sample_counter,
        "reference_utc_ns": evidence["start_utc_ns"],
        "selected_track_span_s": max(selected["times_s"]) - min(selected["times_s"]),
        "reserved_observations_not_bound": len(selected["observation_ids"]) - len(rows),
        "iq_read": False,
        "fresh_random_seed": SEED,
        "fresh_random_whole_visit_split": random_visits(rows),
        "observations": rows,
        "input_sha256": {
            str(path.relative_to(ROOT)): digest(path) for path in (manifest_path, receipt_path)
        },
        "source_sha256": digest(__file__),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: output[key]
                for key in (
                    "session_id",
                    "track_id",
                    "sample_rate_hz",
                    "selected_track_span_s",
                    "reserved_observations_not_bound",
                    "fresh_random_whole_visit_split",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
