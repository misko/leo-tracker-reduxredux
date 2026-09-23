#!/usr/bin/env python3
"""Bounded shared-position comparison for the frozen sixteen scans.

The candidate universe is deliberately conditional: within each scan it is the
union of every NORAD selected by either published Sacramento or Reno search.
Receiver truth is never read while building the cache or fitting a position.
"""

# ruff: noqa: E402
from __future__ import annotations

import os
for _key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_key] = "1"

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen

import numpy as np
from matplotlib.figure import Figure
from scipy.optimize import minimize

from leo.analysis.adaptive_tle_position import AdaptiveTrackPrediction, score_point
from leo.analysis.adaptive_tle_prediction import LIGHT_KM_S, REFERENCE_RF_HZ
from leo.sky.frames import greenwich_mean_sidereal_time_rad, julian_day_from_utc_ns, teme_to_ecef
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid

API = "http://127.0.0.1:8090"
TAUS = np.arange(-5.0, 6.0)


def _json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def _fetch(path: str):
    with urlopen(API + path, timeout=90) as response:
        return json.load(response)


def _production_authority(session_id: str, collected: int, digest: str) -> tuple[int, bytes]:
    """Read exact production authorities through their public read-only ports."""
    program = """\
import base64,json,sys
from pathlib import Path
from leo.operations.tle_archive import TleArchiveReader
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
sid,collected,digest=sys.argv[1],int(sys.argv[2]),sys.argv[3]
store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
try: start=store.load(sid).timing.first_sample_estimate_utc_ns
finally: store.close()
archive=TleArchiveReader(Path('/var/lib/leo/tle'))
ref=next(x for x in archive.list_snapshots() if x.collected_utc_ns==collected and x.digest==digest)
print(json.dumps({'start':start,'tle':base64.b64encode(archive.read(ref).encode()).decode()}))
"""
    result = subprocess.run(["sudo", "-n", "-u", "leo", str(Path(sys.executable)), "-c", program,
                             session_id, str(collected), digest], capture_output=True, text=True,
                            check=True)
    row = json.loads(result.stdout)
    payload = base64.b64decode(row["tle"])
    if "sha256:" + hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("TLE digest mismatch")
    return int(row["start"]), payload


def build_cache(selection: Path, output: Path) -> dict:
    # Frozen selection is newest-first; cache indices and accumulation are chronological.
    session_ids = list(reversed(json.loads(selection.read_text())["session_ids"]))
    rows, started = [], time.monotonic()
    for scan_index, sid in enumerate(session_ids):
        status = _fetch(f"/api/v1/scanner/tracking/{sid}/adaptive-tle-position-v2")
        document = status["manifest"]["document"]
        diagnostics = document["diagnostics"]
        evidence = diagnostics["track_evidence"]
        selected = diagnostics["selected_track_scores"]
        candidates = sorted(
            {int(row["candidate_id"]) for prior in ("sacramento", "reno")
             for row in selected[prior] if row["candidate_id"] is not None}
        )
        if len(evidence) != len(selected["sacramento"]):
            raise ValueError("track evidence/score accounting differs")
        digest = diagnostics["snapshot_digest"]
        start_ns, payload = _production_authority(
            sid, diagnostics["snapshot_collected_utc_ns"], digest)
        catalogue = parse_element_sets(payload.decode("ascii"))
        lookup = {int(number): i for i, number in enumerate(catalogue.satellite_numbers)}
        missing = set(candidates) - set(lookup)
        if missing:
            raise ValueError(f"selected candidates absent from causal catalogue: {missing}")
        maximum = max(max(track["times_s"]) for track in evidence)
        time_grid = np.arange(-5.0, np.ceil((maximum + 5) * 4) / 4 + 0.001, 0.25)
        epochs = start_ns + np.rint(time_grid * 1e9).astype(np.int64)
        state = propagate_grid(catalogue, SamplingGrid(tuple(map(int, epochs)), 0, 1.0),
                               [lookup[value] for value in candidates])
        jd, fraction = julian_day_from_utc_ns(epochs)
        position, velocity = teme_to_ecef(
            state.position_teme_km, state.velocity_teme_km_s,
            greenwich_mean_sidereal_time_rad(jd, fraction))
        if np.any(state.error_code != 0) or not np.all(np.isfinite(position)):
            raise ValueError("shortlist propagation failure")
        scan_dir = output / "scans"
        scan_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(scan_dir / f"{sid}.npz", time_grid_s=time_grid,
                            candidate_id=np.asarray(candidates, dtype=np.int64),
                            position_ecef_km=position, velocity_ecef_km_s=velocity)
        evidence_dir = output / "evidence"
        _json(evidence_dir / f"{sid}.json", {
            "session_id": sid, "scan_index": scan_index, "start_utc_ns": start_ns,
            "snapshot_digest": digest, "candidate_source":
            "union-of-all-production-sacramento-and-reno-selected-identities-in-scan",
            "candidate_ids": candidates, "tracks": evidence,
        })
        rows.append({"session_id": sid, "scan_index": scan_index, "tracks": len(evidence),
                     "observations": sum(len(x["times_s"]) for x in evidence),
                     "candidate_count": len(candidates), "state_nodes": len(time_grid),
                     "snapshot_digest": digest})
        print(f"cached {scan_index + 1}/16 {sid}: {len(evidence)} tracks, "
              f"{len(candidates)} candidates", flush=True)
    manifest = {
        "schema": "frozen16-conditional-state-cache/v1", "position_truth_used": False,
        "partition": "exact-production-saved-randomized-mask",
        "candidate_scope": "conditional prior-selected per-scan union; not full catalogue",
        "time_grid_step_s": 0.25, "tau_support_s": [-5.0, 5.0], "scans": rows,
        "tracks": sum(x["tracks"] for x in rows),
        "observations": sum(x["observations"] for x in rows),
        "elapsed_s": time.monotonic() - started,
    }
    _json(output / "cache_manifest.json", manifest)
    return manifest


