#!/usr/bin/env python3
"""Audit post-fit blind CFO offsets modulo the unresolved pilot alias."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ALIAS_SPACING_HZ = 1.0 / 4.4e-6
CANONICAL_RF_HZ = 11_200_000_000.0


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def native_offset_hz(normalized_offset_hz: float, actual_rf_hz: float) -> float:
    if not np.isfinite(normalized_offset_hz) or not np.isfinite(actual_rf_hz):
        raise ValueError("offset and RF must be finite")
    if actual_rf_hz <= 0:
        raise ValueError("actual RF must be positive")
    return float(normalized_offset_hz * actual_rf_hz / CANONICAL_RF_HZ)


def wrap_alias_hz(value, spacing_hz: float = ALIAS_SPACING_HZ):
    if not np.isfinite(spacing_hz) or spacing_hz <= 0:
        raise ValueError("alias spacing must be finite and positive")
    values = np.asarray(value, dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError("offsets must be finite")
    wrapped = (values + spacing_hz / 2) % spacing_hz - spacing_hz / 2
    return float(wrapped) if wrapped.ndim == 0 else wrapped


def circular_mean_hz(values) -> float:
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)):
        raise ValueError("circular mean requires finite one-dimensional values")
    angle = values * 2 * np.pi / ALIAS_SPACING_HZ
    return float(np.angle(np.mean(np.exp(1j * angle))) * ALIAS_SPACING_HZ / (2 * np.pi))


def circular_stats(values) -> dict:
    values = np.asarray(values, dtype=float)
    mean = circular_mean_hz(values)
    residual = wrap_alias_hz(values - mean)
    return {
        "count": len(values),
        "circular_mean_hz": mean,
        "circular_rms_hz": float(np.sqrt(np.mean(residual**2))),
        "circular_median_abs_deviation_hz": float(np.median(np.abs(residual))),
        "circular_max_abs_deviation_hz": float(np.max(np.abs(residual))),
        "circular_range_hz": float(np.max(residual) - np.min(residual)),
        "resultant_length": float(
            abs(np.mean(np.exp(1j * values * 2 * np.pi / ALIAS_SPACING_HZ)))
        ),
    }


def run(args) -> None:
    if args.output.exists():
        raise ValueError("fresh output required")
    manifest_path = args.residuals / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    lane_by_track = {}
    source_digests = {}
    for shard_path in sorted(args.rf_shards.glob("scan-*.json")):
        shard = json.loads(shard_path.read_text())
        source_digests[str(shard_path)] = digest(shard_path)
        for track in shard["tracks"]:
            key = (shard["session"]["session_id"], track["tracklet_id"])
            if key in lane_by_track:
                raise ValueError("duplicate source track lane")
            lane_by_track[key] = track["lane"]
    tracks = []
    for entry in manifest["sessions"]:
        path = args.residuals / entry["file"]
        if digest(path) != entry["digest"]:
            raise ValueError("residual shard digest mismatch")
        shard = json.loads(path.read_text())
        for episode in shard["episodes"]:
            candidates = episode["candidate_support"]["candidates"]
            if not candidates:
                continue
            candidate = max(candidates, key=lambda item: item["soft_weight"])
            if candidate["soft_weight"] < args.minimum_weight:
                continue
            lane = lane_by_track[(entry["session_id"], episode["episode_id"])]
            for segment, offset in candidate["training_offset_hz_by_segment"].items():
                rows = [
                    row for row in candidate["rows"] if str(row["segment"]) == str(segment)
                ]
                actual_rf = {row["actual_rf_hz"] for row in rows}
                receivers = {row["receiver_id"] for row in rows}
                channels = {row["channel"] for row in rows}
                if len(actual_rf) != 1 or len(receivers) != 1 or len(channels) != 1:
                    raise ValueError("segment RF metadata is not constant")
                actual = actual_rf.pop()
                if (
                    actual != lane["actual_rf_hz"]
                    or receivers != {lane["receiver_id"]}
                    or channels != {lane["channel"]}
                ):
                    raise ValueError("residual metadata differs from source lane")
                native = native_offset_hz(offset, actual)
                tracks.append(
                    {
                        "session_id": entry["session_id"],
                        "episode_id": episode["episode_id"],
                        "catalog_number": candidate["catalog_number"],
                        "soft_weight": candidate["soft_weight"],
                        "receiver_id": lane["receiver_id"],
                        "channel": lane["channel"],
                        "pilot_edge": lane["edge"],
                        "actual_rf_hz": actual,
                        "normalized_training_offset_hz": offset,
                        "native_training_offset_hz": native,
                        "native_mod_alias_hz": wrap_alias_hz(native),
                    }
                )
    grouped = defaultdict(list)
    for track in tracks:
        grouped[
            (
                track["session_id"],
                track["receiver_id"],
                track["channel"],
                track["pilot_edge"],
                track["actual_rf_hz"],
            )
        ].append(track)
    groups = []
    for key, rows in sorted(grouped.items()):
        values = [row["native_mod_alias_hz"] for row in rows]
        stats = circular_stats(values)
        loo = []
        for index, value in enumerate(values):
            others = values[:index] + values[index + 1 :]
            if others:
                loo.append(wrap_alias_hz(value - circular_mean_hz(others)))
        stats.update(
            {
                "session_id": key[0],
                "receiver_id": key[1],
                "channel": key[2],
                "pilot_edge": key[3],
                "actual_rf_hz": key[4],
                "leave_one_track_out_count": len(loo),
                "leave_one_track_out_rms_hz": (
                    float(np.sqrt(np.mean(np.square(loo)))) if loo else None
                ),
                "leave_one_track_out_max_abs_hz": (
                    float(np.max(np.abs(loo))) if loo else None
                ),
            }
        )
        groups.append(stats)
    output = {
        "schema": "blind-postfit-alias-offset-audit/v1",
        "truth_accessed": False,
        "diagnostic_only": True,
        "alias_spacing_hz": ALIAS_SPACING_HZ,
        "canonical_rf_hz": CANONICAL_RF_HZ,
        "selection": f"frozen top candidate with soft_weight >= {args.minimum_weight}",
        "track_count": len(tracks),
        "tracks": tracks,
        "scan_receiver_channel_groups": groups,
        "limitations": [
            "offsets are post-selection diagnostics, not independent calibration evidence",
            "integer pilot alias remains unresolved",
            "pilot-edge labels come from source lanes and do not assert LNB mixing side",
        ],
        "provenance": {
            "residual_manifest_digest": digest(manifest_path),
            "residual_manifest_content_digest": manifest["content_digest"],
            "rf_shard_digests": source_digests,
            "source_code_digest": digest(Path(__file__)),
        },
    }
    output["content_digest"] = "sha256:" + hashlib.sha256(
        json.dumps(output, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--residuals", type=Path, required=True)
    parser.add_argument("--rf-shards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-weight", type=float, default=0.9)
    run(parser.parse_args())
