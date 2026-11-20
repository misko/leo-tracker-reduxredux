"""Conditional field Doppler clock transfer and local position information."""

from dataclasses import dataclass
from math import inf, isfinite

import numpy as np

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from tools.pipeline_eval.reference import grid

RF_HZ = 11_325_000_000
BIN_SIGMA_HZ = (2e6 / 28000) / np.sqrt(12.0)
MAX_EFFECTIVE_SHIFT_S = 2.0
STENCIL_S = 0.05
LOCAL_STEP_KM = 0.25
RIVALS_KM = 5.0 * np.r_[np.eye(2), -np.eye(2)]


def carrier_design(index, time):
    return np.column_stack((np.eye(int(index.max()) + 1)[index], (time - 450.0) / 450.0))


def residual_rms(values):
    return float(np.sqrt(np.mean(np.square(values))))


def project_off(target, nuisance):
    """Remove nuisance rows using a rank-aware, scale-normalized orthogonal basis."""
    length = np.linalg.norm(nuisance, axis=0)
    keep = length > 1e-14
    basis, s, _ = np.linalg.svd(nuisance[:, keep] / length[keep], full_matrices=False)
    basis = basis[:, s > 1e-10]
    return target - basis @ (basis.T @ target)


def singular_for(position_hz, carrier, clock_hz, sigma_hz, clock_s):
    if clock_s == 0.0:
        remaining = project_off(position_hz, carrier)
    elif isfinite(clock_s):
        # Clock information from an independent reference is one extra observed row.
        n = carrier.shape[1]
        design = np.block(
            [[carrier, clock_hz[:, None]], [np.zeros((1, n)), np.array([[sigma_hz / clock_s]])]]
        )
        remaining = project_off(np.vstack((position_hz, np.zeros((1, 2)))), design)
    else:
        remaining = project_off(position_hz, np.column_stack((carrier, clock_hz)))
    return np.linalg.svd(remaining, compute_uv=False)


def information(position, clock, carrier, orbit_id, sigma_hz):
    result = {}
    for name, clock_s in (
        ("fixed-utc", 0.0),
        ("50ms-utc", 0.05),
        ("500ms-utc", 0.5),
        ("free-common-utc", inf),
    ):
        s = singular_for(position, carrier, clock, sigma_hz, clock_s)
        result[name] = dict(
            sigma_hz=sigma_hz,
            singular_hz_per_km=s.tolist(),
            worst_sd_km=sigma_hz / float(s[-1]) if s[-1] > 1e-8 else None,
        )
    orbit_phase = np.eye(int(orbit_id.max()) + 1)[orbit_id] * clock[:, None]
    gauge = project_off(clock, np.column_stack((carrier, orbit_phase)))
    s = np.linalg.svd(
        project_off(position, np.column_stack((carrier, orbit_phase))), compute_uv=False
    )
    result["free-orbit-epochs"] = dict(
        sigma_hz=sigma_hz,
        singular_hz_per_km=s.tolist(),
        worst_sd_km=sigma_hz / float(s[-1]) if s[-1] > 1e-8 else None,
        absolute_utc_gauge_relative_residual=(
            float(np.linalg.norm(gauge) / np.linalg.norm(clock)) if np.any(clock) else 0.0
        ),
    )
    return result


@dataclass(frozen=True)
class Arcs:
    catalogue: object
    satellite_rows: tuple
    times: np.ndarray
    values: np.ndarray
    arc_index: np.ndarray
    early: np.ndarray
    origin_utc_ns: int

    def states(self, shift):
        times, index = np.unique(self.times, return_inverse=True)
        utc = self.origin_utc_ns + np.rint((times + shift) * 1e9).astype(np.int64)
        sample = SamplingGrid(tuple(map(int, utc)), 0, 1.0)
        state = propagate_grid(self.catalogue, sample, indices=self.satellite_rows)
        keep = (self.arc_index, index)
        if np.any(state.error_code[keep] != 0):
            raise ValueError("a labelled causal orbit failed at measured epochs")
        jd, fraction = julian_day_from_utc_ns(utc)
        p, v = teme_to_ecef(
            state.position_teme_km,
            state.velocity_teme_km_s,
            greenwich_mean_sidereal_time_rad(jd, fraction),
        )
        return p[keep], v[keep]

    def carriers(self):
        return carrier_design(self.arc_index, self.times)


