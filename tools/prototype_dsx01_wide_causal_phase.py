"""Combine wide receiver means with the original causal per-satellite phase scales."""

import argparse
import hashlib
import json
from pathlib import Path

from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from dsx01_warm_initialization import restore_radio_initialization
from iterate_dsx01_position_nominations import fit_once
from profile_dsx01_geographic_calibration import OUTPUT
from prototype_dsx01_phase_priors import CausalPhaseFamilies
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_s01_receiver_drift import ReceiverDriftProblem


def causal_problem(*args, mode):
    return restore_radio_initialization(
        ReceiverDriftProblem(CausalPhaseFamilies(*args, mode=mode), mean_sigma=10)
    )


def run(case, method):
    directory = OUTPUT / "causal_phase" / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    source = SOURCE / case / f"{method}_center.json"
    seed = json.loads(source.read_text())
    scan = Scan(case)
    write(
        directory / "protocol.json",
        dict(
            no_GPS_or_future_TLE_input=True,
            original_center_nominations_and_curved_population=True,
            original_causal_phase_sigma_clipped_minimum_s=0.1,
            control_phase_sigma_floor_s=1,
            receiver_mean_contrast_sigmas_hz_s=[10, 0.5],
            phase_bounds_s=[-15, 15],
            c0_fitted_c_common_starts_nominations_aliases_and_24_iteration_budget=True,
            causal_heavy_tail_penalty="3*log(1+(phase/causal_sigma)^2/3)",
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for mode in ("floor1", "causal_gaussian", "causal_student"):
        if all(f"{mode}/{a}" in results for a in ("c0", "fitted_c")):
            continue

        def factory(*args, name=mode):
            return causal_problem(*args, mode=name)

        fits = fit_once(scan, seed, method, (0, 0), problem_class=factory)
        for arm, fit in fits.items():
            results[f"{mode}/{arm}"] = fit
        write(path, results)
        print(case, method, mode, {a: f["east_north_km"] for a, f in fits.items()}, flush=True)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument("--method", choices=METHODS, required=True)
    a = p.parse_args()
    run(a.case, a.method)
