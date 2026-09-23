#!/usr/bin/env python3
"""RF-only cross-receiver path authority for one saved adaptive scan."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from leo.application.scanner_trajectory import project_scanner_candidates
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

ALIAS_HZ = 1 / 4.4e-6


def _wrapped(value, period=ALIAS_HZ):
    return (np.asarray(value) + period / 2) % period - period / 2


@dataclass(frozen=True)
class Detection:
    source_group_id: str
    visit: int
    receiver: int
    channel: int
    edge: str
    time_s: float
    cfo_hz: float
    epoch_samples: float
    margin: float


def _detections(source, projected):
    group_by_probe = {
        (item.visit_index, item.receiver_id, item.probe_index): item.source_group_id
        for item in projected
    }
    origin = source.timing.session_start_device_sample_counter
    output = []
    for probe in source.probes:
        group = group_by_probe.get((probe.visit_index, probe.receiver_id, probe.probe_index))
        if group is None:
            continue
        for candidate in probe.candidates:
            if candidate.passed_fractional_margin_gate:
                output.append(
                    Detection(
                        group,
                        probe.visit_index,
                        probe.receiver_id,
                        probe.channel,
                        probe.edge,
                        (probe.valid_start_counter - origin) / source.sample_rate_hz
                        + probe.probe_start_ms / 1000,
                        candidate.fractional_tracking_cfo_hz,
                        probe.probe_start_ms * source.sample_rate_hz / 1000
                        + candidate.integer_epoch_sample
                        + candidate.fractional_epoch_offset_samples,
                        candidate.fractional_margin,
                    )
                )
    return output


def _timing_edges(detections, sample_rate_hz, *, visit_shift=0):
    period = sample_rate_hz / 750
    by_lane = {}
    for item in detections:
        key = (item.visit - (visit_shift if item.receiver == 1 else 0), item.channel, item.edge)
        by_lane.setdefault(key, {0: [], 1: []})[item.receiver].append(item)
    edges = []
    for lanes in by_lane.values():
        unique = {}
        for receiver, rows in lanes.items():
            keep = []
            for item in sorted(rows, key=lambda value: -value.margin):
                if not any(
                    abs(_wrapped(item.cfo_hz - prior.cfo_hz)) < 1000
                    and abs(_wrapped(item.epoch_samples - prior.epoch_samples, period)) <= 9
                    for prior in keep
                ):
                    keep.append(item)
            unique[receiver] = keep
        for left in unique[0]:
            for right in unique[1]:
                skew = float(abs(_wrapped(right.epoch_samples - left.epoch_samples, period)))
                if skew <= 9:
                    edges.append((left, right, float(_wrapped(right.cfo_hz - left.cfo_hz)), skew))
    return edges


def _shifted_lane_comparison_count(detections, shift):
    keys = {(item.visit, item.channel, item.edge, item.receiver) for item in detections}
    return sum(
        (visit + shift, channel, edge, 1) in keys
        for visit, channel, edge, receiver in keys
        if receiver == 0
    )


def _fit_offset(edges):
    if len(edges) < 12:
        return None
    delta = np.asarray([edge[2] for edge in edges])
    grid = np.linspace(-ALIAS_HZ / 2, ALIAS_HZ / 2, 256, endpoint=False)
    anchor = grid[np.argmax([np.sum(abs(_wrapped(delta - item)) < 1500) for item in grid])]
    mask = abs(_wrapped(delta - anchor)) < 1500
    times = np.asarray([edge[0].time_s for edge in edges])
    origin = float(np.median(times[mask]))
    design = np.column_stack((np.ones(len(times)), times - origin))
    unwrapped = anchor + _wrapped(delta - anchor)
    for _ in range(5):
        beta = np.linalg.lstsq(design[mask], unwrapped[mask], rcond=None)[0]
        residual = _wrapped(delta - design @ beta)
        scale = max(50.0, 1.4826 * np.median(abs(residual[mask] - np.median(residual[mask]))))
        mask = abs(residual) < min(1500, 4 * scale)
    if len({edge[0].visit for edge, keep in zip(edges, mask, strict=True) if keep}) < 12:
        return None
    return beta, origin


def _matches(edges, model):
    if model is None:
        return []
    beta, origin = model
    accepted = [
        edge
        for edge in edges
        if abs(_wrapped(edge[2] - beta @ np.asarray([1.0, edge[0].time_s - origin]))) <= 1000
    ]
    left_count, right_count = {}, {}
    for left, right, *_ in accepted:
        left_count[left] = left_count.get(left, 0) + 1
        right_count[right] = right_count.get(right, 0) + 1
    return [edge for edge in accepted if left_count[edge[0]] == right_count[edge[1]] == 1]


def _atomic(path, document):
    payload = json.dumps(document, indent=2, sort_keys=True).encode() + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(path)
    descriptor, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    with open(descriptor, "wb", closefd=True) as stream:
        stream.write(payload)
    Path(name).replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--shard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    shard = json.loads(args.shard.read_text())
    store = ScannerTrackingInputStore(args.bulk_root)
    try:
        source = store.load(shard["session"]["session_id"])
    finally:
        store.close()
    projected = project_scanner_candidates(source)
    detections = _detections(source, projected)
    timing_edges = _timing_edges(detections, source.sample_rate_hz)
    fit_edges = [edge for edge in timing_edges if edge[0].visit % 2 == 0]
    model = _fit_offset(fit_edges)
    held_edges = [edge for edge in timing_edges if edge[0].visit % 2 == 1]
    matches = _matches(held_edges, model)
    shifted = _matches(_timing_edges(detections, source.sample_rate_hz, visit_shift=17), model)
    shifted_53 = _matches(_timing_edges(detections, source.sample_rate_hz, visit_shift=53), model)
    track_by_group = {}
    for track in shard["tracks"]:
        for row in track["observations"]:
            track_by_group.setdefault(row["source_group_id"], []).append((track, row))

    def matching_tracks(detection):
        matches = []
        for track, row in track_by_group.get(detection.source_group_id, ()):
            lane = track["lane"]
            if (
                lane["receiver_id"] != detection.receiver
                or lane["channel"] != detection.channel
                or lane["edge"] != detection.edge
            ):
                continue
            scale = lane["canonical_rf_hz"] / lane["actual_rf_hz"]
            residual = _wrapped(row["measured_cfo_hz"] - detection.cfo_hz * scale, ALIAS_HZ * scale)
            if abs(residual) < 1:
                matches.append(track["tracklet_id"])
        return matches

    links = {}
    for left, right, delta, skew in matches:
        for left_track in matching_tracks(left):
            for right_track in matching_tracks(right):
                if left_track == right_track:
                    continue
                key = (left_track, right_track)
                links.setdefault(key, []).append((left, right, delta, skew))
    link_rows = []
    for (left, right), rows in sorted(links.items()):
        visits = sorted({row[0].visit for row in rows})
        if len(visits) < 3:
            continue
        beta, origin = model
        residual = [
            float(_wrapped(row[2] - beta @ np.asarray([1.0, row[0].time_s - origin])))
            for row in rows
        ]
        link_rows.append(
            {
                "rx0_tracklet_id": left,
                "rx1_tracklet_id": right,
                "anchor_visits": visits,
                "anchor_count": len(rows),
                "anchors": [
                    {
                        "visit": row[0].visit,
                        "rx0_source_group_id": row[0].source_group_id,
                        "rx1_source_group_id": row[1].source_group_id,
                    }
                    for row in rows
                ],
                "receiver_offset_residual_rms_hz": float(np.sqrt(np.mean(np.square(residual)))),
                "maximum_epoch_skew_samples": max(row[3] for row in rows),
                "alias_resolved": False,
                "identity_claimed": False,
            }
        )
    beta, origin = model
    document = {
        "schema": "recent-paired-source-authority-audit/v1",
        "session_id": source.session_id,
        "truth_accessed": False,
        "site_conditioned_candidates_used": False,
        "input_manifest_sha256": source.input_manifest_sha256,
        "analysis_manifest_sha256": source.analysis_manifest_sha256,
        "raw_recording_authority_digest": source.raw_recording_authority_digest,
        "shard_sha256": "sha256:" + hashlib.sha256(args.shard.read_bytes()).hexdigest(),
        "audit_source_sha256": "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "protocol": {
            "fit_partition": "even visits",
            "evaluation_partition": "odd visits",
            "timing_gate_samples": 9,
            "cfo_gate_hz": 1000,
            "pilot_alias_hz": ALIAS_HZ,
            "minimum_link_anchor_visits": 3,
            "shifted_control_visits": 17,
            "second_shifted_control_visits": 53,
        },
        "receiver_offset": {
            "intercept_hz_modulo_alias": float(beta[0]),
            "drift_hz_s": float(beta[1]),
            "reference_s": origin,
        },
        "rf_detection_table": [asdict(item) for item in detections],
        "accounting": {
            "qualified_detection_count": len(detections),
            "fit_timing_edge_count": len(fit_edges),
            "evaluation_timing_edge_count": len(held_edges),
            "evaluation_unique_match_count": len(matches),
            "shifted_control_unique_match_count": len(shifted),
            "shifted_control_lane_comparison_count": _shifted_lane_comparison_count(detections, 17),
            "shifted_53_control_unique_match_count": len(shifted_53),
            "shifted_53_control_lane_comparison_count": _shifted_lane_comparison_count(
                detections, 53
            ),
            "authorized_track_pair_count": len(link_rows),
        },
        "authorized_track_pairs": link_rows,
        "limitations": [
            "pilot-symbol alias is unresolved",
            "RF evidence links receiver-local paths but does not identify a satellite",
            "source-group membership maps a matched GLRT probe into a reconstructed track",
            "broadband coherence is omitted because generic common-band energy is not "
            "carrier-specific",
        ],
    }
    document["content_digest"] = (
        "sha256:"
        + hashlib.sha256(
            json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    _atomic(args.output, document)
    print(json.dumps(document["accounting"], sort_keys=True))


if __name__ == "__main__":
    main()
