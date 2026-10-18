"""Matched blind localization controls for existing-IQ CFO remeasurements."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from iterate_dsx01_position_nominations import fit_once
from probe_dsx01_pilot_clock import ROOT
from profile_dsx01_geographic_calibration import geometry_problem, incumbents
from prototype_dsx01_calibration_modes import choose_pair

OUTPUT = ROOT / "reports/2026_10_18_dsx01_pilot_clock"
VARIANTS = ("original", "glrt64", "glrt300", "midpoint300")


def apply_measurements(scan, points, variant):
    if variant not in VARIANTS:
        raise ValueError("unknown measurement variant")
    ids = {oid for i in scan.curved for oid in scan.tracks[i]["observation_ids"]}
    if ids != points.keys():
        raise ValueError("remeasurement must cover exactly the original curved population")
    corrected = 0
    changes = []
    for i in scan.curved:
        track = scan.tracks[i]
        delta = np.zeros(len(track["times"]))
        for k, oid in enumerate(track["observation_ids"]):
            row = points[oid]
            if row["receiver"] != track["receiver"] or row["channel"] != track["channel"]:
                raise ValueError("remeasured receiver/channel differs")
            original = row["original_cfo_hz"]
            difference = track["values"][k] - original
            period = 1 / 4.4e-6
            if abs(difference - round(difference / period) * period) > 1e-5:
                raise ValueError("original CFO/graph alias lift differs")
            if variant != "original" and row[variant]["accepted"]:
                delta[k] = row[variant]["residual_cfo_hz"]
                corrected += 1
        track["values"] = np.asarray(track["values"]) + delta
        changes.extend(delta)
    return dict(
        points=len(ids),
        corrected=corrected,
        fallback=len(ids) - corrected,
        correction_rms_hz=float(np.sqrt(np.mean(np.array(changes) ** 2))),
        correction_quantiles_hz=np.quantile(changes, [0, 0.1, 0.5, 0.9, 1]),
    )


def run(case, method):
    source = OUTPUT / "remeasurement" / case / "measurements.json"
    data = json.loads(source.read_text())
    _, original = choose_pair(incumbents(case, method))
    base = original["c0"]
    seed = {"rows": base["rows"], "state": base["state"]}
    anchor = base["east_north_km"]
    directory = OUTPUT / "localization" / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    write(
        directory / "protocol.json",
        dict(
            case=case,
            method=method,
            variants=VARIANTS,
            measurement_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            no_GPS_or_future_TLE_in_fit=True,
            original_curved_population_and_partition_frozen=True,
            no_withholding=True,
            failed_refinements_fall_back_to_original=True,
            native_noise_sigma_hz=150,
            drift_mean_sigma_hz_s=10,
            drift_contrast_sigma_hz_s=0.5,
            warm_initialization_restored=True,
            max_iterations_per_start=24,
            geographic_grid_km=[-12.5, -6.25, 0, 6.25, 12.5],
            nominal_center=[37.906, -122.545],
            common_c0_selected_starts_and_equal_budgets_for_both_c_arms=True,
            original_blind_seed_sha256=hashlib.sha256(
                json.dumps(base, sort_keys=True).encode()
            ).hexdigest(),
            sources_sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [Path(__file__), ROOT / "tools/dsx01_glrt_remeasurement.py"]
            },
        ),
    )
    for variant in VARIANTS:
        if variant in results:
            continue
        scan = Scan(case)
        metadata = apply_measurements(scan, data["points"], variant)

        def factory(*args):
            return geometry_problem(*args, mean_sigma=10, height_sigma=0)

        fits = fit_once(scan, seed, method, anchor, problem_class=factory)
        if (
            fits["c0"]["rows"] != fits["fitted_c"]["rows"]
            or fits["c0"]["aliases"] != fits["fitted_c"]["aliases"]
        ):
            raise AssertionError("c ablation nominations or alias mismatch")
        results[variant] = dict(fits=fits, measurement_metadata=metadata)
        write(path, results)
        print(
            json.dumps(
                dict(
                    method=method,
                    variant=variant,
                    positions={a: list(f["east_north_km"]) for a, f in fits.items()},
                    corrected=metadata["corrected"],
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S05")
    parser.add_argument("--method", choices=METHODS, required=True)
    args = parser.parse_args()
    run(args.case, args.method)
