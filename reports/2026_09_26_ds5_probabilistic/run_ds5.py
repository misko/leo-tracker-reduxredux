"""Read-only DS5 fixed-site probabilistic timing diagnostic.

The three sites are evaluated independently. Satellite identities are selected
at each site using only the existing training mask at zero timing, then frozen.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "reports/2026_09_26_reno_track_audit"
sys.path.insert(0, str(SOURCE))

from compare_scan_clock import (  # noqa: E402
    AdaptiveTlePositionStoreV2,
    RegionalTrackPredictionEvaluator,
    ScannerTrackingInputStore,
    TleArchiveReader,
    build_prediction_banks,
    point_factory,
    prepare_adaptive_tle_position_inputs,
)
from probabilistic_core import evaluate, fit_profiles, scale_at  # noqa: E402

HOUR = 3_600_000_000_000
DEVELOPMENT_SCAN = "scan-fw-d86e8f23c0624bac"
DEFAULT_MANIFEST = Path("/home/mouse9911/gits/leo-adaptive-position-deploy/reports/2026_09_26_ds5_since_local_midnight/manifest.json")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    os.replace(temporary, path)


def sites_from_document(document):
    priors = {row["name"]: row["selected"] for row in document["priors"]}
    return {
        "reference": document["diagnostics"]["reference_evaluation_only"],
        "sacramento": priors["sacramento"],
        "reno": priors["reno"],
    }


def select_zero_timing(prepared, sites):
    """Full-catalogue identity selection using training observations only."""
    banks, _ = build_prediction_banks(
        prepared.catalogue,
        prepared.candidate_indices,
        prepared.start_utc_ns,
        prepared.tracks,
        taus_s=np.array([0.0]),
    )
    output = {}
    for site_name, site in sites.items():
        best = {}
        evaluator = RegionalTrackPredictionEvaluator(
            banks,
            point_factory(site["latitude_deg"], site["longitude_deg"]),
            taus_s=np.array([0.0]),
        )
        for block in evaluator(0, 0):
            train = np.asarray(block.training_mask, dtype=bool)
            residual = block.measured_hz[None, :] - block.predictions_hz[:, 0, :]
            offset = residual[:, train].mean(axis=1)
            rms = np.sqrt(np.mean((residual[:, train] - offset[:, None]) ** 2, axis=1))
            visible = np.asarray(block.visible)
            if visible.ndim == 2:
                visible = visible[:, 0]
            for index, candidate_id in enumerate(block.candidate_ids):
                if not visible[index] or not np.isfinite(rms[index]):
                    continue
                row = {
                    "candidate_id": str(candidate_id),
                    "training_rms_hz": float(rms[index]),
                    "training_cfo_hz": float(offset[index]),
                }
                prior = best.get(block.track_id)
                if prior is None or (row["training_rms_hz"], int(row["candidate_id"])) < (
                    prior["training_rms_hz"], int(prior["candidate_id"])
                ):
                    best[block.track_id] = row
        missing = [track.track_id for track in prepared.tracks if track.track_id not in best]
        if missing:
            raise RuntimeError(f"{site_name}: no visible zero-time candidate for {missing}")
        output[site_name] = best
    return output


def selected_profiles(prepared, sites, selected, total_grid, noise_scales):
    lookup = {str(number): index for index, number in enumerate(prepared.catalogue.satellite_numbers)}
    selected_ids = sorted(
        {row["candidate_id"] for site in selected.values() for row in site.values()},
        key=int,
    )
    epochs = prepared.catalogue.element_epoch_utc_ns()
    ages = {
        candidate_id: float((prepared.start_utc_ns - epochs[lookup[candidate_id]]) / HOUR)
        for candidate_id in selected_ids
    }
    raw = {site: {} for site in sites}
    # Build only the at-most-three identities selected for each track. A union
    # across every track would propagate dozens of irrelevant satellites over
    # every observation and timing point.
    for track in prepared.tracks:
        track_ids = sorted(
            {selected[site_name][track.track_id]["candidate_id"] for site_name in sites},
            key=int,
        )
        banks, _ = build_prediction_banks(
            prepared.catalogue,
            [lookup[candidate_id] for candidate_id in track_ids],
            prepared.start_utc_ns,
            [track],
            taus_s=total_grid,
        )
        for site_name, site in sites.items():
            blocks = tuple(
                RegionalTrackPredictionEvaluator(
                    banks,
                    point_factory(site["latitude_deg"], site["longitude_deg"]),
                    taus_s=total_grid,
                )(0, 0)
            )
            wanted = selected[site_name][track.track_id]["candidate_id"]
            recovered = False
            for block in blocks:
                candidates = list(map(str, block.candidate_ids))
                if wanted not in candidates:
                    continue
                index = candidates.index(wanted)
                visible = np.asarray(block.visible)
                if visible.ndim == 2:
                    visible = visible[:, 0]
                if not visible[index]:
                    raise RuntimeError(f"{site_name}/{block.track_id}/{wanted}: selected candidate became invisible")
                raw[site_name][block.track_id] = {
                    "track_id": block.track_id,
                    "satellite_id": wanted,
                    "measured": block.measured_hz,
                    "prediction": block.predictions_hz[index],
                    "mask": block.training_mask,
                    "weight_s": len(np.unique(np.floor(track.times_s))),
                }
                recovered = True
                break
            if not recovered:
                raise RuntimeError(f"{site_name}/{track.track_id}/{wanted}: candidate block absent")
    profiles = {}
    for noise in noise_scales:
        profiles[noise] = {}
        for site_name, rows in raw.items():
            if len(rows) != len(prepared.tracks):
                raise RuntimeError(f"{site_name}: recovered {len(rows)}/{len(prepared.tracks)} selected tracks")
            profiles[noise][site_name] = [
                dict(
                    track_id=row["track_id"],
                    satellite_id=row["satellite_id"],
                    weight_s=row["weight_s"],
                    **fit_profiles(row["measured"], row["prediction"], row["mask"], noise),
                )
                for row in rows.values()
            ]
    return profiles, ages


def analyze_scan(capture, history_bins, bulk_root, tle_root, bound, step):
    started = time.monotonic()
    session_id = capture["session_id"]
    position_store = AdaptiveTlePositionStoreV2(bulk_root)
    status = position_store.status(session_id)
    if status.manifest is None:
        raise RuntimeError("position manifest absent")
    document = status.manifest.document.model_dump(mode="json")
    store = ScannerTrackingInputStore(bulk_root)
    try:
        prepared = prepare_adaptive_tle_position_inputs(
            session_id, inputs=store, archive=TleArchiveReader(tle_root)
        )
    finally:
        store.close()
    if prepared.evidence_sha256 != document["evidence_sha256"]:
        raise RuntimeError("evidence digest mismatch")
    if prepared.snapshot_digest != document["diagnostics"]["snapshot_digest"]:
        raise RuntimeError("snapshot digest mismatch")
    sites = sites_from_document(document)
    selected = select_zero_timing(prepared, sites)
    total = np.round(np.arange(round(-(bound + 3) / step), round((bound + 3) / step) + 1) * step, 6)
    delta = np.round(np.arange(round(-bound / step), round(bound / step) + 1) * step, 6)
    profiles, ages = selected_profiles(prepared, sites, selected, total, (50.0, 100.0, 200.0))
    experiments = []
    arm_map = {
        50.0: ("age_satellite", "age_satellite_scan"),
        100.0: ("zero", "free_per_track", "flat_satellite", "age_satellite", "age_satellite_scan"),
        200.0: ("age_satellite", "age_satellite_scan"),
    }
    for noise, arms in arm_map.items():
        scales = {candidate_id: scale_at(age, history_bins) for candidate_id, age in ages.items()}
        for mode in arms:
            clock = np.round(np.arange(-30, 31) / 10, 1) if mode == "age_satellite_scan" else np.array([0.0])
            timing = np.array([0.0]) if mode == "zero" else delta
            fit = {
                site_name: evaluate(
                    rows,
                    total,
                    timing,
                    clock,
                    1.0 if mode == "age_satellite_scan" else None,
                    scales,
                    per_track=mode == "free_per_track",
                    flat=mode in ("zero", "free_per_track", "flat_satellite"),
                )
                for site_name, rows in profiles[noise].items()
            }
            experiments.append(
                {
                    "noise_scale_hz": noise,
                    "mode": mode,
                    "sites": fit,
                    "gaps": {
                        f"reference_minus_{prior}_nll_per_observation": (
                            fit["reference"]["negative_log_score_per_test_observation"]
                            - fit[prior]["negative_log_score_per_test_observation"]
                        )
                        for prior in ("sacramento", "reno")
                    },
                }
            )
    return {
        "session_id": session_id,
        "capture_start_utc": capture["capture_start_utc"],
        "sample_rate_hz": capture["sample_rate_hz"],
        "median_visit_dwell_ms": capture["median_visit_dwell_ms"],
        "development_scan": session_id == DEVELOPMENT_SCAN,
        "document_sha256": status.manifest.document_sha256,
        "evidence_sha256": prepared.evidence_sha256,
        "snapshot_digest": prepared.snapshot_digest,
        "sites": {
            name: {"latitude_deg": value["latitude_deg"], "longitude_deg": value["longitude_deg"]}
            for name, value in sites.items()
        },
        "track_count": len(prepared.tracks),
        "fixed_identities": selected,
        "age_hours": ages,
        "experiments": experiments,
        "elapsed_s": time.monotonic() - started,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=HERE / "results.json")
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--bound", type=float, default=60.0)
    parser.add_argument("--step", type=float, default=0.1)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    history_path = SOURCE / "probabilistic_history.json"
    history = json.loads(history_path.read_text())
    latest_history_snapshot = max(row["collected_utc_ns"] for row in history["snapshots"])
    first_capture_ns = int(
        datetime.fromisoformat(manifest["captures"][0]["capture_start_utc"].replace("Z", "+00:00")).timestamp()
        * 1_000_000_000
    )
    if latest_history_snapshot >= first_capture_ns:
        raise RuntimeError("historical prior is not frozen before DS5")
    captures = [row for row in manifest["captures"] if row["admission_status"] == "included"]
    if args.limit is not None:
        captures = captures[: args.limit]
    payload = {
        "schema": "ds5-probabilistic-fixed-site/v1",
        "protocol": {
            "scope": "retrospective fixed-site diagnostic; no geographic search or cross-site sharing",
            "identity_selection": "independent full-catalogue zero-timing training-only RMS at each fixed site; frozen before timing arms",
            "sites": "published Sacramento/Reno winners are evaluation-selected; reference is diagnostic only",
            "split": "reused existing masks; not a new randomized holdout; overlapping-track independence not guaranteed",
            "timing": {"satellite_support_s": [-args.bound, args.bound], "step_s": args.step, "optional_clock_sigma_s": 1.0, "optional_clock_support_s": [-3.0, 3.0]},
            "residual": "normalized Student-t(4); per-track CFO profiled on training only; no RMS cap or drift",
            "history_latest_snapshot_utc_ns": latest_history_snapshot,
            "manifest_sha256": sha256(args.manifest),
            "history_sha256": sha256(history_path),
            "core_sha256": sha256(SOURCE / "probabilistic_core.py"),
            "source_sha256": sha256(Path(__file__)),
        },
        "dataset": {"manifest": str(args.manifest), "name": manifest["dataset_name"], "expected_included": len(captures)},
        "scans": [],
        "failures": [],
    }
    prior = {}
    if args.output.exists():
        prior = json.loads(args.output.read_text())
        if prior.get("protocol", {}).get("source_sha256") == payload["protocol"]["source_sha256"]:
            payload["scans"] = prior.get("scans", [])
            payload["failures"] = prior.get("failures", [])
    done = {row["session_id"] for row in payload["scans"]}
    for index, capture in enumerate(captures, 1):
        if capture["session_id"] in done:
            continue
        try:
            result = analyze_scan(capture, history["bins"], args.bulk_root, args.tle_root, args.bound, args.step)
            payload["scans"].append(result)
            print(f"{index}/{len(captures)} {capture['session_id']} {result['elapsed_s']:.1f}s", flush=True)
        except Exception as exc:
            payload["failures"].append({"session_id": capture["session_id"], "error": repr(exc)})
            atomic_json(args.output, payload)
            raise
        atomic_json(args.output, payload)


if __name__ == "__main__":
    main()
