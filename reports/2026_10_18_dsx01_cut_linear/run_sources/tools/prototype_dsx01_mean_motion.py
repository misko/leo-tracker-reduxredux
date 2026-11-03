"""Shared orbital mean-motion uncertainty after common-RX drift relaxation."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from fit_s01_69333_tle_parameter import perturb
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from prototype_dsx01_receiver_geometry import OUTPUT as BASELINE
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_s01_receiver_drift import ReceiverDriftProblem
from sgp4.api import WGS72, Satrec

from leo.sky.propagation import ElementSetCatalogue

OUTPUT = ROOT / "reports/2026_10_18_dsx01_mean_motion"


def reference_motion_satellite(base, delta, elapsed_days):
    """Vary orbital size/rate while keeping mean longitude near scan midpoint.

    Without this coordinate choice, a mean-motion perturbation accumulates a
    large phase change from the TLE epoch; linearizing then cancelling it with
    phase can leave an artificial second-order radial displacement.
    """
    motion = perturb(base, "mean_motion_rev_day", delta)
    sat = Satrec()
    sat.sgp4init(
        WGS72,
        motion.operationmode,
        motion.satnum,
        (motion.jdsatepoch - 2433281.5) + motion.jdsatepochF,
        motion.bstar,
        motion.ndot,
        motion.nddot,
        motion.ecco,
        motion.argpo,
        motion.inclo,
        motion.mo - 2 * np.pi * delta * elapsed_days,
        motion.no_kozai,
        motion.nodeo,
    )
    sat.jdsatepoch, sat.jdsatepochF = motion.jdsatepoch, motion.jdsatepochF
    return sat


def reference_motion_basis(scan, j):
    if not hasattr(scan, "reference_motion_derivatives"):
        scan.reference_motion_derivatives = {}
    if j not in scan.reference_motion_derivatives:
        n = int(scan.norads[j])
        sat = Satrec.twoline2rv(*scan.elements[str(n)]["lines"])
        elapsed = (
            (scan.receipt["origin_utc_ns"] / 1e9 + 150) / 86400
            + 2440587.5
            - sat.jdsatepoch
            - sat.jdsatepochF
        )
        cat = ElementSetCatalogue(
            (str(n), str(n)),
            (n, n),
            tuple(reference_motion_satellite(sat, d, elapsed) for d in (0.001, -0.001)),
        )
        p, v, good = ecef_states(cat, scan.receipt["origin_utc_ns"], scan.sky["time_s"])
        if not good.all():
            raise ValueError("reference-aligned mean-motion propagation failed")
        scan.reference_motion_derivatives[j] = ((p[0] - p[1]) / 0.002, (v[0] - v[1]) / 0.002)
    return scan.reference_motion_derivatives[j]


def motion_basis(scan, j):
    if not hasattr(scan, "mean_motion_derivatives"):
        scan.mean_motion_derivatives = {}
    if j not in scan.mean_motion_derivatives:
        n = int(scan.norads[j])
        sat = Satrec.twoline2rv(*scan.elements[str(n)]["lines"])
        cat = ElementSetCatalogue(
            (str(n), str(n)),
            (n, n),
            tuple(perturb(sat, "mean_motion_rev_day", d) for d in (0.001, -0.001)),
        )
        p, v, good = ecef_states(cat, scan.receipt["origin_utc_ns"], scan.sky["time_s"])
        if not good.all():
            raise ValueError("mean-motion tangent propagation failed")
        scan.mean_motion_derivatives[j] = ((p[0] - p[1]) / 0.002, (v[0] - v[1]) / 0.002)
    return scan.mean_motion_derivatives[j]


class MotionFamilies(AnchoredFamilies):
    def __init__(
        self, scan, seed, method, fitted_c, anchor, *, sigma=0.0015, basis=None, basis_provider=None
    ):
        if not np.isfinite(sigma) or sigma <= 0:
            raise ValueError("positive finite orbital mean-motion scale required")
        self.base_size, self.motion_basis = None, {}
        super().__init__(scan, seed, method, fitted_c, anchor)
        self.base_size, self.motion_sigma = len(self.initial), sigma
        self.motion_labels = []
        for j in self.labels:
            owners = {
                (scan.tracks[i]["receiver"], scan.tracks[i]["channel"])
                for i, r in zip(self.members, self.rows, strict=True)
                if r["candidate_index"] == j
            }
            if len(owners) >= 2:
                self.motion_labels.append(j)
                self.motion_basis[j] = (
                    basis[j] if basis is not None else (basis_provider or motion_basis)(scan, j)
                )
        self.initial = np.r_[self.initial, np.zeros(len(self.motion_labels))]
        self.lower = np.r_[self.lower, np.full(len(self.motion_labels), -3.0)]
        self.upper = np.r_[self.upper, np.full(len(self.motion_labels), 3.0)]

    def decode(self, x):
        if self.base_size is None:
            return super().decode(x)
        state = super().decode(x[: self.base_size])
        state["mean_motion_offsets_rev_day"] = dict(
            zip(
                self.motion_labels, self.motion_sigma * np.asarray(x[self.base_size :]), strict=True
            )
        )
        return state

    def orbit_sky(self, state):
        sky = super().orbit_sky(state)
        if not self.motion_basis:
            return sky
        sky = {k: v.copy() for k, v in sky.items()}
        for j, value in state["mean_motion_offsets_rev_day"].items():
            k = self.local_j[j]
            dp, dv = self.motion_basis[j]
            sky["position_km"][k] += value * dp
            sky["velocity_km_s"][k] += value * dv
        return sky

    def residual(self, x, *, details=False):
        result = super().residual(x, details=details)
        prior = x[self.base_size :]
        return (np.r_[result[0], prior], result[1]) if details else np.r_[result, prior]


def run(case, method, *, mean=10.0, sigmas=(0.0, 0.0015, 0.005), reference_aligned=False):
    directory = (OUTPUT / "reference_aligned" if reference_aligned else OUTPUT) / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    seed_path = SOURCE / case / f"{method}_center.json"
    seed = json.loads(seed_path.read_text())
    write(
        directory / "protocol.json",
        dict(
            no_reference_GPS_or_oracle_states=True,
            parameter="SGP4 mean_motion_rev_day",
            prior_sigmas_rev_day=sigmas,
            zero_mean_prior=True,
            coefficient_bounds_in_prior_sigma=3,
            curved_RX_channel_owners_at_least_two=True,
            tangent_derivative_step_rev_day=0.001,
            same_curved_points_nominations_aliases_grid_and_iterations_for_c_arms=True,
            common_RX_mean_sigma_hz_s=mean,
            band_contrast_sigma_hz_s=0.5,
            seed_sha256=hashlib.sha256(seed_path.read_bytes()).hexdigest(),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            tangent_not_exact_propagation=True,
            mean_longitude_held_at_scan_midpoint=reference_aligned,
        ),
    )
    scan = None
    for sigma in sigmas:
        name = f"mean_{mean:g}_motion_{sigma:g}"
        if all(f"{name}/{a}" in results for a in ("c0", "fitted_c")):
            continue
        if sigma == 0:
            old_path = BASELINE / case / method / "endpoints.json"
            old = json.loads(old_path.read_text())
            for a in ("c0", "fitted_c"):
                results[f"{name}/{a}"] = dict(
                    old[f"mean_{mean:g}_height_0/{a}"], reused_from=str(old_path.relative_to(ROOT))
                )
            write(path, results)
            continue
        scan = Scan(case) if scan is None else scan

        def factory(scan, seed, method, fitted_c, anchor, scale=sigma):
            return ReceiverDriftProblem(
                MotionFamilies(
                    scan,
                    seed,
                    method,
                    fitted_c,
                    anchor,
                    sigma=scale,
                    basis_provider=reference_motion_basis if reference_aligned else None,
                ),
                mean_sigma=mean,
            )

        fits = fit_once(scan, seed, method, (0, 0), problem_class=factory)
        for a, f in fits.items():
            results[f"{name}/{a}"] = f
        write(path, results)
        print(
            json.dumps(
                dict(
                    case=case,
                    method=method,
                    variant=name,
                    positions={a: f["east_north_km"].tolist() for a, f in fits.items()},
                )
            ),
            flush=True,
        )
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S01")
    p.add_argument("--method", choices=METHODS, default="shared_phase")
    p.add_argument("--reference-aligned", action="store_true")
    a = p.parse_args()
    run(a.case, a.method, reference_aligned=a.reference_aligned)
