#!/usr/bin/env python3
"""Training-only residual dependence audit for regularized position modelling."""

# ruff: noqa: E402
from __future__ import annotations

import os

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure


def _load_joint():
    path = Path(__file__).with_name("sixteen_joint_compare.py")
    spec = importlib.util.spec_from_file_location("regularized_noise_joint", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, path


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _quantiles(values):
    return dict(
        zip(
            ("min", "p25", "median", "p75", "max"),
            np.quantile(values, (0, 0.25, 0.5, 0.75, 1)).tolist(),
            strict=True,
        )
    )


def _select(prediction):
    train = np.asarray(prediction.training_mask, dtype=bool)
    residual = np.asarray(prediction.measured_hz)[None, None, :] - prediction.predictions_hz
    offset = residual[..., train].mean(axis=-1)
    centered = residual - offset[..., None]
    mse = np.mean(centered[..., train] ** 2, axis=-1)
    visible = np.asarray(prediction.visible, dtype=bool)
    if visible.ndim == 1:
        visible = np.broadcast_to(visible[:, None], mse.shape)
    mse = np.where(visible, mse, np.inf)
    candidate, tau = np.unravel_index(np.argmin(mse), mse.shape)
    if not np.isfinite(mse[candidate, tau]):
        return None
    return {
        "candidate_id": str(prediction.candidate_ids[candidate]),
        "tau_s": float(prediction.taus_s[tau]),
        "times_s": np.asarray(prediction.times_s)[train],
        "residual_hz": centered[candidate, tau, train],
    }


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    joint, joint_path = _load_joint()
    track_rows, scan_rows, adjacent_x, adjacent_y = [], [], [], []
    candidate_scans: dict[str, set[str]] = {}
    cache_digests = {}
    for block_number in (1, 2, 3):
        block = args.replication_root / f"block_{block_number:02d}"
        manifest_path = block / "cache" / "cache_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        cache_digests[block.name] = _digest(manifest_path)
        for scan in manifest["scans"]:
            sid = scan["session_id"]
            evidence, arrays = joint.load_scan_cache(block / "cache", sid)
            scan_sse = scan_n = scan_bins = 0
            for track in evidence["tracks"]:
                prediction = joint.prediction_for_track(
                    evidence, arrays, track, args.latitude, args.longitude
                )
                selected = _select(prediction)
                if selected is None:
                    continue
                times = selected["times_s"]
                residual = selected["residual_hz"]
                scale = float(np.sqrt(np.mean(residual**2)))
                bins = int(len(np.unique(np.floor(times).astype(int))))
                track_rows.append(
                    {
                        "session_id": sid,
                        "track_id": track["track_id"],
                        "candidate_id": selected["candidate_id"],
                        "tau_s": selected["tau_s"],
                        "training_observations": len(residual),
                        "one_second_bins": bins,
                        "rms_hz": scale,
                        "sse_hz2": float(np.sum(residual**2)),
                    }
                )
                candidate_scans.setdefault(selected["candidate_id"], set()).add(sid)
                scan_sse += float(np.sum(residual**2))
                scan_n += len(residual)
                scan_bins += bins
                # Lag one requires consecutive source observations in training.
                full_indices = np.flatnonzero(np.asarray(track["training_mask"], dtype=bool))
                consecutive = np.flatnonzero(np.diff(full_indices) == 1)
                if scale > 0 and len(consecutive):
                    standardized = residual / scale
                    adjacent_x.extend(standardized[consecutive].tolist())
                    adjacent_y.extend(standardized[consecutive + 1].tolist())
            scan_rows.append(
                {
                    "session_id": sid,
                    "training_observations": scan_n,
                    "one_second_bins": scan_bins,
                    "rms_hz": float(np.sqrt(scan_sse / scan_n)),
                }
            )
    x, y = np.asarray(adjacent_x), np.asarray(adjacent_y)
    rho = float(np.corrcoef(x, y)[0, 1]) if len(x) > 2 else float("nan")
    n = sum(row["training_observations"] for row in track_rows)
    bins = sum(row["one_second_bins"] for row in track_rows)
    sse = np.asarray([row["sse_hz2"] for row in track_rows])
    largest = max(1, int(np.ceil(0.1 * len(sse))))
    repeated = Counter(len(scans) for scans in candidate_scans.values())
    result = {
        "schema": "regularized-position-training-noise-audit/v1",
        "position_truth_used": False,
        "coordinate": [args.latitude, args.longitude],
        "coordinate_source": "previous exposed development solution; fixed before this audit",
        "data_scope": "training rows only from exposed training blocks 01-03",
        "candidate_scope": (
            "per-scan production-prior winner union; conditional, not full catalogue"
        ),
        "counts": {
            "scans": len(scan_rows),
            "tracks": len(track_rows),
            "training_observations": n,
            "one_second_track_bins": bins,
            "adjacent_training_pairs": len(x),
        },
        "dependence": {
            "pooled_within_track_adjacent_standardized_residual_correlation": rho,
            "ar1_observation_effective_count_heuristic": n * (1 - rho) / (1 + rho),
            "one_second_bin_to_observation_ratio": bins / n,
            "warning": "pooled AR(1) effective count is descriptive, not a calibrated likelihood",
        },
        "heterogeneity": {
            "track_rms_hz": _quantiles([row["rms_hz"] for row in track_rows]),
            "scan_rms_hz": _quantiles([row["rms_hz"] for row in scan_rows]),
            "largest_10_percent_tracks_share_of_training_sse": float(
                np.sort(sse)[-largest:].sum() / sse.sum()
            ),
            "candidate_distinct_scan_count_histogram": dict(sorted(repeated.items())),
            "candidates_seen_in_multiple_scans": sum(len(v) > 1 for v in candidate_scans.values()),
            "unique_selected_candidates": len(candidate_scans),
        },
        "track_rows": track_rows,
        "scan_rows": scan_rows,
        "bindings": {
            "joint_source": _digest(joint_path),
            "audit_source": _digest(Path(__file__)),
            "cache_manifests": cache_digests,
        },
    }
    args.output.mkdir(parents=True)
    (args.output / "noise_audit.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    fig = Figure(figsize=(12, 4), layout="constrained")
    axes = fig.subplots(1, 3)
    track_rms = np.asarray([row["rms_hz"] for row in track_rows])
    axes[0].hist(
        track_rms, bins=np.geomspace(max(1, track_rms.min()), track_rms.max(), 35), color="#267b9f"
    )
    axes[0].set(
        xscale="log", xlabel="Training track RMS (Hz)", ylabel="Tracks", title="Heavy residual tail"
    )
    ordered_sse = np.sort(sse)
    axes[1].plot(
        np.arange(1, len(sse) + 1) / len(sse), np.cumsum(ordered_sse) / sse.sum(), color="#a23b72"
    )
    axes[1].plot([0, 1], [0, 1], color="black", alpha=0.35, linestyle="--")
    axes[1].set(
        xlabel="Cumulative fraction of tracks",
        ylabel="Cumulative fraction of SSE",
        title="Residual influence concentration",
    )
    axes[2].plot([row["rms_hz"] for row in scan_rows], "o-", markersize=3, color="#d97904")
    axes[2].axhline(
        np.median([row["rms_hz"] for row in scan_rows]), color="black", linestyle="--", linewidth=1
    )
    axes[2].set(
        xlabel="Chronological training scan",
        ylabel="Training RMS (Hz)",
        title="Between-scan heterogeneity",
    )
    for axis in axes:
        axis.grid(alpha=0.2)
    fig.suptitle("Training-only residual structure · exposed blocks 01–03")
    fig.savefig(args.output / "noise_structure.png", dpi=160)
    print(
        json.dumps(
            {
                "counts": result["counts"],
                "dependence": result["dependence"],
                "heterogeneity": result["heterogeneity"],
            },
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replication-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
