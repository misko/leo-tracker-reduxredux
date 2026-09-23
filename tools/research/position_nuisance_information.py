"""Local Doppler sensitivity after nuisance projection; not an accuracy bound."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from tools.research.sixteen_joint_compare import load_scan_cache, prediction_for_track


def project_nuisance(jacobian, nuisance):
    """Remove the least-squares nuisance tangent space without normal equations."""
    j = np.asarray(jacobian, dtype=float)
    n = np.asarray(nuisance, dtype=float)
    if j.ndim != 2 or n.ndim != 2 or j.shape[0] != n.shape[0]:
        raise ValueError("matching observation rows required")
    if not np.all(np.isfinite(j)) or not np.all(np.isfinite(n)):
        raise ValueError("finite inputs required")
    return j - n @ np.linalg.lstsq(n, j, rcond=1e-10)[0]


def sensitivity(jacobians):
    j = np.vstack(jacobians)
    gram = j.T @ j / len(j)
    eig = np.maximum(np.linalg.eigvalsh(gram), 0)
    return {
        "observations": len(j),
        "gram_hz2_per_km2": gram.tolist(),
        "rms_change_for_300m_hz_min_max": (0.3 * np.sqrt(eig)).tolist(),
    }


def run(cache, output, latitude, longitude):
    manifest = json.loads((cache / "cache_manifest.json").read_text())
    stages = {
        name: []
        for name in ("fixed_nuisances", "track_cfo", "track_cfo_scan_tau", "track_cfo_and_tau")
    }
    rows = []
    for scan in manifest["scans"]:
        sid = scan["session_id"]
        evidence, arrays = load_scan_cache(cache, sid)
        scan_j, scan_dt = [], []
        for track in evidence["tracks"]:
            p = prediction_for_track(evidence, arrays, track, latitude, longitude)
            mask = np.asarray(track["training_mask"], dtype=bool)
            y = np.asarray(track["measured_hz"])[mask]
            bank = p.predictions_hz[..., mask]
            residual = y - bank
            residual -= residual.mean(axis=-1, keepdims=True)
            loss = np.mean(residual**2, axis=-1)
            loss[~p.visible, :] = np.inf
            if not np.isfinite(loss).any():
                continue
            candidate, k = np.unravel_index(np.argmin(loss), loss.shape)
            tau = float(p.taus_s[k])

            def pred(
                lat,
                lon,
                taus,
                evidence=evidence,
                arrays=arrays,
                track=track,
                candidate=candidate,
                mask=mask,
            ):
                return prediction_for_track(
                    evidence, arrays, track, lat, lon, np.asarray(taus)
                ).predictions_hz[candidate][:, mask]

            step_km = 0.1
            dlat = step_km / 111.195
            dlon = dlat / np.cos(np.deg2rad(latitude))
            north = (
                pred(latitude + dlat, longitude, [tau])[0]
                - pred(latitude - dlat, longitude, [tau])[0]
            ) / (2 * step_km)
            east = (
                pred(latitude, longitude + dlon, [tau])[0]
                - pred(latitude, longitude - dlon, [tau])[0]
            ) / (2 * step_km)
            lo, hi = max(-5.0, tau - 0.25), min(5.0, tau + 0.25)
            dt = np.diff(pred(latitude, longitude, [lo, hi]), axis=0)[0] / (hi - lo)
            j = np.column_stack([east, north])
            stages["fixed_nuisances"].append(j)
            stages["track_cfo"].append(project_nuisance(j, np.ones((len(y), 1))))
            scan_j.append(stages["track_cfo"][-1])
            scan_dt.append(dt - dt.mean())
            stages["track_cfo_and_tau"].append(
                project_nuisance(j, np.column_stack([np.ones(len(y)), dt]))
            )
            rows.append(
                {
                    "session_id": sid,
                    "track_id": track["track_id"],
                    "candidate_id": str(p.candidate_ids[candidate]),
                    "tau_s": tau,
                    "training_observations": len(y),
                }
            )
        if scan_j:
            stages["track_cfo_scan_tau"].append(
                project_nuisance(np.vstack(scan_j), np.concatenate(scan_dt)[:, None])
            )
    result = {
        "schema": "local-nuisance-sensitivity/v1",
        "coordinate": [latitude, longitude],
        "coordinate_source": "previous development solution; not reference truth",
        "selection": (
            "training-only identity and tau within previously exposed conditional candidate pool"
        ),
        "limitations": (
            "Local linearization with fixed identities, unweighted training rows; "
            "not a noise model, covariance, uncertainty or global accuracy bound. "
            "Tau at bounds uses a one-sided derivative; tangent projection permits "
            "both directions and is optimistic nuisance freedom."
        ),
        "tracks": rows,
        "stages": {k: sensitivity(v) for k, v in stages.items()},
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    fig = Figure(figsize=(9, 4.8), layout="constrained")
    ax = fig.subplots()
    for i, values in enumerate(result["stages"].values()):
        lo, hi = values["rms_change_for_300m_hz_min_max"]
        ax.plot([lo, hi], [i, i], "o-", linewidth=4)
    ax.set_yticks(
        range(4),
        [
            "Nuisances fixed",
            "Fit CFO per track",
            "Track CFO + scan timing",
            "Fit CFO + timing per track",
        ],
    )
    ax.set_xscale("log")
    ax.set_xlabel(
        "Local RMS frequency change for 300 m displacement (Hz)\n"
        "weakest–strongest horizontal direction"
    )
    ax.set_title(
        "Original development recordings · training samples only\n"
        "Fixed candidate identities; sensitivity, not achievable accuracy"
    )
    ax.grid(axis="x", alpha=0.3)
    fig.savefig(output / "sensitivity.png", dpi=160)
    print(json.dumps(result["stages"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    args = parser.parse_args()
    run(args.cache, args.output, args.latitude, args.longitude)
