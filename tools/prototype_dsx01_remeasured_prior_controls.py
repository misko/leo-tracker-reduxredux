"""Cross existing causal-prior controls with radio-only CFO remeasurements."""

import argparse
import hashlib
import json
from pathlib import Path

from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from iterate_dsx01_position_nominations import fit_once
from profile_dsx01_geographic_calibration import incumbents
from prototype_dsx01_calibration_modes import choose_pair
from prototype_dsx01_causal_clock import clock_problem, lock_aliases
from prototype_dsx01_phase_priors import CausalPhaseFamilies
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_dsx01_remeasured_position import OUTPUT, VARIANTS, apply_measurements
from prototype_dsx01_wide_causal_phase import causal_problem


def prior_problem(*args, mode):
    if mode == "tight_causal":
        return CausalPhaseFamilies(*args, mode="causal_gaussian")
    if mode == "wide_causal":
        return causal_problem(*args, mode="causal_gaussian")
    if mode == "wide_family_causal":
        return clock_problem(*args, phase_mode="causal", clock_sigma=0)
    raise ValueError("unknown prior control")


def run(case, method, mode):
    source = OUTPUT / "remeasurement" / case / "measurements.json"
    points = json.loads(source.read_text())["points"]
    if mode == "wide_family_causal":
        _, pair = choose_pair(incumbents(case, method))
        seed, anchor = pair["c0"], pair["c0"]["east_north_km"]
    else:
        seed = json.loads((SOURCE / case / f"{method}_center.json").read_text())
        anchor = [0, 0]
    directory = OUTPUT / "prior_controls" / case / mode / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    write(
        directory / "protocol.json",
        dict(
            case=case,
            method=method,
            mode=mode,
            variants=VARIANTS,
            same_original_curved_points_no_withholding=True,
            same_latest_causal_candidate_bank=True,
            no_GPS_or_future_TLE_input=True,
            causal_phase_sigma_floor_s=0.1,
            phase_bound_s=15,
            tight_control_has_original_four_independent_sigma_halfHz_per_s_bound_oneHz_per_s=True,
            wide_controls_have_RX_mean_contrast_sigmas_hz_s=[10, 0.5],
            same_c0_selected_starts_and_24_iterations_per_start_for_both_c_arms=True,
            native_white_noise_sigma_hz=150,
            measurement_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            seed_sha256=hashlib.sha256(json.dumps(seed, sort_keys=True).encode()).hexdigest(),
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for variant in VARIANTS:
        if variant in results:
            continue
        scan = Scan(case)
        metadata = apply_measurements(scan, points, variant)

        def factory(*args):
            problem = prior_problem(*args, mode=mode)
            if mode == "wide_family_causal":
                lock_aliases(problem, seed["aliases"])
            return problem

        fits = fit_once(scan, seed, method, anchor, problem_class=factory)
        if (
            fits["c0"]["rows"] != fits["fitted_c"]["rows"]
            or fits["c0"]["aliases"] != fits["fitted_c"]["aliases"]
        ):
            raise AssertionError("c arms differ in nominations or aliases")
        results[variant] = dict(fits=fits, measurement_metadata=metadata)
        write(path, results)
        print(
            json.dumps(
                dict(
                    method=method,
                    mode=mode,
                    variant=variant,
                    positions={a: list(f["east_north_km"]) for a, f in fits.items()},
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", default="DSX01-S05")
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument(
        "--mode", choices=["tight_causal", "wide_causal", "wide_family_causal"], required=True
    )
    a = parser.parse_args()
    run(a.case, a.method, a.mode)
