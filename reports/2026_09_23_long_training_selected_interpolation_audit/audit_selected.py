#!/usr/bin/env python3
"""Audit cached-state interpolation at sealed 6/16 TRAIN search selections."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from leo.sky.propagation import parse_element_sets

LIGHT_KM_S = 299_792.458
REFERENCE_RF_HZ = 11_200_000_000.0


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_interpolator(path: Path):
    spec = importlib.util.spec_from_file_location("regular_cache", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.interpolate_states


def receiver_ecef(latitude_deg: float, longitude_deg: float) -> np.ndarray:
    return geodetic_to_ecef_km(latitude_deg, longitude_deg, 0)


def doppler(position, velocity, receiver):
    delta = position - receiver
    return (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * velocity, axis=-1)
        / np.linalg.norm(delta, axis=-1)
    )


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output file required")
    inference = json.loads(args.inference.read_text())
    results = json.loads(args.results.read_text())
    if (
        hashlib.sha256(args.inference.read_bytes()).hexdigest()
        != args.inference_sha256.read_text().strip()
    ):
        raise ValueError("sealed inference hash mismatch")
    if (
        hashlib.sha256(args.results.read_bytes()).hexdigest()
        != args.results_sha256.read_text().strip()
    ):
        raise ValueError("sealed results hash mismatch")
    if inference["bindings"] != results["bindings"]:
        raise ValueError("post-seal results do not bind the sealed inference inputs")
    for sealed, post in zip(inference["views"], results["views"], strict=True):
        for left, right in zip(sealed["searches"], post["searches"], strict=True):
            for key in ("latitude_deg", "longitude_deg", "objective_rmse_hz"):
                if left["selected"][key] != right["selected"][key]:
                    raise ValueError("post-seal results changed a selected coordinate or objective")

    interpolate = load_interpolator(args.interpolation_helper)
    cache_bindings = {row["session_id"]: row for row in inference["bindings"]["sessions"]}
    archive = TleArchiveReader(args.tle_root)
    prepared_by_session = {}
    cache_by_session = {}
    snapshots = {
        (snapshot.sha256, snapshot.collected_utc_ns): snapshot
        for snapshot in archive.list_snapshots()
    }
    for session_id, binding in cache_bindings.items():
        cache_dir = args.cache_root / session_id
        receipt_path = cache_dir / "cache_receipt.json"
        cache_path = cache_dir / "state_cache.npz"
        if digest(receipt_path) != binding["receipt"] or digest(cache_path) != binding["cache"]:
            raise ValueError(f"sealed cache binding mismatch for {session_id}")
        receipt = json.loads(receipt_path.read_text())
        evidence = receipt["prepared_evidence"]
        snapshot = snapshots.get(
            (
                evidence["snapshot_digest"].removeprefix("sha256:"),
                evidence["snapshot_collected_utc_ns"],
            )
        )
        if snapshot is None:
            raise ValueError(f"saved causal snapshot unavailable for {session_id}")
        text, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
        prepared_by_session[session_id] = {
            "catalogue": parse_element_sets(text),
            "start_utc_ns": evidence["start_utc_ns"],
            "tracks": {track["track_id"]: track for track in evidence["tracks"]},
        }
        cache_by_session[session_id] = {
            "arrays": {
                key: value for key, value in np.load(cache_path, allow_pickle=False).items()
            },
            "receipt": receipt,
        }

    views = []
    all_track_rms = []
    for sealed_view, result_view in zip(inference["views"], results["views"], strict=True):
        searches = []
        for sealed_search, result_search in zip(
            sealed_view["searches"], result_view["searches"], strict=True
        ):
            selected = sealed_search["selected"]
            receiver = receiver_ecef(selected["latitude_deg"], selected["longitude_deg"])
            track_rows = []
            for scan in result_search["selected"]["scans"]:
                session_id = scan["session_id"]
                prepared = prepared_by_session[session_id]
                cache = cache_by_session[session_id]["arrays"]
                candidates = {
                    int(value): index
                    for index, value in enumerate(prepared["catalogue"].satellite_numbers)
                }
                cache_rows = {
                    int(value): index for index, value in enumerate(cache["candidate_id"])
                }
                for selected_track in scan["tracks"]:
                    candidate = selected_track["candidate_id"]
                    if candidate is None:
                        track_rows.append(
                            {
                                "session_id": session_id,
                                "track_id": selected_track["track_id"],
                                "status": "unmatched",
                            }
                        )
                        continue
                    candidate_id = int(candidate)
                    if candidate_id not in candidates or candidate_id not in cache_rows:
                        raise ValueError(
                            "sealed selected candidate is absent from causal cache or catalogue"
                        )
                    track = prepared["tracks"][selected_track["track_id"]]
                    times = np.asarray(track["times_s"], dtype=float)
                    mask = np.asarray(track["training_mask"], dtype=bool)
                    direct_p, direct_v, direct_ids = propagate_candidate_states(
                        prepared["catalogue"],
                        np.asarray([candidates[candidate_id]]),
                        prepared["start_utc_ns"],
                        times,
                        np.asarray([0.0]),
                    )
                    if direct_ids.tolist() != [candidates[candidate_id]]:
                        raise ValueError("direct propagation failed selected candidate")
                    block = {
                        "position_ecef_km": cache["position_ecef_km"][
                            cache_rows[candidate_id] : cache_rows[candidate_id] + 1
                        ],
                        "velocity_ecef_km_s": cache["velocity_ecef_km_s"][
                            cache_rows[candidate_id] : cache_rows[candidate_id] + 1
                        ],
                        "receive_plus_tau_offset_ns": cache["receive_plus_tau_offset_ns"],
                    }
                    interpolated_p, interpolated_v = interpolate(
                        block, np.rint(times * 1e9).astype(np.int64)
                    )
                    error = doppler(interpolated_p[0], interpolated_v[0], receiver) - doppler(
                        direct_p[0, 0], direct_v[0, 0], receiver
                    )
                    raw_rms = float(np.sqrt(np.mean(error[mask] ** 2)))
                    shape = error - float(np.mean(error[mask]))
                    shape_rms = float(np.sqrt(np.mean(shape[mask] ** 2)))
                    row = {
                        "session_id": session_id,
                        "track_id": selected_track["track_id"],
                        "status": "matched",
                        "candidate_id": candidate_id,
                        "training_observation_count": int(np.sum(mask)),
                        "raw_training_rms_hz": raw_rms,
                        "after_training_constant_removal_rms_hz": shape_rms,
                        "after_training_constant_removal_max_abs_hz": float(
                            np.max(np.abs(shape[mask]))
                        ),
                    }
                    track_rows.append(row)
                    all_track_rms.append(shape_rms)
            matched = [row for row in track_rows if row["status"] != "unmatched"]
            searches.append(
                {
                    "prior": sealed_search["prior"],
                    "selected_coordinate": {
                        key: selected[key] for key in ("latitude_deg", "longitude_deg")
                    },
                    "matched_track_count": len(matched),
                    "unmatched_track_count": len(track_rows) - len(matched),
                    "median_track_rms_hz": float(
                        np.median(
                            [row["after_training_constant_removal_rms_hz"] for row in matched]
                        )
                    ),
                    "max_track_rms_hz": float(
                        max(row["after_training_constant_removal_rms_hz"] for row in matched)
                    ),
                    "worst_tracks": sorted(
                        matched,
                        key=lambda row: row["after_training_constant_removal_rms_hz"],
                        reverse=True,
                    )[:5],
                }
            )
        views.append({"scan_count": sealed_view["scan_count"], "searches": searches})
    result = {
        "schema": "long-training-selected-interpolation-audit/v1",
        "scope": {
            "selection": "sealed TRAIN-only 6/16 tau-zero coordinates and candidates",
            "reference_or_validation_used": False,
            "catalogue_policy": "direct SGP4 from each selected track's same saved causal snapshot",
            "constant_removal": (
                "one training-row mean interpolation-minus-direct Doppler error per selected track"
            ),
        },
        "views": views,
        "aggregate": {
            "all_matched_track_count": len(all_track_rms),
            "median_track_rms_hz": float(np.median(all_track_rms)),
            "max_track_rms_hz": float(max(all_track_rms)),
        },
        "bindings": {
            "audit_tool": digest(Path(__file__)),
            "interpolation_helper": digest(args.interpolation_helper),
            "benchmark_helper": digest(args.benchmark_helper),
            "inference": digest(args.inference),
            "results": digest(args.results),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps(result["aggregate"], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--inference-sha256", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--results-sha256", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--interpolation-helper", type=Path, required=True)
    parser.add_argument("--benchmark-helper", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    run(parser.parse_args())


if __name__ == "__main__":
    main()
