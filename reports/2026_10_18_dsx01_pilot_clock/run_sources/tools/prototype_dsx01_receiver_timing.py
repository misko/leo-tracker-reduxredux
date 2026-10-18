"""Relative receiver timestamp offset, distinct from a shared orbital phase."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from probe_dsx01_scan_influence import OUTPUT
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_s01_receiver_drift import ReceiverDriftProblem


class TimingFamilies(AnchoredFamilies):
    def __init__(self, scan, seed, method, fitted_c, anchor, *, sigma=0.1):
        if not np.isfinite(sigma) or sigma <= 0:
            raise ValueError("positive finite timing sigma required")
        self.base_size = None
        self.timing_parameters, self.timing_sigma = 1, sigma
        super().__init__(scan, seed, method, fitted_c, anchor)
        self.base_size = len(self.initial)
        self.initial = np.r_[self.initial, 0.0]
        self.lower = np.r_[self.lower, -3.0]
        self.upper = np.r_[self.upper, 3.0]
        self.receiver_sign = np.concatenate(
            [
                np.full(
                    len(scan.tracks[i]["times"]), 1.0 if scan.tracks[i]["receiver"] == 2 else -1.0
                )
                for i in self.members
            ]
        )

    def decode(self, x):
        if self.base_size is None:
            return super().decode(x)
        state = super().decode(x[: self.base_size])
        state["rx_time_difference_s"] = float(self.timing_sigma * x[-1])
        return state

    def observation_times(self, state):
        delta = state.get("rx_time_difference_s", 0.0)
        return self.flat_times if delta == 0 else self.flat_times + self.receiver_sign * delta / 2

    def residual(self, x, *, details=False):
        result = super().residual(x, details=details)
        return (np.r_[result[0], x[-1]], result[1]) if details else np.r_[result, x[-1]]


def timing_problem(*args, sigma):
    return ReceiverDriftProblem(TimingFamilies(*args, sigma=sigma), mean_sigma=10)


def run(case, method="shared_phase", sigmas=(0.1, 0.5)):
    directory = OUTPUT / "timing" / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    source = SOURCE / case / f"{method}_center.json"
    seed = json.loads(source.read_text())
    scan = Scan(case)
    write(
        directory / "protocol.json",
        dict(
            no_reference_GPS_or_oracle_initialization=True,
            one_relative_timestamp_coordinate_with_mean_UTC_fixed=True,
            RX1_UTC_shift="-delta/2",
            RX2_UTC_shift="+delta/2",
            true_UTC_shift_not_a_receiver_specific_orbital_phase=True,
            timing_sigma_s=sigmas,
            timing_bounds_sigma=3,
            original_curved_points_nominations_aliases_and_c_arms_budgets_match=True,
            common_RX_drift_sigma_hz_s=10,
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for sigma in sigmas:
        key = f"time_sigma_{sigma:g}"
        if all(f"{key}/{a}" in results for a in ("c0", "fitted_c")):
            continue

        def factory(*args, s=sigma):
            return timing_problem(*args, sigma=s)

        fits = fit_once(scan, seed, method, (0, 0), problem_class=factory)
        for a, f in fits.items():
            results[f"{key}/{a}"] = f
        write(path, results)
        print(
            json.dumps(
                dict(
                    case=case,
                    method=method,
                    sigma=sigma,
                    positions={a: f["east_north_km"].tolist() for a, f in fits.items()},
                    relative_time_s={
                        a: f["state"]["rx_time_difference_s"] for a, f in fits.items()
                    },
                )
            ),
            flush=True,
        )
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S01")
    run(p.parse_args().case)
