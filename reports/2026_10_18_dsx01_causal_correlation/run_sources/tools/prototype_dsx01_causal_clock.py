"""Separate orbital phase uncertainty from a shared satellite frequency bias."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from dsx01_warm_initialization import restore_radio_initialization
from iterate_dsx01_position_nominations import fit_once
from profile_dsx01_geographic_calibration import OUTPUT, incumbents
from prototype_dsx01_calibration_modes import choose_pair
from prototype_dsx01_orbit_marginal import marginal_problem
from prototype_dsx01_receiver_phase import PhaseScaleProblem


class CausalPhaseProblem(PhaseScaleProblem):
    def __init__(self, problem):
        super().__init__(problem, factor=1.0)
        self.factor = (
            np.maximum(0.1, problem.scan.sky["phase_sigma_s"][problem.labels])
            / problem.scan.sigma[problem.labels]
        )


def clock_problem(*args, phase_mode, clock_sigma):
    p = restore_radio_initialization(
        marginal_problem(
            *args,
            kind="none",
            likelihood="student",
            curve_bias_sigma=1000.0,
            satellite_bias_sigma=clock_sigma,
        )
    )
    return CausalPhaseProblem(p) if phase_mode == "causal" else p


def lock_aliases(problem, aliases):
    while hasattr(problem, "problem"):
        problem = problem.problem
    problem.alias = list(aliases)


def run(case, method):
    directory = OUTPUT / "satellite_clock" / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    source_name, pair = choose_pair(incumbents(case, method))
    seed = pair["c0"]
    anchor = seed["east_north_km"]
    scan = Scan(case)
    write(
        directory / "protocol.json",
        dict(
            no_GPS_or_future_TLE_input=True,
            inherited_completed_blind_grid=True,
            input_c0_source=source_name,
            same_raw_curved_rows_aliases_and_input_state_in_all_controls=True,
            student_family_nu=4,
            curve_constant_sigma_hz=1000,
            satellite_clock_sigmas_reference_hz=[0, 5000, 20000],
            two_phase_prior_controls=["original_floor1", "original_causal_sigma_min_.1"],
            satellite_clock_is_integrated_with_covariance_volume_penalty=True,
            no_additional_fitted_clock_coordinates=True,
            common_c0_starts_and_24_iteration_budget_for_c_arms=True,
            no_noise_or_position_gate_relaxed=True,
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for phase in ("floor", "causal"):
        for sigma in (0.0, 5000.0, 20000.0):
            name = f"{phase}_clock{sigma:g}"
            if all(f"{name}/{a}" in results for a in ("c0", "fitted_c")):
                continue

            def factory(*args, ph=phase, s=sigma):
                p = clock_problem(*args, phase_mode=ph, clock_sigma=s)
                lock_aliases(p, seed["aliases"])
                return p

            fits = fit_once(scan, seed, method, anchor, problem_class=factory)
            for arm, fit in fits.items():
                results[f"{name}/{arm}"] = fit
            write(path, results)
            print(case, method, name, {a: f["east_north_km"] for a, f in fits.items()}, flush=True)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument("--method", choices=METHODS, default="receiver_smooth")
    a = p.parse_args()
    run(a.case, a.method)
