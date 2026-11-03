"""Causal state-error directions; no receiver position or measured CFO input."""

import numpy as np
from analyze_dsx01_fixed_site import ecef_states
from fit_s01_69333_tle_parameter import perturb
from probe_dsx01_scan_influence import OUTPUT
from prototype_dsx01_mean_motion import reference_motion_basis
from prototype_s01_causal_shape import previous_bank
from sgp4.api import Satrec

from leo.analysis.research.orbit_phase_geometry import EARTH_ROTATION_RAD_S, phase_shifted_states
from leo.sky.propagation import ElementSetCatalogue


def build_modes(scan, labels, supported, kind):
    key = (tuple(labels), tuple(supported), kind)
    if not hasattr(scan, "causal_uncertainty_modes"):
        scan.causal_uncertainty_modes = {}
    if key in scan.causal_uncertainty_modes:
        return scan.causal_uncertainty_modes[key]
    old, available, phase = previous_bank(
        scan, labels, previous_path=OUTPUT / "causal_inputs" / scan.case / "previous.tle"
    )
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
        p, v, good = ecef_states(cat, scan.receipt["origin_utc_ns"], scan.sky["time_s"])
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
