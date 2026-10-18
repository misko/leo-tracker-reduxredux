"""Compare satellite-wide and satellite/channel clocks shared across receivers."""

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
from prototype_dsx01_causal_clock import lock_aliases
from prototype_dsx01_orbit_marginal import MarginalFamilies
from prototype_s01_receiver_drift import ReceiverDriftProblem


class ChannelClockFamilies(MarginalFamilies):
    def __init__(self, *args, grouping="channel", rate_sigma=1.0):
        if (
            grouping not in ("satellite", "channel")
            or not np.isfinite(rate_sigma)
            or rate_sigma < 0
        ):
            raise ValueError("known grouping and finite nonnegative rate scale required")
        super().__init__(*args, kind="none", likelihood="student", curve_bias_sigma=1000.0)
        self.clock_grouping, self.rate_sigma = grouping, rate_sigma
        self.clock_modes = np.zeros((len(self.flat_times), 2 if grouping == "satellite" else 16))
        for i, block in zip(self.members, self.slices, strict=True):
            track = self.scan.tracks[i]
            k = 0 if grouping == "satellite" else 2 * (track["channel"] - 1)
            self.clock_modes[block, k] = 5000.0
            self.clock_modes[block, k + 1] = rate_sigma * (track["times"] - 150)

    def frequency_modes(self, x, state):
        return self.clock_modes

    def predicted(self, x):
        if not getattr(self, "ready", False):
            return AnchoredFamilies.predicted(self, x)
        _, _, coefficients, _, f, e, modes = self.calculate(x)
        for j, a in coefficients.items():
            use = self.flat_labels == self.local_j[j]
            f[use] += modes[use] @ a
        return f, e

    def association_state(self, x):
        _, statistics, coefficients, state, *_ = self.calculate(x)
        state["transmit_clock_coefficients"] = {j: a for j, a in coefficients.items()}
        state["transmit_clock_grouping"] = self.clock_grouping
        state["marginal_signal_probability"] = {
            j: r["signal_probability"] for j, r in statistics.items()
        }
        return state


def channel_problem(*args, grouping, rate_sigma):
    return restore_radio_initialization(
        ReceiverDriftProblem(
            ChannelClockFamilies(*args, grouping=grouping, rate_sigma=rate_sigma), mean_sigma=10
        )
    )


def run(case, method):
    directory = OUTPUT / "channel_clock" / case / method
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
            constant_clock_sigma_reference_hz=5000,
            rate_sigmas_hz_s=[0, 1, 5],
            student_scale_hz=150,
            nu=4,
            curve_constant_sigma_hz=1000,
            receiver_means_and_band_contrasts_unchanged=[10, 0.5],
            satellite_phase_and_orbit_model_remain_shared_across_channels=True,
            covariance_volume_penalty_for_clock_uncertainty_included=True,
            no_new_fitted_clock_coordinates=True,
            same_original_curved_rows_aliases_and_c0_selected_grid_starts_for_c_arms=True,
            same_24_iteration_budget_per_start_for_both_c_arms=True,
            shared_channel_clock_is_hypothesis_not_verified_transmitter_correction=True,
            source="https://www.ion.org/publications/abstract.cfm?articleID=20898",
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for grouping in ("satellite", "channel"):
        for rate in (0.0, 1.0, 5.0):
            name = f"{grouping}_rate{rate:g}"
            if all(f"{name}/{a}" in results for a in ("c0", "fitted_c")):
                continue

            def factory(*args, g=grouping, r=rate):
                p = channel_problem(*args, grouping=g, rate_sigma=r)
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
