#!/usr/bin/env python3
"""Compare frozen full-catalogue winners with the conditional candidate cache."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

from leo.contracts.digests import canonical_digest


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_joint(path: Path):
    spec = importlib.util.spec_from_file_location("candidate_support_joint", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def select_training(prediction):
    """Select identity, integer tau, and CFO without reading reserved frequencies."""
    train = np.asarray(prediction.training_mask, dtype=bool)
    residual = prediction.measured_hz[None, None, train] - prediction.predictions_hz[..., train]
    cfo = residual.mean(axis=-1)
    mse = np.mean((residual - cfo[..., None]) ** 2, axis=-1)
    visible = np.asarray(prediction.visible, dtype=bool)
    if visible.ndim == 1:
        visible = np.broadcast_to(visible[:, None], mse.shape)
    mse = np.where(visible, mse, np.inf)
    candidate, tau = np.unravel_index(np.argmin(mse), mse.shape)
    if not np.isfinite(mse[candidate, tau]):
        return None
    held = ~train
    held_residual = (
        prediction.measured_hz[held]
        - prediction.predictions_hz[candidate, tau, held]
        - cfo[candidate, tau]
    )
    return {
        "candidate_id": str(prediction.candidate_ids[candidate]),
        "tau_s": float(prediction.taus_s[tau]),
        "training_rms_hz": float(np.sqrt(mse[candidate, tau])),
        "reserved_rms_hz": float(np.sqrt(np.mean(held_residual**2))),
    }


def span_bucket(weight_s: int) -> str:
    if weight_s < 10:
        return "03-09s"
    if weight_s < 20:
        return "10-19s"
    if weight_s < 40:
        return "20-39s"
    return "40s+"


def weighted_rms(rows, field: str) -> float:
    weights = np.asarray([row["weight_s"] for row in rows], dtype=float)
    values = np.asarray([row[field] for row in rows], dtype=float)
    return float(np.sqrt(np.sum(weights * values**2) / np.sum(weights)))


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output directory required")
    dataset = json.loads(args.dataset.read_text())
    training_ids = set(dataset["partitions"]["training"]["session_ids"])
    protocol = json.loads(args.protocol.read_text())
    locations = {row["location_id"]: row for row in protocol["locations"]}
    joint = _load_joint(args.joint_tool)
    cache_index = {}
    cache_bindings = {}
    for manifest_path in sorted(args.replication_root.glob("block_*/cache/cache_manifest.json")):
        cache_bindings[manifest_path.parent.parent.name] = _digest(manifest_path)
        for scan in json.loads(manifest_path.read_text())["scans"]:
            sid = scan["session_id"]
            if sid in cache_index:
                raise ValueError(f"duplicate cache session {sid}")
            cache_index[sid] = manifest_path.parent

    full_results = json.loads(args.full_results.read_text())
    result_sessions = {
        row["session_id"]: row
        for row in full_results["sessions"]
        if row["session_id"] in training_ids
    }
    retention_files = sorted(
        path for path in args.retention.glob("*.json") if path.stem in training_ids
    )
    retained = [json.loads(path.read_text()) for path in retention_files]
    retained = [row for row in retained if row["session_id"] in training_ids]
    if set(result_sessions) != {row["session_id"] for row in retained}:
        raise ValueError("training-intersection full-result and retention sessions differ")

    rows = []
    for receipt in retained:
        sid = receipt["session_id"]
        if receipt["locations_digest"] != full_results["locations_digest"]:
            raise ValueError(f"location binding mismatch for {sid}")
        evidence, arrays = joint.load_scan_cache(cache_index[sid], sid)
        tracks = {row["track_id"]: row for row in evidence["tracks"]}
        receipt_rows = {(row["location_id"], row["track_id"]): row for row in receipt["rows"]}
        evaluation_rows = {
            (row["location_id"], row["track_id"]): row
            for row in result_sessions[sid]["evaluation"]
        }
        expected = {(location_id, track_id) for location_id in locations for track_id in tracks}
        if set(receipt_rows) != expected or set(evaluation_rows) != expected:
            raise ValueError(f"exact track/location binding mismatch for {sid}")
        for location_id, location in locations.items():
            for track_id, track in tracks.items():
                receipt_row = receipt_rows[(location_id, track_id)]
                if canonical_digest(track["training_mask"]) != receipt_row["training_mask_digest"]:
                    raise ValueError(f"training mask mismatch for {sid}/{track_id}")
                prediction = joint.prediction_for_track(
                    evidence,
                    arrays,
                    track,
                    location["latitude_deg"],
                    location["longitude_deg"],
                )
                conditional = select_training(prediction)
                full = evaluation_rows[(location_id, track_id)]
                if conditional is None or not full["matched"]:
                    raise ValueError(f"unmatched comparison row for {sid}/{track_id}")
                full_winner = receipt_row["hypotheses"][0]
                if full_winner["candidate_id"] != full["candidate_id"]:
                    raise ValueError("retention/evaluation winner mismatch")
                rows.append(
                    {
                        "session_id": sid,
                        "location_id": location_id,
                        "track_id": track_id,
                        "weight_s": full["weight_s"],
                        "span_bucket": span_bucket(full["weight_s"]),
                        "full_candidate_id": full["candidate_id"],
                        "conditional_candidate_id": conditional["candidate_id"],
                        "full_winner_omitted": full["candidate_id"]
                        not in set(map(str, prediction.candidate_ids)),
                        "full_training_rms_hz": full["training_rms_hz"],
                        "full_reserved_rms_hz": full["evaluation_rms_hz"],
                        "conditional_training_rms_hz": conditional["training_rms_hz"],
                        "conditional_reserved_rms_hz": conditional["reserved_rms_hz"],
                    }
                )
    buckets = {}
    for bucket in ("03-09s", "10-19s", "20-39s", "40s+"):
        subset = [row for row in rows if row["span_bucket"] == bucket]
        if subset:
            buckets[bucket] = {
                "rows": len(subset),
                "omitted_fraction": sum(row["full_winner_omitted"] for row in subset) / len(subset),
            }
    result = {
        "schema": "position-candidate-support-audit/v1",
        "scope": "frozen-training-recording intersection only; five fixed coordinates",
        "reserved_role": "inner randomized-mask diagnostic only",
        "counts": {
            "sessions": len(retained),
            "track_location_rows": len(rows),
            "omitted_full_winners": sum(row["full_winner_omitted"] for row in rows),
            "different_training_map_identity": sum(
                row["full_candidate_id"] != row["conditional_candidate_id"] for row in rows
            ),
        },
        "omitted_fraction": sum(row["full_winner_omitted"] for row in rows) / len(rows),
        "by_track_span": buckets,
        "weighted_rms_hz": {
            "full_catalogue_training_map_training": weighted_rms(rows, "full_training_rms_hz"),
            "conditional_training_map_training": weighted_rms(rows, "conditional_training_rms_hz"),
            "full_catalogue_training_map_reserved": weighted_rms(rows, "full_reserved_rms_hz"),
            "conditional_training_map_reserved": weighted_rms(rows, "conditional_reserved_rms_hz"),
        },
        "bindings": {
            "dataset": _digest(args.dataset),
            "protocol": _digest(args.protocol),
            "full_results": _digest(args.full_results),
            "retention_files": {path.name: _digest(path) for path in retention_files},
            "cache_manifests": cache_bindings,
            "tool": _digest(Path(__file__)),
        },
        "rows": rows,
    }
    args.output.mkdir(parents=True)
    (args.output / "candidate_support.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    summary_keys = ("counts", "omitted_fraction", "by_track_span", "weighted_rms_hz")
    print(json.dumps({key: result[key] for key in summary_keys}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--full-results", type=Path, required=True)
    parser.add_argument("--retention", type=Path, required=True)
    parser.add_argument("--replication-root", type=Path, required=True)
    parser.add_argument("--joint-tool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
