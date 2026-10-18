"""Isolate warm-start restoration with identical observations and local anchors."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from dsx01_warm_initialization import restore_radio_initialization
from profile_dsx01_geographic_calibration import OUTPUT, incumbents
from prototype_dsx01_calibration_modes import choose_pair
from prototype_dsx01_continuous_position import latlon
from prototype_dsx01_receiver_geometry import geometry_problem

from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton


def run(case, method):
    directory = OUTPUT / "warm_start_ablation" / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    origin, source = choose_pair(incumbents(case, method))
    seed = source["c0"]
    anchor = seed["east_north_km"]
    scan = Scan(case)
    write(
        directory / "protocol.json",
        dict(
            no_GPS_or_future_TLE_input=True,
            inherited_completed_blind_grid=True,
            same_c0_incumbent_anchor_and_input_state_in_all_four_runs=True,
            incumbent=origin,
            observations_labels_aliases_priors_final_bounds_24_iteration_budget_matched=True,
            only_four_initial_receiver_mean_contrast_coordinates_change=True,
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for variant in ("legacy_clipped", "restored"):
        for arm in ("c0", "fitted_c"):
            key = f"{variant}/{arm}"
            if key in results:
                continue
            p = geometry_problem(
                scan, seed, method, arm == "fitted_c", anchor, mean_sigma=10, height_sigma=0
            )
            p.problem.alias = list(seed["aliases"])
            if variant == "restored":
                restore_radio_initialization(p)
            mark = time.monotonic()
            fit = bounded_gauss_newton(p.residual, p.initial, p.lower, p.upper, iterations=24)
            fit["start_east_north_km"] = anchor
            x = fit["parameters"]
            penalty = len(x) * np.log(len(p.flat_times))
            results[key] = dict(
                latitude_deg=latlon(x[:2])[0],
                longitude_deg=latlon(x[:2])[1],
                east_north_km=x[:2],
                frequency_prior_score=fit["score"],
                complexity_penalty=penalty,
                score=fit["score"] + penalty,
                state=p.decode(x),
                rows=p.rows,
                aliases=p.alias,
                fits=[fit],
                starts=[anchor],
                anchor=anchor,
                seconds=time.monotonic() - mark,
                initial_band_rates_hz_s=p.decode(p.initial)["beta"][4:8] / 150,
            )
            write(path, results)
            print(case, method, key, x[:2], fit["score"], fit["evaluations"], flush=True)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument("--method", choices=METHODS, required=True)
    a = p.parse_args()
    run(a.case, a.method)
