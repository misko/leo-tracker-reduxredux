#!/usr/bin/env python3
"""Read-only residual concentration audit for the sealed full-8h TRAIN fit."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def weighted_quantiles(values, weights, probabilities):
    order = np.argsort(values)
    values, weights = np.asarray(values)[order], np.asarray(weights)[order]
    cdf = np.cumsum(weights) / np.sum(weights)
    return [float(np.interp(probability, cdf, values)) for probability in probabilities]


def pairwise_covariance(rows):
    values = []
    for left in range(len(rows)):
        a = rows[left]
        by_second_a = {
            int(second): float(np.mean(a["residual"][np.floor(a["time"]) == second]))
            for second in np.unique(np.floor(a["time"])).astype(int)
        }
        for right in range(left + 1, len(rows)):
            b = rows[right]
            by_second_b = {
                int(second): float(np.mean(b["residual"][np.floor(b["time"]) == second]))
                for second in np.unique(np.floor(b["time"])).astype(int)
            }
            common = sorted(by_second_a.keys() & by_second_b.keys())
            if len(common) < 3:
                continue
            first = np.asarray([by_second_a[key] for key in common])
            second = np.asarray([by_second_b[key] for key in common])
            values.append(float(np.mean((first - first.mean()) * (second - second.mean()))))
    return values


def training_residual_rows(time, residual, training):
    """Return the only residual samples eligible for a TRAIN covariance audit."""
    return {"time": np.asarray(time)[training], "residual": np.asarray(residual)[training]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--single-tool", type=Path, required=True)
    parser.add_argument("--fast-loader", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("fresh output path required")

    inference_path = args.results / "inference.json"
    sealed = hashlib.sha256(inference_path.read_bytes()).hexdigest()
    if sealed != (args.results / "inference.sha256").read_text().strip():
        raise ValueError("sealed inference digest mismatch")
    inference = json.loads(inference_path.read_text())
    result = json.loads((args.results / "results.json").read_text())
    manifest = json.loads(args.manifest.read_text())
    sessions = manifest["source_group"]["session_ids"]
    if inference["session_ids"] != sessions or len(sessions) != 72:
        raise ValueError("sealed inference does not bind the frozen full TRAIN group")
    if inference["position_truth_used"] or inference["reserved_rows_used"]:
        raise ValueError("baseline inference is not TRAIN-only")
    expected_sources = {
        "single_tool": digest(args.single_tool),
        "fast_loader": digest(args.fast_loader),
    }
    if {key: inference["bindings"][key] for key in expected_sources} != expected_sources:
        raise ValueError("baseline helper source binding mismatch")
    cache_bindings = inference["bindings"]["sessions"]
    if [row["session_id"] for row in cache_bindings] != sessions:
        raise ValueError("baseline cache binding order differs from frozen sessions")
    for bound in cache_bindings:
        directory = args.cache_root / bound["session_id"]
        if (
            digest(directory / "cache_receipt.json") != bound["receipt"]
            or digest(directory / "state_cache.npz") != bound["cache"]
        ):
            raise ValueError(f"cache binding mismatch for {bound['session_id']}")
    single = load_module("audit_single", args.single_tool)
    single.LEVELS_KM = tuple(inference["levels_km"])
    loader = load_module("audit_loader", args.fast_loader)
    prepared = [
        loader.load_session(single, args.cache_root / session, session) for session in sessions
    ]
    selections = {row["prior"]: row["selected"] for row in result["searches"]}
    report = {
        "schema": "long-full8h-residual-audit/v1",
        "selection": "sealed full72 TRAIN baseline",
        "receiver_mapping": (
            "unknown: compact public evidence contract has no receiver field per track"
        ),
        "bindings": {
            "audit": digest(Path(__file__)),
            "baseline_inference": digest(inference_path),
            "baseline_results": digest(args.results / "results.json"),
            "manifest": digest(args.manifest),
            "single_tool": digest(args.single_tool),
            "fast_loader": digest(args.fast_loader),
        },
        "views": {},
    }
    for prior, point in selections.items():
        total_weight = total_loss = 0.0
        fixed = {
            scan["session_id"]: {row["track_id"]: row for row in scan["tracks"]}
            for scan in point["scans"]
        }
        track_rows, scan_rows, candidate_sessions = [], [], {}
        for session in prepared:
            fixed_scan = fixed[session["session_id"]]
            if {track["track_id"] for track in session["prepared"]} != set(fixed_scan):
                raise ValueError(f"fixed track IDs differ for {session['session_id']}")
            scan_data, loss, weight = [], 0.0, 0.0
            index = {str(value): i for i, value in enumerate(session["candidate_ids"])}
            for track in session["prepared"]:
                selected = fixed_scan[track["track_id"]]
                candidate = selected["candidate_id"]
                if candidate is None:
                    raise ValueError("unmatched candidate in sealed result")
                winner = index[candidate]
                receiver, _ = single.receiver_ecef(point["latitude_deg"], point["longitude_deg"])
                delta = track["position"][winner] - receiver
                distance = np.linalg.norm(delta, axis=-1)
                prediction = (
                    -single.REFERENCE_RF_HZ
                    / single.LIGHT_KM_S
                    * np.sum(delta * track["velocity"][winner], axis=-1)
                    / distance
                )
                residual = track["measured_hz"] - prediction
                training = track["training_mask"]
                residual -= np.mean(residual[training])
                time = track["times_s"]
                slope = float(
                    np.polyfit(time[training] - np.mean(time[training]), residual[training], 1)[0]
                )
                rms = float(np.sqrt(np.mean(residual[training] ** 2)))
                if not np.isclose(rms, selected["training_rms_hz"], rtol=0, atol=1e-8):
                    raise ValueError("fixed residual RMS differs from sealed score")
                item = {
                    "track_id": track["track_id"],
                    "candidate_id": candidate,
                    "span_s": float(np.ptp(time)),
                    "training_rms_hz": rms,
                    "slope_hz_per_s": slope,
                    "weight_s": track["weight_s"],
                    "capped_loss_hz2_s": float(track["weight_s"] * min(800.0, rms) ** 2),
                    **training_residual_rows(time, residual, training),
                }
                scan_data.append(item)
                track_rows.append(
                    {key: value for key, value in item.items() if key not in {"time", "residual"}}
                )
                candidate_sessions.setdefault(candidate, set()).add(session["session_id"])
                loss += item["capped_loss_hz2_s"]
                weight += track["weight_s"]
            total_loss += loss
            total_weight += weight
            slopes = np.asarray([row["slope_hz_per_s"] for row in scan_data])
            weights = np.asarray([row["weight_s"] for row in scan_data])
            mean_slope = float(np.average(slopes, weights=weights))
            covariance = pairwise_covariance(scan_data)
            scan_rows.append(
                {
                    "session_id": session["session_id"],
                    "track_count": len(scan_data),
                    "weight_s": float(weight),
                    "capped_loss_hz2_s": float(loss),
                    "training_rmse_hz": float(np.sqrt(loss / weight)),
                    "weighted_slope_hz_per_s": mean_slope,
                    "slope_weighted_sd_hz_per_s": float(
                        np.sqrt(np.average((slopes - mean_slope) ** 2, weights=weights))
                    ),
                    "slope_sign_coherence": float(
                        np.average(np.sign(slopes) == np.sign(mean_slope), weights=weights)
                    )
                    if mean_slope
                    else None,
                    "pair_covariance_count": len(covariance),
                    "pair_covariance_median_hz2": float(np.median(covariance))
                    if covariance
                    else None,
                }
            )
        recomputed = float(np.sqrt(total_loss / total_weight))
        if not np.isclose(recomputed, point["objective_rmse_hz"], rtol=0, atol=1e-8):
            raise ValueError("full fixed objective does not equal sealed baseline")
        losses = np.asarray([row["capped_loss_hz2_s"] for row in track_rows])
        order = np.argsort(losses)[::-1]
        recurrence = Counter(len(supported) for supported in candidate_sessions.values())
        report["views"][prior] = {
            "selected_coordinate": {
                "latitude_deg": point["latitude_deg"],
                "longitude_deg": point["longitude_deg"],
            },
            "objective_parity": {
                "sealed_rmse_hz": point["objective_rmse_hz"],
                "recomputed_rmse_hz": recomputed,
                "absolute_difference_hz": abs(recomputed - point["objective_rmse_hz"]),
            },
            "track_count": len(track_rows),
            "weight_s": total_weight,
            "track_span_s_weighted_quantiles": weighted_quantiles(
                [row["span_s"] for row in track_rows],
                [row["weight_s"] for row in track_rows],
                [0.1, 0.5, 0.9],
            ),
            "slope_hz_per_s_weighted_quantiles": weighted_quantiles(
                [row["slope_hz_per_s"] for row in track_rows],
                [row["weight_s"] for row in track_rows],
                [0.1, 0.5, 0.9],
            ),
            "top_track_loss_share": {
                "top_1": float(losses[order[:1]].sum() / total_loss),
                "top_10": float(losses[order[:10]].sum() / total_loss),
                "top_100": float(losses[order[:100]].sum() / total_loss),
            },
            "top_scan_loss_share": {
                "top_1": float(max(row["capped_loss_hz2_s"] for row in scan_rows) / total_loss),
                "top_10": float(
                    sum(sorted((row["capped_loss_hz2_s"] for row in scan_rows), reverse=True)[:10])
                    / total_loss
                ),
            },
            "candidate_recurrence": {
                "unique_candidate_ids": len(candidate_sessions),
                "support_scan_histogram": {
                    str(key): value for key, value in sorted(recurrence.items())
                },
                "candidate_ids_with_2plus_scans": sum(
                    value for count, value in recurrence.items() if count >= 2
                ),
            },
            "scan_summary": scan_rows,
            "top_tracks": [
                {key: value for key, value in track_rows[index].items()} for index in order[:20]
            ],
        }
    args.output.mkdir(parents=True)
    (args.output / "results.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    figure = Figure(figsize=(8, 4), layout="constrained")
    axes = figure.subplots(1, 2)
    for prior, view in report["views"].items():
        tracks = view["top_tracks"]
        axes[0].plot(
            range(1, len(tracks) + 1),
            [row["training_rms_hz"] for row in tracks],
            marker=".",
            label=prior,
        )
        axes[1].hist(
            [row["weighted_slope_hz_per_s"] for row in view["scan_summary"]],
            bins=18,
            alpha=0.5,
            label=prior,
        )
    axes[0].set(xlabel="Ranked top-loss track", ylabel="TRAIN CFO-centered RMS (Hz)")
    axes[1].set(xlabel="Scan weighted residual slope (Hz/s)", ylabel="Scans")
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend()
    figure.savefig(args.output / "residual_concentration.png", dpi=160)


if __name__ == "__main__":
    main()
