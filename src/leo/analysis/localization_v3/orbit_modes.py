"""Causal orbital uncertainty from explicit previous elements, without file access."""
import hashlib

import numpy as np
from sgp4.api import WGS72, Satrec

from leo.analysis.localization_v3.orbits import ecef_states
from leo.analysis.localization_v3.scan import perturb
from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S, phase_shifted_states
from leo.sky.propagation import ElementSetCatalogue, parse_element_sets


def previous_bank(scan, labels):
    if scan.previous_tle is None or scan.previous_tle_sha256 is None:
        raise ValueError("Explicit previous causal TLE text and hash required")
    if hashlib.sha256(scan.previous_tle.encode()).hexdigest() != scan.previous_tle_sha256:
        raise ValueError("previous causal TLE bytes differ from the original prior receipt")
    if not hasattr(scan, "previous_shape_cache"):
        scan.previous_shape_cache = {}
    key = tuple(labels)
    if key in scan.previous_shape_cache:
        return scan.previous_shape_cache[key]
    old = parse_element_sets(scan.previous_tle)
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
    if not available:
        # A new catalogue object can have no earlier causal element. Preserve
        # the existing caller's unavailable-history prior; there is no phase
        # alignment or previous orbit to propagate in this case.
        result = {name: value.copy() for name, value in current.items()}, set(), {}
        scan.previous_shape_cache[key] = result
        return result
    sample = np.array([0.0, 150.0, 300.0])
    po, _, good = ecef_states(cat, scan.origin_utc_ns, sample)
    assert good.all()
    pn, vn = phase_shifted_states(current, sample, 0)
    pn, vn = pn[available], vn[available]
    vi = vn.copy()
    vi[..., 0] -= EARTH_ROTATION_RAD_S * pn[..., 1]
    vi[..., 1] += EARTH_ROTATION_RAD_S * pn[..., 0]
    phase = np.median(np.sum((po - pn) * vi, axis=2) / np.sum(vi**2, axis=2), axis=1)
    padding = int(np.ceil(max(abs(phase)))) + 18
    knots = np.arange(current["time_s"][0] - padding, current["time_s"][-1] + padding + 1)
    po, vo, good = ecef_states(cat, scan.origin_utc_ns, knots)
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
            (scan.origin_utc_ns / 1e9 + 150) / 86400
            + 2440587.5
            - sat.jdsatepoch
            - sat.jdsatepochF
        )
        cat = ElementSetCatalogue(
            (str(n), str(n)),
            (n, n),
            tuple(reference_motion_satellite(sat, d, elapsed) for d in (0.001, -0.001)),
        )
        p, v, good = ecef_states(cat, scan.origin_utc_ns, scan.sky["time_s"])
        if not good.all():
            raise ValueError("reference-aligned mean-motion propagation failed")
        scan.reference_motion_derivatives[j] = ((p[0] - p[1]) / 0.002, (v[0] - v[1]) / 0.002)
    return scan.reference_motion_derivatives[j]


def build_modes(scan, labels, supported, kind):
    key = (tuple(labels), tuple(supported), kind)
    if not hasattr(scan, "causal_uncertainty_modes"):
        scan.causal_uncertainty_modes = {}
    if key in scan.causal_uncertainty_modes:
        return scan.causal_uncertainty_modes[key]
    old, available, phase = previous_bank(scan, labels)
    nominal = dict(
        time_s=scan.sky["time_s"],
        position_km=scan.sky["position_km"][labels],
        velocity_km_s=scan.sky["velocity_km_s"][labels],
    )
    count = 1 if kind == "old_new" else 3
    shape = (len(labels), count, *nominal["position_km"].shape[1:])
    dp, dv = np.zeros(shape), np.zeros(shape)
    pn, vn = phase_shifted_states(nominal, np.array([0.0, 150.0, 300.0]), 0)
    po, _ = phase_shifted_states(old, np.array([0.0, 150.0, 300.0]), 0)
    vi = vn.copy()
    vi[:, :, 0] -= EARTH_ROTATION_RAD_S * pn[:, :, 1]
    vi[:, :, 1] += EARTH_ROTATION_RAD_S * pn[:, :, 0]
    radial = pn / np.linalg.norm(pn, axis=2)[:, :, None]
    normal = np.cross(pn, vi)
    normal /= np.linalg.norm(normal, axis=2)[:, :, None]
    difference = po - pn
    metadata = {}
    for k, j in enumerate(labels):
        if j not in supported:
            continue
        sigma_r = (
            max(0.05, float(np.median(abs(np.sum(difference[k] * radial[k], axis=1)))))
            if k in available
            else 0.5
        )
        sigma_n = (
            max(0.025, float(np.median(abs(np.sum(difference[k] * normal[k], axis=1)))))
            if k in available
            else 0.25
        )
        metadata[j] = dict(
            norad=int(scan.norads[j]),
            previous_available=k in available,
            radial_sigma_km=sigma_r,
            cross_sigma_km=sigma_n,
            old_alignment_s=phase.get(int(scan.norads[j])),
        )
        if kind == "old_new":
            dp[k, 0] = old["position_km"][k] - nominal["position_km"][k]
            dv[k, 0] = old["velocity_km_s"][k] - nominal["velocity_km_s"][k]
            continue
        sat = Satrec.twoline2rv(*scan.elements[str(int(scan.norads[j]))]["lines"])
        radius = float(np.mean(np.linalg.norm(pn[k], axis=1)))
        motion = sat.no_kozai * 1440 / (2 * np.pi)
        sigma_motion = 1.5 * motion / radius * sigma_r
        dpr, dvr = reference_motion_basis(scan, j)
        dp[k, 0], dv[k, 0] = dpr * sigma_motion, dvr * sigma_motion
        angular = np.rad2deg(sigma_n / radius)
        scales = (angular, angular / max(abs(np.sin(sat.inclo)), 0.1))
        satellites = tuple(
            perturb(sat, p, d) for p in ("inclination_deg", "raan_deg") for d in (0.001, -0.001)
        )
        n = int(scan.norads[j])
        cat = ElementSetCatalogue((str(n),) * 4, (n,) * 4, satellites)
        p, v, good = ecef_states(cat, scan.origin_utc_ns, scan.sky["time_s"])
        if not good.all():
            raise ValueError("orbital mode propagation failed")
        for mode, scale in enumerate(scales, 1):
            a = 2 * (mode - 1)
            dp[k, mode] = (p[a] - p[a + 1]) / 0.002 * scale
            dv[k, mode] = (v[a] - v[a + 1]) / 0.002 * scale
        metadata[j].update(
            mean_motion_sigma_rev_day=sigma_motion,
            inclination_sigma_deg=scales[0],
            raan_sigma_deg=scales[1],
        )
    bank = dict(
        time_s=nominal["time_s"],
        position_km=dp.reshape(-1, *dp.shape[2:]),
        velocity_km_s=dv.reshape(-1, *dv.shape[2:]),
    )
    scan.causal_uncertainty_modes[key] = (bank, metadata)
    return bank, metadata

