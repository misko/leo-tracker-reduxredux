"""Fit a two-dimensional position from labelled, UTC-tagged VHF Doppler passes."""

from dataclasses import dataclass
from functools import cached_property

import numpy as np
from scipy.optimize import least_squares
from sgp4.api import Satrec

from leo.sky.frames import (
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)

LIGHT_KM_S = 299_792.458
WIDTH = 25.0
INTERIOR_KM = 0.02
MAX_HELD_DRIFT_KM = 3.0
MIN_HELD_GAIN_HZ = 0.50
GRID_POINTS = 9
METHODS = (
    "orbcomm_held_shape",
    "orbcomm_ungated_shape",
    "orbcomm_absolute",
    "orbcomm_time_reverse",
    "orbcomm_offer_center",
)


@dataclass
class Observations:
    xyz: np.ndarray
    velocity: np.ndarray
    rf_hz: np.ndarray
    observed: np.ndarray
    groups: np.ndarray
    reversed_observed: np.ndarray
    track_count: int
    norads: tuple

    @cached_property
    def sizes(self):
        return np.bincount(self.groups)

    @cached_property
    def weights(self):
        return np.sqrt(1 / (self.track_count * self.sizes[self.groups]))

    def project(self, values):
        average = np.bincount(self.groups, weights=values) / self.sizes
        return values - average[self.groups]

    def profile(self, point, model):
        station = geodetic_to_ecef_km(*point, 0.0)
        relative = self.xyz - station
        radial = np.einsum("ij,ij->i", relative, self.velocity) / np.linalg.norm(relative, axis=1)
        doppler = -self.rf_hz * radial / LIGHT_KM_S
        observed = self.reversed_observed if model == "reversed" else self.observed
        residual = observed - doppler
        return (self.project(residual) if model != "absolute" else residual) * self.weights


def observations(tracks, elements):
    if len({r["norad"] for r in tracks}) < 3 or len(tracks) < 6:
        raise ValueError("each independent day needs three orbits and six pass-channel traces")
    positions, velocities, frequencies, values, groups, reversed_values = [], [], [], [], [], []
    for i, r in enumerate(tracks):
        t = np.asarray(r["times_ns"], dtype=np.int64)
        y = np.asarray(r["cfo_hz"], dtype=float)
        orbit = elements[str(r["tle_id"])]
        if (
            len(t) < 12
            or len(t) != len(y)
            or np.any(np.diff(t) <= 0)
            or not np.all(np.isfinite(y))
            or t[0] < max(orbit["epoch_ns"], orbit["first_used_ns"])
            or r["norad"] != orbit["norad"]
            or not 137.2e6 <= r["rf_hz"] <= 137.8e6
        ):
            raise ValueError("pass measurement and earlier-used orbit contract mismatch")
        satellite = Satrec.twoline2rv(*orbit["tle"])
        jd, fraction = julian_day_from_utc_ns(t)
        status, position, speed = satellite.sgp4_array(jd, fraction)
        if np.any(status):
            raise ValueError("SGP4 rejected an authenticated earlier orbit")
        xyz, velocity = teme_to_ecef(
            position, speed, greenwich_mean_sidereal_time_rad(jd, fraction)
        )
        positions.append(xyz)
        velocities.append(velocity)
        values.append(y)
        reversed_values.append(y[::-1])
        frequencies.append(np.full(len(y), r["rf_hz"]))
        groups.append(np.full(len(y), i, dtype=int))
    return Observations(
        *(
            np.concatenate(x)
            for x in (positions, velocities, frequencies, values, groups, reversed_values)
        ),
        len(tracks),
        tuple(sorted({r["norad"] for r in tracks})),
    )


def geographic(center, offset):
    latitude, longitude = center
    east, north = offset
    return [
        float(latitude + north / 111),
        float(longitude + east / (111.32 * np.cos(np.deg2rad(latitude)))),
    ]


