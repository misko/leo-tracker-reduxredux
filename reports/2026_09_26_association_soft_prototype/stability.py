"""Conditional top-three identity sensitivity to seeded whole-bin split changes.

This is an exploratory sensitivity test. Candidate identities were selected
using the original observations; the new splits are not independent validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_prediction import RegionalTrackPredictionEvaluator, build_prediction_banks
from leo.cli.adaptive_tle_position import PRIORS, _point_factory
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

from run_prototype import _distance_km, _local


def masks(times, seed, repetitions=32):
    groups, inverse = np.unique(np.floor(times).astype(int), return_inverse=True)
    if len(groups) < 2:
        raise ValueError("at least two whole time bins required")
    rng = np.random.default_rng(seed)
    train_count = min(len(groups) - 1, max(1, round(0.6 * len(groups))))
    for _ in range(repetitions):
        selected = np.sort(rng.choice(len(groups), train_count, replace=False))
        yield np.isin(inverse, selected), groups[selected].tolist()


def winners(measured, predictions, visible, candidate_ids, partitions):
    output = []
    residual = measured[None, None, :] - predictions
    for training, _ in partitions:
        offsets = np.mean(residual[:, :, training], axis=2)
        centered = residual - offsets[:, :, None]
        fit = np.sqrt(np.mean(centered[:, :, training] ** 2, axis=2))
        score = np.sqrt(np.mean(centered[:, :, ~training] ** 2, axis=2))
        allowed = visible[:, None] if visible.ndim == 1 else visible
        fit = np.where(allowed, fit, np.inf)
        tau = np.argmin(fit, axis=1)
        usable = [i for i in range(len(candidate_ids)) if np.isfinite(fit[i, tau[i]])]
        if not usable:
            output.append(None)
            continue
        index = min(usable, key=lambda i: (score[i, tau[i]], fit[i, tau[i]], int(candidate_ids[i])))
        output.append(str(candidate_ids[index]))
    return output


def analyze(session, bulk, tle):
    sid = session["session_id"]
    source = ScannerTrackingInputStore(bulk)
    try:
        prepared = prepare_adaptive_tle_position_inputs(sid, inputs=source, archive=TleArchiveReader(tle))
    finally:
        source.close()
    if prepared.evidence_sha256 != session["bindings"]["evidence_sha256"]:
        raise ValueError("source evidence changed")
    if prepared.snapshot_digest != session["bindings"]["snapshot_digest"]:
        raise ValueError("TLE snapshot changed")
    published_points = {}
    for prior, published in session["published"].items():
        point = min((x for x in session["evaluations"] if x["prior"] == prior), key=lambda x: _distance_km((x["latitude_deg"], x["longitude_deg"]), (published["latitude_deg"], published["longitude_deg"])))
        if _distance_km((point["latitude_deg"], point["longitude_deg"]), (published["latitude_deg"], published["longitude_deg"])) > 1e-5:
            raise ValueError("published seed absent")
        published_points[prior] = point
    candidate_ids = {c["candidate_id"] for p in published_points.values() for track in p["tracks"] for c in track["candidates"]}
    indices = np.asarray([i for i in prepared.candidate_indices if str(prepared.catalogue.satellite_numbers[i]) in candidate_ids])
    banks, _ = build_prediction_banks(prepared.catalogue, indices, prepared.start_utc_ns, prepared.tracks)
    output = {}
    for prior, point in published_points.items():
        lat, lon, _ = PRIORS[prior]
        evaluator = RegionalTrackPredictionEvaluator(banks, _point_factory(lat, lon))
        east, north = _local((lat, lon), (point["latitude_deg"], point["longitude_deg"]))
        track_stats = {x["track_id"]: x for x in point["tracks"]}
        blocks = {}
        for block in evaluator(east, north):
            blocks.setdefault(block.track_id, []).append(block)
        rows = []
        for track_id, parts in sorted(blocks.items()):
            stats = track_stats[track_id]
            ids = {x["candidate_id"] for x in stats["candidates"]}
            if not ids:
                continue
            predictions, visible, selected_ids = [], [], []
            for part in parts:
                for index, candidate_id in enumerate(part.candidate_ids):
                    if str(candidate_id) in ids:
                        predictions.append(part.predictions_hz[index])
                        visible.append(part.visible[index])
                        selected_ids.append(str(candidate_id))
            if set(selected_ids) != ids or len(selected_ids) != len(ids):
                raise ValueError("retained alternatives absent or duplicated")
            first = parts[0]
            prediction = np.asarray(predictions)
            visibility = np.asarray(visible)
            original = winners(first.measured_hz, prediction, visibility, selected_ids, [(first.training_mask, [])])[0]
            if original != stats["candidates"][0]["candidate_id"]:
                raise ValueError("original retained-candidate identity parity failed")
            seed = int.from_bytes(hashlib.sha256(f"soft-prototype-split-v1:{sid}:{track_id}".encode()).digest()[:8], "big")
            partitions = list(masks(first.times_s, seed))
            selected = winners(first.measured_hz, prediction, visibility, selected_ids, partitions)
            counts = Counter(selected)
            groups = np.unique(np.floor(first.times_s).astype(int))
            rows.append({"track_id": track_id, "seed": seed, "candidate_ids": selected_ids, "original_identity": original, "original_margin_hz": stats.get("margin_hz"), "weight_s": stats["weight_s"], "original_winner_fraction": counts[original] / len(selected), "winner_counts": dict(counts), "unique_split_count": len({tuple(p[1]) for p in partitions}), "total_bin_count": len(groups), "training_bin_count": len(partitions[0][1]), "scoring_bin_count": len(groups) - len(partitions[0][1]), "training_bins_each_split": [p[1] for p in partitions]})
        output[prior] = {"tracks": rows, "track_count": len(rows), "median_original_winner_fraction": float(np.median([r["original_winner_fraction"] for r in rows])) if rows else None, "duration_weighted_original_winner_fraction": float(np.average([r["original_winner_fraction"] for r in rows], weights=[r["weight_s"] for r in rows])) if rows else None, "tracks_below_75_percent": sum(r["original_winner_fraction"] < .75 for r in rows)}
    return {"session_id": sid, "branches": output}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()
    source_bytes = args.results.read_bytes()
    payload = {"protocol": {"scope": "conditional original top-three identities; fixed published locations", "repetitions": 32, "group_width_seconds": 1, "training_fraction": .6, "independent_validation": False, "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "results_sha256": hashlib.sha256(source_bytes).hexdigest()}, "sessions": []}
    for session in json.loads(source_bytes)["sessions"]:
        payload["sessions"].append(analyze(session, args.bulk_root, args.tle_root))
        args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
        print(session["session_id"], "stability complete", flush=True)
