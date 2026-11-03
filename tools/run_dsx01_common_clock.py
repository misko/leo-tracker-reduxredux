"""Matched zero-clock/reconstructed-clock continuations of completed blind fits."""

import argparse
import hashlib
import json

from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from dsx01_clock_transfer_models import transfer_problem
from dsx01_common_clock import CommonPairClock, CommonParentClock
from dsx01_warm_initialization import restore_radio_initialization
from iterate_dsx01_position_nominations import fit_once
from profile_dsx01_geographic_calibration import geometry_problem
from prototype_dsx01_causal_clock import lock_aliases
from prototype_dsx01_remeasured_position import apply_measurements
from prototype_s01_receiver_drift import ReceiverDriftProblem
from run_dsx01_clock_transfer import MEASUREMENTS, OUTPUT, check_pair, measurement_path, read_pairs


def clock_problem(*args, kind, clock, pairs, enabled):
    if kind == "parents":
        p = (
            restore_radio_initialization(
                ReceiverDriftProblem(CommonParentClock(*args, clock=clock), mean_sigma=10)
            )
            if enabled
            else geometry_problem(*args, mean_sigma=10, height_sigma=0)
        )
    elif kind == "tight_pairs":
        p = (
            CommonPairClock(
                *args, clock=clock, provided_pairs=pairs, phase_mode="causal", use_pairs=True
            )
            if enabled
            else transfer_problem(*args, pairs=pairs, mode="tight_causal")
        )
    else:
        raise ValueError("unknown matched clock control")
    return p


def run(case):
    method = "receiver_smooth"
    source = measurement_path(case)
    points = json.loads(source.read_text())["points"]
    clock = json.loads((OUTPUT / "clock_brackets.json").read_text())[case]
    pairs, _ = read_pairs(case)
    for kind in ["parents", "tight_pairs"]:
        baseline = (
            (OUTPUT / "parents" / case / method / "endpoints.json")
            if kind == "parents"
            else (OUTPUT / "priors" / case / "tight_causal" / "selected.json")
        )
        inherited = json.loads(baseline.read_text())
        directory = OUTPUT / "common_clock" / case / kind
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "endpoints.json"
        results = json.loads(path.read_text()) if path.exists() else {}
        write(
            directory / "protocol.json",
            dict(
                case=case,
                method=method,
                kind=kind,
                inherited_blind_endpoint_source=str(baseline),
                source_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
                zero_clock_control_receives_same_inherited_state_anchor_and_24_iteration_budget=True,
                common_UTC_prior=clock,
                no_GPS_or_future_TLE_input=True,
                time_shift_changes_orbit_and_Earth_rotation_but_not_elapsed_hardware_basis=True,
                common_clock_is_one_added_parameter_and_receives_parameter_count_penalty=True,
                matched_c_arms_same_data_nominations_aliases_starts_and_budgets=True,
            ),
        )
        for variant in MEASUREMENTS:
            scan = Scan(case)
            apply_measurements(scan, points, variant)
            seed = inherited[variant]["fits"]["c0"]
            anchor = seed["east_north_km"]
            for enabled in [False, True]:
                key = f"{variant}/clock{int(enabled)}"
                if key in results:
                    continue

                def factory(*args, on=enabled, category=kind, fixed_aliases=seed["aliases"]):
                    p = clock_problem(*args, kind=category, clock=clock, pairs=pairs, enabled=on)
                    lock_aliases(p, fixed_aliases)
                    return p

                fits = fit_once(scan, seed, method, anchor, problem_class=factory)
                check_pair(fits)
                results[key] = dict(fits=fits)
                write(path, results)
                print(
                    json.dumps(
                        dict(
                            case=case,
                            kind=kind,
                            measurement=variant,
                            clock=enabled,
                            positions={a: list(f["east_north_km"]) for a, f in fits.items()},
                            shifts={
                                a: f["state"].get("common_utc_shift_s", 0) for a, f in fits.items()
                            },
                        )
                    ),
                    flush=True,
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    run(parser.parse_args().case)
