"""Overdetermined shell-radius correction shared across different satellites."""

import argparse
import json
from collections import defaultdict

import numpy as np
from associate_merged_track_catalogue import write
from build_dsx01_causal_forecast import OUTPUT
from compare_dsx01_retention_localization import METHODS, Scan
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from prototype_dsx01_mean_motion import reference_motion_basis
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_s01_receiver_drift import ReceiverDriftProblem
from sgp4.api import Satrec


class ShellFamilies(AnchoredFamilies):
    def __init__(self, *args, sigma_km=0.3):
        self.base_size, self.shell_derivatives = None, None
        super().__init__(*args)
        self.base_size = len(self.initial)
        self.shell_sigma = sigma_km
        groups = defaultdict(list)
        satellites = {}
        for j in self.labels:
            satellite = Satrec.twoline2rv(
                *self.scan.elements[str(int(self.scan.norads[j]))]["lines"]
            )
            satellites[j] = satellite
            motion = satellite.no_kozai * 1440 / (2 * np.pi)
            groups[(round(np.rad2deg(satellite.inclo)), round(motion, 1))].append(j)
        # A one-satellite group cannot claim to calibrate a shared shell error.
        self.shell_groups = {str(k): v for k, v in groups.items() if len(v) >= 2}
        self.shell_names = sorted(self.shell_groups)
        self.shell_derivatives = {}
        for name in self.shell_names:
            for j in self.shell_groups[name]:
                sat = satellites[j]
                radius = float(
                    np.mean(np.linalg.norm(self.sky["position_km"][self.local_j[j]], axis=1))
                )
                motion = sat.no_kozai * 1440 / (2 * np.pi)
                dp, dv = reference_motion_basis(self.scan, j)
                dn = -1.5 * motion / radius
                self.shell_derivatives[j] = (name, dp * dn, dv * dn)
        self.initial = np.r_[self.initial, np.zeros(len(self.shell_names))]
        self.lower = np.r_[self.lower, np.full(len(self.shell_names), -5.0)]
        self.upper = np.r_[self.upper, np.full(len(self.shell_names), 5.0)]

    def decode(self, x):
        if self.base_size is None:
            return super().decode(x)
        state = super().decode(x[: self.base_size])
        state["shell_radial_km"] = dict(
            zip(self.shell_names, np.asarray(x[self.base_size :]) * self.shell_sigma, strict=True)
        )
        return state

    def orbit_sky(self, state):
        sky = super().orbit_sky(state)
        if self.shell_derivatives is None:
            return sky
        sky = {k: v.copy() for k, v in sky.items()}
        for j, (name, dp, dv) in self.shell_derivatives.items():
            amount = state["shell_radial_km"][name]
            k = self.local_j[j]
            sky["position_km"][k] += amount * dp
            sky["velocity_km_s"][k] += amount * dv
        return sky

    def residual(self, x, *, details=False):
        value = super().residual(x, details=details)
        prior = np.asarray(x[self.base_size :])
        return (np.r_[prior, value[0]], value[1]) if details else np.r_[prior, value]


def shell_problem(*args):
    return ReceiverDriftProblem(ShellFamilies(*args), mean_sigma=10)


def run(case, method, refreshed=False):
    directory = OUTPUT / "shell_radius" / case / method / ("refreshed" if refreshed else "original")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    if path.exists():
        return json.loads(path.read_text())
    if refreshed:
        source = (
            OUTPUT.parent
            / "2026_10_18_dsx01_receiver_identity"
            / case
            / method
            / "mean_10_endpoints.json"
        )
        seed = json.loads(source.read_text())["c0"]
        anchor = seed["east_north_km"]
    else:
        source = SOURCE / case / f"{method}_center.json"
        seed = json.loads(source.read_text())
        anchor = (0, 0)
    scan = Scan(case)
    nominal = shell_problem(scan, seed, method, False, anchor)
    locked = seed.get("aliases", nominal.alias)

    def factory(*args):
        p = shell_problem(*args)
        p.problem.alias = list(locked)
        return p

    write(
        directory / "protocol.json",
        dict(
            no_GPS_or_future_elements=True,
            blind_source=str(source),
            shell_groups={
                k: [int(scan.norads[j]) for j in v] for k, v in nominal.shell_groups.items()
            },
            radius_prior_sigma_km=0.3,
            bounds_sigma=5,
            minimum_distinct_satellites=2,
            same_c0_nominations_aliases_and_grid_budget_for_both_c_arms=True,
        ),
    )
    fits = fit_once(scan, seed, method, anchor, problem_class=factory)
    write(path, fits)
    print(
        case,
        method,
        refreshed,
        {a: (f["east_north_km"], f["state"]["shell_radial_km"]) for a, f in fits.items()},
        flush=True,
    )
    return fits


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S05")
    p.add_argument("--method", choices=METHODS, default="receiver_smooth")
    p.add_argument("--refreshed", action="store_true")
    a = p.parse_args()
    run(a.case, a.method, a.refreshed)
