#!/usr/bin/env python3
"""Training-only shared receiver-drift diagnostic on frozen scan caches."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _load_joint(path: Path):
    spec = importlib.util.spec_from_file_location("receiver_drift_joint", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def select_track(prediction):
    """Freeze candidate, tau and CFO from training rows only."""
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
    residual_all = (
        prediction.measured_hz - prediction.predictions_hz[candidate, tau] - cfo[candidate, tau]
    )
    return {
        "candidate_id": str(prediction.candidate_ids[candidate]),
        "tau_s": float(prediction.taus_s[tau]),
        "cfo_hz": float(cfo[candidate, tau]),
        "times_s": np.asarray(prediction.times_s, dtype=float),
        "training_mask": train,
        "residual_hz": residual_all,
    }


def fit_shared_slope(rows) -> float:
    """Fit one slope after projecting a separate intercept for every track."""
    numerator = denominator = 0.0
    for row in rows:
        train = row["training_mask"]
        time = row["times_s"][train]
        residual = row["residual_hz"][train]
        centered_time = time - time.mean()
        centered_residual = residual - residual.mean()
        numerator += float(np.sum(centered_time * centered_residual))
        denominator += float(np.sum(centered_time**2))
    return numerator / denominator if denominator else 0.0


def track_slope(row) -> float:
    train = row["training_mask"]
    time = row["times_s"][train]
    residual = row["residual_hz"][train]
    time = time - time.mean()
    return float(np.sum(time * (residual - residual.mean())) / np.sum(time**2))


def reserved_sse(rows, slope=0.0):
    sse = count = 0
    for row in rows:
        train = row["training_mask"]
        time = row["times_s"]
        # The training-fitted CFO is the intercept authority; centre the drift
        # at the training mean so adding a slope does not refit that intercept.
        adjusted = row["residual_hz"] - slope * (time - time[train].mean())
        held = adjusted[~train]
        sse += float(np.sum(held**2))
        count += len(held)
    return sse, count


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    split = json.loads(args.manifest.read_text())
    training_ids = split["partitions"]["train"]["session_ids"]
    joint = _load_joint(args.joint_tool)
    scan_index = {}
    bindings = {}
    for block in sorted(args.replication_root.glob("block_*")):
        manifest_path = block / "cache/cache_manifest.json"
        scans_path = block / "scans.json"
        if not manifest_path.exists():
            continue
        bindings[block.name] = {
            "cache_manifest": _digest(manifest_path),
            "scans": _digest(scans_path),
        }
        details = {row["session_id"]: row for row in json.loads(scans_path.read_text())}
        for row in json.loads(manifest_path.read_text())["scans"]:
            sid = row["session_id"]
            if sid in scan_index:
                raise ValueError(f"duplicate cached session {sid}")
            scan_index[sid] = (block / "cache", details[sid])
    sessions = [sid for sid in training_ids if sid in scan_index][: args.scan_limit]
    if len(sessions) != args.scan_limit:
        raise ValueError("insufficient cached training scans")
    scan_rows = []
    boundary_flags = []
    slope_deviations = []
    for sid in sessions:
        cache, published = scan_index[sid]
        evidence, arrays = joint.load_scan_cache(cache, sid)
        prior, source = min(
            published["priors"].items(),
            key=lambda item: item[1]["selected"]["capped_weighted_rmse_hz"],
        )
        point = source["selected"]
        selected = []
        metadata_fields = set()
        for track in evidence["tracks"]:
            metadata_fields.update(track)
            prediction = joint.prediction_for_track(
                evidence, arrays, track, point["latitude_deg"], point["longitude_deg"]
            )
            choice = select_track(prediction)
            if choice is not None:
                selected.append(choice)
        slope = fit_shared_slope(selected)
        base_sse, held_count = reserved_sse(selected)
        drift_sse, drift_count = reserved_sse(selected, slope)
        slopes = np.asarray([track_slope(row) for row in selected])
        boundary = np.asarray([abs(row["tau_s"]) == 5.0 for row in selected])
        boundary_flags.extend(boundary.tolist())
        slope_deviations.extend(np.abs(slopes - slope).tolist())
        scan_rows.append(
            {
                "session_id": sid,
                "seed_prior": prior,
                "seed_latitude_deg": point["latitude_deg"],
                "seed_longitude_deg": point["longitude_deg"],
                "tracks": len(selected),
                "reserved_observations": held_count,
                "shared_slope_hz_per_s": slope,
                "track_slope_median_hz_per_s": float(np.median(slopes)),
                "track_slope_iqr_hz_per_s": float(
                    np.quantile(slopes, 0.75) - np.quantile(slopes, 0.25)
                ),
                "tau_boundary_fraction": float(np.mean(boundary)),
                "base_reserved_rms_hz": float(np.sqrt(base_sse / held_count)),
                "shared_slope_reserved_rms_hz": float(np.sqrt(drift_sse / drift_count)),
                "receiver_metadata_fields": sorted(
                    metadata_fields & {"receiver_id", "channel_id", "rx_id", "device_id"}
                ),
            }
        )
    base_sse = sum(
        row["reserved_observations"] * row["base_reserved_rms_hz"] ** 2 for row in scan_rows
    )
    drift_sse = sum(
        row["reserved_observations"] * row["shared_slope_reserved_rms_hz"] ** 2 for row in scan_rows
    )
    count = sum(row["reserved_observations"] for row in scan_rows)
    slopes = np.asarray([row["shared_slope_hz_per_s"] for row in scan_rows])
    boundary_flags = np.asarray(boundary_flags, dtype=float)
    slope_deviations = np.asarray(slope_deviations)
    boundary_correlation = (
        float(np.corrcoef(boundary_flags, slope_deviations)[0, 1])
        if 0 < boundary_flags.sum() < len(boundary_flags)
        else None
    )
    result = {
        "schema": "position-receiver-drift-audit/v1",
        "scope": "first 12 cached sessions in frozen random-group training order",
        "selection_uses_training_rows_only": True,
        "reserved_role": "inner randomized-mask diagnostic only",
        "counts": {"scans": len(scan_rows), "reserved_observations": count},
        "shared_scan_slope_hz_per_s": {
            "min": float(slopes.min()),
            "median": float(np.median(slopes)),
            "max": float(slopes.max()),
            "rms": float(np.sqrt(np.mean(slopes**2))),
        },
        "aggregate_reserved_rms_hz": {
            "unchanged": float(np.sqrt(base_sse / count)),
            "shared_scan_slope": float(np.sqrt(drift_sse / count)),
        },
        "timing_boundary_diagnostic": {
            "track_count": len(boundary_flags),
            "tau_plus_or_minus_5_fraction": float(np.mean(boundary_flags)),
            "correlation_with_absolute_track_minus_scan_slope": boundary_correlation,
        },
        "per_receiver_model_available": any(row["receiver_metadata_fields"] for row in scan_rows),
        "missing_receiver_metadata": not any(row["receiver_metadata_fields"] for row in scan_rows),
        "confounding": (
            "slope includes receiver drift, orbit/identity error, timing error, and "
            "track curvature; "
            "it is not a calibrated oscillator estimate"
        ),
        "bindings": {
            "manifest": _digest(args.manifest),
            "joint_tool": _digest(args.joint_tool),
            "audit_tool": _digest(Path(__file__)),
            "blocks": bindings,
        },
        "scans": scan_rows,
    }
    args.output.mkdir(parents=True)
    (args.output / "receiver_drift.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    keys = (
        "counts",
        "shared_scan_slope_hz_per_s",
        "aggregate_reserved_rms_hz",
        "timing_boundary_diagnostic",
        "missing_receiver_metadata",
    )
    print(json.dumps({key: result[key] for key in keys}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--replication-root", type=Path, required=True)
    parser.add_argument("--joint-tool", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scan-limit", type=int, default=12)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
