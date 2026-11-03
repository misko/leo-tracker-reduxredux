"""Test whether a single RF coefficient hides RX/band calibration differences."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from dsx01_warm_initialization import restore_radio_initialization
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from profile_dsx01_geographic_calibration import OUTPUT, incumbents
from prototype_dsx01_calibration_modes import choose_pair
from prototype_dsx01_rf_clock import rf_centres
from prototype_s01_receiver_drift import ReceiverDriftProblem


class SeparateRFFamilies(AnchoredFamilies):
    def __init__(self, *args, mode="receiver", sigma=10000.0):
        self.base_size, self.rf_factor = None, None
        super().__init__(*args)
        self.base_size = len(self.initial)
        self.rf_sigma = sigma
        self.rf_mode = mode
        if mode not in ("global", "receiver", "band") or not np.isfinite(sigma) or sigma <= 0:
            raise ValueError("known RF model and positive finite prior required")
        fitted_c = len(self.starts["beta"]) == 9
        self.rf_contrasts = (
            np.array([[-1.0], [-1.0], [1.0], [1.0]])
            if mode == "receiver"
            else np.array(
                [[-1.0, -1.0, 1.0], [-1.0, 1.0, -1.0], [1.0, -1.0, -1.0], [1.0, 1.0, 1.0]]
            )
            / 2
        )
        count = 0 if not fitted_c or mode == "global" else self.rf_contrasts.shape[1]
        self.initial = np.r_[self.initial, np.zeros(count)]
        self.lower = np.r_[self.lower, np.full(count, -5.0)]
        self.upper = np.r_[self.upper, np.full(count, 5.0)]
        centres = rf_centres(self.scan.tracks)
        self.rf_factor = np.zeros((len(self.flat_times), count))
        for i, block in zip(self.members, self.slices, strict=True):
            t = self.scan.tracks[i]
            rx = t["receiver"]
            band = int(t["channel"] > 4)
            g = 2 * (rx - 1) + band
            if count:
                self.rf_factor[block] = (
                    (t["rf_hz"] - centres[rx, band])
                    / 1e9
                    / (t["rf_hz"] / 11.5e9)
                    * self.rf_contrasts[g]
                )

    def decode(self, x):
        if self.base_size is None:
            return super().decode(x)
        state = super().decode(x[: self.base_size])
        state["rf_contrast_hz_per_ghz"] = np.asarray(x[self.base_size :]) * self.rf_sigma
        return state

    def predicted(self, x):
        f, e = super().predicted(x)
        if self.rf_factor is not None:
            f += self.rf_factor @ self.decode(x)["rf_contrast_hz_per_ghz"]
        return f, e

    def residual(self, x, *, details=False):
        value = super().residual(x, details=details)
        prior = np.asarray(x[self.base_size :])
        return (np.r_[prior, value[0]], value[1]) if details else np.r_[prior, value]


def rf_problem(*args, mode):
    return restore_radio_initialization(
        ReceiverDriftProblem(SeparateRFFamilies(*args, mode=mode), mean_sigma=10)
    )


def run(case, method):
    directory = OUTPUT / "separate_rf" / case / method
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
            incumbent_c0_source=source_name,
            common_c0_rows_aliases_geographic_starts_24_iteration_budget=True,
            all_RF_coefficients_fixed_zero_in_c0_arm=True,
            contrast_prior_sigma_hz_per_ghz=10000,
            contrast_bounds_sigma=5,
            original_global_RF_coefficient_and_four_RX_band_constants_retained=True,
            mean_and_band_contrast_drift_priors_unchanged=[10, 0.5],
            warm_radio_restoration_applied_all_models=True,
            mode_selection_if_used_is_fitted_c_objective_not_GPS=True,
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for mode in ("global", "receiver", "band"):
        if all(f"{mode}/{a}" in results for a in ("c0", "fitted_c")):
            continue

        def factory(*args, name=mode):
            p = rf_problem(*args, mode=name)
            p.problem.alias = list(seed["aliases"])
            return p

        fits = fit_once(scan, seed, method, anchor, problem_class=factory)
        for arm, fit in fits.items():
            results[f"{mode}/{arm}"] = fit
        write(path, results)
        print(
            case,
            method,
            mode,
            {
                a: (f["east_north_km"], f["state"]["rf_contrast_hz_per_ghz"])
                for a, f in fits.items()
            },
            flush=True,
        )
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument("--method", choices=METHODS, required=True)
    a = p.parse_args()
    run(a.case, a.method)