def solve_mode(train, held, center, kind):
    def fit(panel):
        def residual(local):
            return panel.profile(geographic(center, local), kind)

        ordinate = np.linspace(-WIDTH / 2, WIDTH / 2, GRID_POINTS)
        grid = [(e, n) for e in ordinate for n in ordinate]
        start = min(grid, key=lambda local: np.linalg.norm(residual(local)))
        result = least_squares(
            residual,
            start,
            bounds=(-WIDTH / 2, WIDTH / 2),
            max_nfev=30,
            ftol=1e-7,
            xtol=1e-7,
            gtol=1e-7,
        )
        return result, residual

    early, rf = fit(train)
    independent, verify = fit(held)
    xyz = early.x
    support = np.linalg.svd(early.jac, compute_uv=False)
    held_rms = float(np.linalg.norm(verify(xyz)))
    return dict(
        max_face_km=float(WIDTH / 2 - max(abs(xyz))),
        held_face_km=float(WIDTH / 2 - max(abs(independent.x))),
        held_stability_km=float(np.linalg.norm(independent.x - xyz)),
        held_center_gain_hz=float(np.linalg.norm(verify((0, 0))) - held_rms),
        training_rms_hz=float(np.linalg.norm(rf(xyz))),
        held_rms_hz=held_rms,
        horizontal_rank=int(np.count_nonzero(support > 1e-5)),
        numerically_returned=bool(early.success and independent.success),
        forced_latlon=geographic(center, xyz),
    )


def hold_reason(value):
    if not value["numerically_returned"] or value["horizontal_rank"] != 2:
        return "geographic_rank_or_numerics"
    if min(value["max_face_km"], value["held_face_km"]) <= INTERIOR_KM:
        return "fit_at_region_face"
    if value["held_stability_km"] > MAX_HELD_DRIFT_KM:
        return "independent_day_disagrees"
    if value["held_center_gain_hz"] < MIN_HELD_GAIN_HZ:
        return "insufficient_held_gain_over_center"
    return None


def outcome(point, science, *, reason=None, is_prior=False):
    ground = point if not reason else None
    c0 = dict(latlon=ground, forced_latlon=point if reason else None)
    if science is not None:
        c0["rf_rms_hz"] = science["held_rms_hz"]
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary="Independent measured UAB VHF Doppler after author attribution",
        metrics=dict(science or {}, prior_only=is_prior, rf_slope_identifiable=False),
        arms=dict(c0=c0, fitted_c=dict(latlon=None, reason="per_pass_offsets_span_rf_term")),
    )


def infer(packet, center):
    train = observations(packet["training"], packet["elements"])
    held = observations(packet["held"], packet["elements"])
    shape, absolute, reversed_shape = (
        solve_mode(train, held, center, kind) for kind in ("shape", "absolute", "reversed")
    )
    numerical = "geographic_rank_or_numerics"
    contents = (
        outcome(shape["forced_latlon"], shape, reason=hold_reason(shape)),
        outcome(
            shape["forced_latlon"],
            shape,
            reason=numerical if not shape["numerically_returned"] else None,
        ),
        outcome(
            absolute["forced_latlon"],
            absolute,
            reason=numerical if not absolute["numerically_returned"] else None,
        ),
        outcome(
            reversed_shape["forced_latlon"], reversed_shape, reason=hold_reason(reversed_shape)
        ),
        outcome(center, None, is_prior=True),
    )
    projected = max(np.max(abs(panel.project(panel.rf_hz - 137.5e6))) for panel in (train, held))
    coverage = dict(
        training_tracks=train.track_count,
        held_tracks=held.track_count,
        training_rows=len(train.observed),
        held_rows=len(held.observed),
        train_norads=list(train.norads),
        held_norads=list(held.norads),
        max_profiled_rf_column=float(projected),
    )
    return dict(zip(METHODS, contents, strict=True)), coverage


if __name__ == "__main__":
    import json
    import sys

    request = json.load(sys.stdin)
    rows, support = infer(request["packet"], request["tile"])
    print(json.dumps(dict(results=rows, support=support), allow_nan=False))