def prepare(observation, catalogue_text):
    cat = parse_element_sets(catalogue_text)
    clock = (
        observation["catalog_timestamp_ns"],
        observation["cutoff_utc_ns"],
        observation["anchor_utc_ns"],
    )
    if not clock[0] <= clock[1] <= clock[2]:
        raise ValueError("the field catalogue does not bind a causal capture clock")
    names = {}
    for i, label in enumerate(cat.names):
        names.setdefault(label, []).append(i)
    arcs = observation["arcs"]
    if len(arcs) < 2 or len(set(r["label"] for r in arcs)) != len(arcs):
        raise ValueError("the field clock control needs distinct labelled measured arcs")
    if any(len(names.get(row["label"], ())) != 1 for row in arcs):
        raise ValueError("a measured orbit label lacks an unambiguous causal row")
    rows = tuple(names[row["label"]][0] for row in arcs)
    epochs = cat.element_epoch_utc_ns()
    if any(epochs[i] > clock[1] for i in rows):
        raise ValueError("future orbit epoch in field receiver clock analysis")
    lengths = [len(row["time_s"]) for row in arcs]
    if any(
        np.any(np.diff(row["time_s"]) <= 0) or len(row["time_s"]) != len(row["frequency_hz"])
        for row in arcs
    ):
        raise ValueError("measured frequency rows must match a strictly increasing arc clock")
    t = np.concatenate([row["time_s"] for row in arcs])
    y = np.concatenate([row["frequency_hz"] for row in arcs])
    if min(lengths) < 6 or t.shape != y.shape or t.ndim != 1 or not np.isfinite(y).all():
        raise ValueError("insufficient labelled early and late field data")
    if not np.isfinite(t).all() or np.any(t < 0) or np.any(t > observation["duration_s"]):
        raise ValueError("the selected measurement timestamps leave the capture")
    early = np.concatenate([np.arange(n) < n // 2 for n in lengths])
    return Arcs(cat, rows, t, y, np.repeat(np.arange(len(arcs)), lengths), early, clock[-1])


def project(receivers, states):
    position, velocity = states
    los = position - receivers[:, None, :]
    return (
        -RF_HZ
        / grid.LIGHT_SPEED_KM_S
        * ((los * velocity).sum(axis=-1) / np.linalg.norm(los, axis=-1))
    )


def identified_shift(early_difference, carrier, clock_hz):
    remaining = project_off(np.column_stack((early_difference, clock_hz)), carrier)
    observed, slope = remaining.T
    energy = float(slope @ slope)
    if energy <= 1e-12:
        return None
    shift = (slope @ observed) / energy
    return float(np.clip(shift, -MAX_EFFECTIVE_SHIFT_S, MAX_EFFECTIVE_SHIFT_S))


def held_residual(values, forecast, carrier, early):
    residual = values - forecast
    fit = np.linalg.lstsq(carrier[early], residual[early].T, rcond=None)[0]
    return residual[~early] - carrier[~early] @ fit


def evaluate(arcs, location, altitude_m, donor_shift_s=None, sigma_hz=None):
    lat, lon = location
    receiver = geodetic_to_ecef_km(lat, lon, altitude_m)
    en = ecef_to_enu_matrix(lat, lon)[:2]
    comparison = receiver + np.vstack((np.zeros((1, 2)), RIVALS_KM)) @ en
    zero = arcs.states(0.0)
    baseline = project(comparison, zero)
    later = project(receiver[None], arcs.states(STENCIL_S))[0]
    earlier = project(receiver[None], arcs.states(-STENCIL_S))[0]
    clock = (later - earlier) / (2 * STENCIL_S)
    carrier, early = arcs.carriers(), arcs.early
    own = identified_shift((arcs.values - baseline[0])[early], carrier[early], clock[early])

    def held(positions):
        return [residual_rms(held_residual(arcs.values, row, carrier, early)) for row in positions]

    result = dict(
        fixed_utc_held_rms_hz=held(baseline),
        own_effective_shift_s=own,
        local_clock_held_rms_hz=None
        if own is None
        else held(project(receiver[None], arcs.states(own)))[0],
        causal_norads=[arcs.catalogue.satellite_numbers[i] for i in arcs.satellite_rows],
        sample_count=len(arcs.times),
        late_samples=int(np.count_nonzero(~early)),
        c_affine_level_gauge=True,
    )
    if donor_shift_s is not None:
        result.update(
            donor_effective_shift_s=donor_shift_s,
            donor_utc_held_rms_hz=held(project(comparison, arcs.states(donor_shift_s))),
        )
    if sigma_hz is not None:
        displaced = project(receiver + np.r_[en, -en] * LOCAL_STEP_KM, zero)
        gradient = ((displaced[:2] - displaced[2:]) / (2 * LOCAL_STEP_KM)).T
        result["information"] = information(
            gradient[~early], clock[~early], carrier[~early], arcs.arc_index[~early], sigma_hz
        )
        result["bin_floor_information"] = information(
            gradient[~early], clock[~early], carrier[~early], arcs.arc_index[~early], BIN_SIGMA_HZ
        )
    return result