@lru_cache(maxsize=32)
def load_scan_cache(cache: Path, session_id: str):
    """Shared consumer interface: evidence document plus mmap-safe numerical arrays."""
    evidence = json.loads((cache / "evidence" / f"{session_id}.json").read_text())
    arrays = np.load(cache / "scans" / f"{session_id}.npz", allow_pickle=False)
    return evidence, {key: arrays[key] for key in arrays.files}


def receiver_ecef(latitude_deg: float, longitude_deg: float, altitude_m: float = 0.0):
    lat, lon = np.deg2rad([latitude_deg, longitude_deg])
    a, f = 6378.137, 1 / 298.257223563
    e2 = f * (2 - f); n = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    h = altitude_m / 1000
    xyz = np.array([(n + h) * np.cos(lat) * np.cos(lon),
                    (n + h) * np.cos(lat) * np.sin(lon),
                    (n * (1 - e2) + h) * np.sin(lat)])
    up = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    return xyz, up


def prediction_for_track(evidence, arrays, track, latitude_deg, longitude_deg,
                         taus_s=TAUS) -> AdaptiveTrackPrediction:
    """Evaluate one cached state bank at a receiver; exact on the 0.25 s grid."""
    grid = arrays["time_grid_s"]
    times = np.asarray(track["times_s"], dtype=float)
    query = times[None, :] + np.asarray(taus_s)[:, None]
    fractional = (query - grid[0]) / 0.25
    low = np.floor(fractional).astype(int); high = np.minimum(low + 1, len(grid) - 1)
    weight = fractional - low
    position = arrays["position_ecef_km"][:, low, :] * (1 - weight)[None, :, :, None]
    position += arrays["position_ecef_km"][:, high, :] * weight[None, :, :, None]
    velocity = arrays["velocity_ecef_km_s"][:, low, :] * (1 - weight)[None, :, :, None]
    velocity += arrays["velocity_ecef_km_s"][:, high, :] * weight[None, :, :, None]
    receiver, up = receiver_ecef(latitude_deg, longitude_deg)
    delta = position - receiver; distance = np.linalg.norm(delta, axis=-1)
    prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * velocity, axis=-1) / distance
    visible = np.max(np.sum(delta * up, axis=-1) / distance, axis=(1, 2)) >= 0
    return AdaptiveTrackPrediction(track["track_id"], tuple(track["observation_ids"]), times,
        np.asarray(track["measured_hz"]), np.asarray(track["training_mask"], dtype=bool),
        arrays["candidate_id"].astype(str), np.asarray(taus_s), prediction, visible)


def score_location(cache: Path, sessions, latitude_deg: float, longitude_deg: float):
    predictions = []
    for sid in sessions:
        evidence, arrays = load_scan_cache(cache, sid)
        predictions.extend(prediction_for_track(evidence, arrays, track, latitude_deg,
                                                 longitude_deg) for track in evidence["tracks"])
    return score_point(0, 0, predictions)


