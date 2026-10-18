"""Shared causal orbit-shape correction directions beyond a constant phase.

The latest causal TLE remains the mean prediction. A previous causal TLE,
aligned in orbital phase, supplies a zero-mean Gaussian error direction shared
by a satellite's curved tracks. This is an uncertainty hypothesis, not orbit
truth or a fitted replacement TLE.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import AnchoredFamilies, fit_once
from prototype_dsx01_continuous_position import CENTER, GRID, latlon

from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S, phase_shifted_states
from leo.sky.propagation import ElementSetCatalogue, parse_element_sets

OUTPUT = ROOT / "reports/2026_10_18_s01_causal_shape"
SOURCE = ROOT / "reports/2026_10_18_dsx01_nomination_iteration/seeds_32/DSX01-S01"
PREVIOUS = (
    ROOT
    / "reports/2026_10_17_ds22_physical_model_revision/orbit_disagreement/DSX01-S01/previous.tle"
)


def previous_bank(scan, labels):
    expected = scan.receipt["previous_tle_sha256"]
    if hashlib.sha256(PREVIOUS.read_bytes()).hexdigest() != expected:
        raise ValueError("previous causal TLE bytes differ from the original prior receipt")
    if not hasattr(scan, "previous_shape_cache"):
        scan.previous_shape_cache = {}
    key = tuple(labels)
    if key in scan.previous_shape_cache:
        return scan.previous_shape_cache[key]
    old = parse_element_sets(PREVIOUS.read_text())
    lookup = dict(zip(old.satellite_numbers, old.satellites, strict=True))
    available = [k for k, j in enumerate(labels) if int(scan.norads[j]) in lookup]
    numbers = [int(scan.norads[labels[k]]) for k in available]
    cat = ElementSetCatalogue(
        tuple(map(str, numbers)), tuple(numbers), tuple(lookup[n] for n in numbers)
    )
    current = dict(
        time_s=scan.sky["time_s"],
        position_km=scan.sky["position_km"][labels],
        velocity_km_s=scan.sky["velocity_km_s"][labels],
    )
    sample = np.array([0.0, 150.0, 300.0])
    po, _, good = ecef_states(cat, scan.receipt["origin_utc_ns"], sample)
    assert good.all()
    pn, vn = phase_shifted_states(current, sample, 0)
    pn, vn = pn[available], vn[available]
    vi = vn.copy()
    vi[..., 0] -= EARTH_ROTATION_RAD_S * pn[..., 1]
    vi[..., 1] += EARTH_ROTATION_RAD_S * pn[..., 0]
    phase = np.median(np.sum((po - pn) * vi, axis=2) / np.sum(vi**2, axis=2), axis=1)
    padding = int(np.ceil(max(abs(phase)))) + 18
    knots = np.arange(current["time_s"][0] - padding, current["time_s"][-1] + padding + 1)
    po, vo, good = ecef_states(cat, scan.receipt["origin_utc_ns"], knots)
    assert good.all()
    pp, vv = phase_shifted_states(
        dict(time_s=knots, position_km=po, velocity_km_s=vo), current["time_s"], -phase
    )
    previous = {name: value.copy() for name, value in current.items()}
    previous["position_km"][available] = pp
    previous["velocity_km_s"][available] = vv
    result = previous, set(available), dict(zip(numbers, map(float, phase), strict=True))
    scan.previous_shape_cache[key] = result
    return result


class CausalShapeFamilies(AnchoredFamilies):
    def __init__(self, scan, seed, method, fitted_c, anchor, *, sigma=1.0, aligned_previous=None):
        self.base_size, self.aligned_previous = None, None
        super().__init__(scan, seed, method, fitted_c, anchor)
        self.base_size = len(self.initial)
        self.shape_sigma = sigma
        if sigma <= 0 or not np.isfinite(sigma):
            raise ValueError("positive finite causal shape scale required")
        if aligned_previous is None:
            bank, available, self.phase_alignment = previous_bank(scan, self.labels)
        else:
            bank, available = aligned_previous, set(range(len(self.labels)))
            self.phase_alignment = {}
        supported = []
        for k, j in enumerate(self.labels):
            channels = {
                (scan.tracks[i]["receiver"], scan.tracks[i]["channel"])
                for i, r in zip(self.members, self.rows, strict=True)
                if r["candidate_index"] == j
            }
            if k in available and len(channels) >= 2:
                supported.append(j)
        self.shape_labels = supported
        self.initial = np.r_[self.initial, np.zeros(len(supported))]
        self.lower = np.r_[self.lower, np.full(len(supported), -3.0)]
        self.upper = np.r_[self.upper, np.full(len(supported), 3.0)]
        self.aligned_previous = bank

    def decode(self, x):
        if self.base_size is None:
            return super().decode(x)
        state = super().decode(x[: self.base_size])
        state["causal_shape_coefficients"] = dict(
            zip(self.shape_labels, np.asarray(x[self.base_size :]) * self.shape_sigma, strict=True)
        )
        return state

    def predicted(self, x):
        f, e = super().predicted(x)
        if self.aligned_previous is None:
            return f, e
        state = self.decode(x)
        phases = state["phases"][self.labels]
        old, _ = paired_phase_frequency(
            self.aligned_previous, self.flat_times, self.flat_labels, phases, *latlon(x[:2])
        )
        nominal, _ = paired_phase_frequency(
            self.sky, self.flat_times, self.flat_labels, phases, *latlon(x[:2])
        )
        for j, coefficient in state["causal_shape_coefficients"].items():
            mask = self.flat_labels == self.local_j[j]
            f[mask] += coefficient * (old[mask] - nominal[mask])
        return f, e

    def residual(self, x, *, details=False):
        result = super().residual(x, details=details)
        prior = np.asarray(x[self.base_size :])
        if details:
            return np.r_[result[0], prior], result[1]
        return np.r_[result, prior]


def run(method, sigmas=(0.0, 1.0, 3.0)):
    directory = OUTPUT / method
    directory.mkdir(parents=True, exist_ok=True)
    scan = Scan("DSX01-S01")
    seed = json.loads((SOURCE / f"{method}_center.json").read_text())
    output = directory / "endpoints.json"
    results = json.loads(output.read_text()) if output.exists() else {}
    write(
        directory / "protocol.json",
        dict(
            no_reference_GPS_or_oracle_calibration=True,
            latest_causal_TLE_remains_mean=True,
            previous_TLE_matches_original_causal_prior_receipt=True,
            previous_TLE_sha256=scan.receipt["previous_tle_sha256"],
            center=CENTER,
            grid=GRID,
            shared_shape_prior_sigmas=list(sigmas),
            coefficient_bounds_in_prior_sigma=3,
            corrections_require_two_distinct_curved_RX_channels=True,
            linear_tracks_never_calibrate=True,
            c0_fitted_c_same_points_candidates_other_priors_and_24_iteration_budgets=True,
            coefficient_is_a_frequency_error_direction_not_a_new_validated_TLE=True,
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for sigma in sigmas:
        name = f"shape_sigma_{sigma:g}"
        if all(f"{name}/{arm}" in results for arm in ("c0", "fitted_c")):
            continue
        if sigma:

            def factory(scan, seed, method, fitted_c, anchor, scale=sigma):
                return CausalShapeFamilies(scan, seed, method, fitted_c, anchor, sigma=scale)
        else:
            factory = AnchoredFamilies
        fits = fit_once(scan, seed, method, (0.0, 0.0), problem_class=factory)
        for arm, fit in fits.items():
            results[f"{name}/{arm}"] = fit
        write(output, results)
        print(
            json.dumps(
                dict(
                    method=method,
                    sigma=sigma,
                    positions={arm: list(f["east_north_km"]) for arm, f in fits.items()},
                    coefficients={
                        arm: len(f["state"].get("causal_shape_coefficients", {}))
                        for arm, f in fits.items()
                    },
                )
            ),
            flush=True,
        )
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--sigmas", nargs="+", type=float, default=(0.0, 1.0, 3.0))
    a = parser.parse_args()
    run(a.method, tuple(a.sigmas))
