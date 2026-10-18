"""Isolate RX prior width with the successful tight control's blind nominations."""

import json

from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from iterate_dsx01_position_nominations import fit_once
from prototype_dsx01_causal_clock import lock_aliases
from prototype_dsx01_pair_difference import pair_problem
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_dsx01_remeasured_position import OUTPUT, apply_measurements


def run():
    case, method = "DSX01-S05", "receiver_smooth"
    seed = json.loads((SOURCE / case / f"{method}_center.json").read_text())
    pairs = json.loads(
        (
            OUTPUT.parent
            / "2026_10_18_dsx01_geographic_calibration/frame_coherent_calibration.json"
        ).read_text()
    )[case]["pairs"]
    points = json.loads((OUTPUT / "remeasurement" / case / "measurements.json").read_text())[
        "points"
    ]
    tight_path = OUTPUT / "pair_difference" / case / "tight_causal" / method / "endpoints.json"
    tight = json.loads(tight_path.read_text())
    directory = OUTPUT / "pair_prior_control" / case / method
    directory.mkdir(parents=True, exist_ok=True)
    write(
        directory / "protocol.json",
        dict(
            case=case,
            method=method,
            variants=["original", "glrt64", "glrt300"],
            tight_control_path=str(tight_path),
            same_center_seed_rows_aliases_initial_physical_state=True,
            only_RX_drift_prior_coordinates_scales_and_bounds_change=True,
            both_phase_priors_are_original_causal_Gaussian=True,
            matched_c_arms_same_starts_and_24_iteration_budget=True,
            no_GPS_or_future_TLE_in_fit=True,
        ),
    )
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    for variant in ["original", "glrt64", "glrt300"]:
        if variant in results:
            continue
        scan = Scan(case)
        meta = apply_measurements(scan, points, variant)
        aliases = tight[f"{variant}/pairs1"]["fits"]["c0"]["aliases"]

        def factory(*args, fixed_aliases=aliases):
            p = pair_problem(*args, pairs=pairs, mode="wide_causal", use_pairs=True)
            lock_aliases(p, fixed_aliases)
            return p

        fits = fit_once(scan, seed, method, [0, 0], problem_class=factory)
        for arm in ["c0", "fitted_c"]:
            comparison = tight[f"{variant}/pairs1"]["fits"][arm]
            assert (
                fits[arm]["rows"] == comparison["rows"]
                and fits[arm]["aliases"] == comparison["aliases"]
            )
            assert [r["east_north_km"] for r in fits[arm]["starts"]] == [
                r["east_north_km"] for r in comparison["starts"]
            ]
        results[variant] = dict(
            fits=fits,
            measurement_metadata=meta,
            pair_metadata=factory(scan, seed, method, False, [0, 0]).pair_metadata,
        )
        write(path, results)
        print(variant, {a: list(f["east_north_km"]) for a, f in fits.items()}, flush=True)


if __name__ == "__main__":
    run()