def haversine_km(a, b):
    p1, p2 = np.deg2rad([a[0], b[0]]); dl = np.deg2rad(b[1] - a[1])
    x = np.sin((p2-p1)/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
    return 6371.0088 * 2*np.arctan2(np.sqrt(x), np.sqrt(1-x))


def compare(cache: Path, scans_path: Path, output: Path, budget_s: float):
    scans = json.loads(scans_path.read_text()); sessions = [x["session_id"] for x in scans]
    seeds = []
    for scan in scans:
        for prior in ("sacramento", "reno"):
            for key in ("selected", "finest"):
                p = scan["priors"][prior][key]; point = (p["latitude_deg"], p["longitude_deg"])
                if all(haversine_km(point, old) >= 20 for old in seeds): seeds.append(point)
    # Candidate seeds come only from inference outputs. Truth is introduced after selection.
    started = time.monotonic(); results = []
    prior_centres = ((38.5816, -121.4944, 250.0), (39.5296, -119.8138, 500.0))
    def objective(active_sessions, point):
        if any(haversine_km(point, centre[:2]) > centre[2] for centre in prior_centres):
            return 1e6
        return score_location(cache, active_sessions, *point).residual_rmse_hz
    for count in (16, 1, 2, 4, 8):
        if time.monotonic() - started > budget_s: break
        scored = []
        for point in seeds:
            value = score_location(cache, sessions[:count], *point)
            scored.append((value.residual_rmse_hz, point, value))
        scored.sort(key=lambda x: x[0]); retained = []
        for row in scored:
            if all(haversine_km(row[1], x[1]) >= 20 for x in retained): retained.append(row)
            if len(retained) == 4: break
        refined = []
        for _, seed, incumbent in retained:
            if time.monotonic() - started > budget_s: break
            fit = minimize(lambda x: objective(sessions[:count], tuple(x)),
                           seed, method="Nelder-Mead", options={"maxfev": 35, "xatol": .002,
                           "fatol": .01, "initial_simplex": np.array([seed,(seed[0]+.02,seed[1]),(seed[0],seed[1]+.02)])})
            candidates = [(incumbent.residual_rmse_hz, seed), (float(fit.fun), tuple(fit.x))]
            best = min(candidates)
            refined.append({"latitude_deg": best[1][0], "longitude_deg": best[1][1],
                            "rmse_hz": best[0], "seed": seed, "evaluations": int(fit.nfev),
                            "optimizer_converged": bool(fit.success),
                            "optimizer_message": str(fit.message)})
        refined.sort(key=lambda x: x["rmse_hz"])
        active = scans[:count]
        results.append({"scan_count": count,
                        "track_count": sum(x["priors"]["sacramento"]["accounting"]["eligible_track_count"] for x in active),
                        "observation_count": sum(x["priors"]["sacramento"]["accounting"]["eligible_observation_count"] for x in active),
                        "best": refined[0], "basins": refined})
        print(f"fit {count} scans: {refined[0]}", flush=True)
        _json(output/"inference_partial.json", {"position_truth_used_for_inference": False,
              "prior_support":"intersection: Sacramento 250 km and Reno 500 km",
              "results":results})
    # Reference is evaluation-only and intentionally absent above.
    truth = (37.84903264307456, -122.4856541910174)
    for row in results:
        row["best"]["error_km"] = haversine_km((row["best"]["latitude_deg"], row["best"]["longitude_deg"]), truth)
    ordered = sorted(results,key=lambda x:x["scan_count"])
    result = {"schema":"frozen16-joint-comparison/v1", "position_truth_used_for_inference":False,
              "candidate_scope":"conditional prior-selected per-scan union; not global recovery",
              "scan_prefix_is_sensitivity_not_chronological_validation":True,
              "prior_support":"intersection: Sacramento 250 km and Reno 500 km",
              "optimizer_budget":"Nelder-Mead, at most 35 evaluations per retained basin; incumbents preserved",
              "results":ordered,"runtime_s":time.monotonic()-started}
    _json(output/"results.json", result)
    fig=Figure(figsize=(9,4),layout="constrained"); ax=fig.subplots(1,2)
    ax[0].plot([r["scan_count"] for r in ordered],[r["best"]["rmse_hz"] for r in ordered],"o-")
    ax[1].plot([r["scan_count"] for r in ordered],[r["best"]["error_km"] for r in ordered],"o-")
    ax[0].set(xlabel="Scans accumulated",ylabel="Selection RMS (Hz)"); ax[1].set(xlabel="Scans accumulated",ylabel="Evaluation-only error (km)")
    for a in ax:a.grid(alpha=.25);a.set_xscale("log",base=2);a.set_xticks([1,2,4,8,16]);a.get_xaxis().set_major_formatter("{x:g}")
    fig.savefig(output/"comparison.png",dpi=160)
    return result


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--selection",type=Path,required=True)
    parser.add_argument("--scans",type=Path,required=True); parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--build-cache",action="store_true"); parser.add_argument("--cache-only",action="store_true")
    parser.add_argument("--budget-seconds",type=float,default=900)
    args=parser.parse_args(); cache=args.output/"cache"
    if args.build_cache: print(json.dumps(build_cache(args.selection,cache),indent=2))
    if args.cache_only: return
    print(json.dumps(compare(cache,args.scans,args.output,args.budget_seconds),indent=2))

if __name__ == "__main__": main()
