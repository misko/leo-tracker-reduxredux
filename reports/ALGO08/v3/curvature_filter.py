"""Independent three-epoch bound and a separate sampled Doppler scout."""

from collections import Counter
from fractions import Fraction

import numpy as np


PHASES_S = (-15., 0., 15.)


def independent_bound(times, basis):
    """Zero bound on contrast loss if any unconstrained column spans it.

    Each input float is treated as its exact represented value. A missing
    witness means fallback. The result excludes no candidate in either case.
    """
    times, basis = np.asarray(times), np.asarray(basis)
    if (times.ndim != 1 or len(times) < 3 or basis.ndim != 2 or
            basis.shape[0] != len(times) or not np.isfinite(times).all() or
            not np.isfinite(basis).all() or not np.all(times[1:] > times[:-1])):
        return None
    indices = (0, (len(times)-1)//2, len(times)-1)
    a, b, c = [Fraction(float(times[i])) for i in indices]
    weights = (c-b, a-c, b-a)
    projections = [sum(w*Fraction(float(entry)) for w, entry in zip(weights, column, strict=True))
                   for column in basis[list(indices)].T]
    nonzero = sum(value != 0 for value in projections)
    numeric_weights = np.asarray(weights, dtype=float)
    norm = np.linalg.norm(numeric_weights)
    strongest = max(map(abs, projections), default=0)
    return dict(indices=indices, weights=numeric_weights/norm,
                nonzero_columns=nonzero, conditional_loss_floor=0 if nonzero else None,
                strongest_normalized_projection=float(strongest)/norm)


def eligibility(scan):
    """Test each active model once and retain each original row in order."""
    reports = [independent_bound(scan.tracks[i]["times"], scan.rx_basis[i]) for i in scan.curved]
    kinds = Counter("unsupported" if report is None else
                    "smooth_spans_contrast" if report["nonzero_columns"] else
                    "no_smooth_witness" for report in reports)
    slots = len(reports)*len(scan.norads)
    strengths = [r["strongest_normalized_projection"] for r in reports if r and r["nonzero_columns"]]
    return reports, dict(tracks=dict(kinds), slots=slots, survivors=slots,
                         min_strongest_smooth_projection=min(strengths, default=None),
                         max_strongest_smooth_projection=max(strengths, default=None),
                         disposition="original_full_fallback")


def update_ordering(best, sign, supported, observed, predicted, visible):
    """A sampled score can improve order, while unsupported rows stay eligible."""
    supported |= visible
    sign |= visible & (np.sign(predicted) == np.sign(observed))
    np.minimum(best, np.where(visible, np.abs(observed-predicted), np.inf), out=best)


def stable_order(norads, costs):
    return norads[np.argsort(costs, kind="stable")]


def sampled_ordering(scan, region, records):
    from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
    from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles

    active = [(i, r) for i, r in zip(scan.curved, records, strict=True) if r is not None]
    if not active:
        return dict(nodes=0, epochs=0, tracks=[])
    times = np.array([scan.tracks[i]["times"][list(r["indices"])] for i, r in active])
    unique, inverse = np.unique(times, return_inverse=True)
    indices = inverse.reshape(-1, 3)
    weights = np.array([r["weights"] for _, r in active])
    measured = np.array([scan.tracks[i]["values"][list(r["indices"])] for i, r in active])
    observed = np.einsum("ij,ij->i", weights, measured, optimize=False)[:, None]
    scale = np.array([scan.tracks[i]["rf_hz"]/11.5e9 for i, _ in active])[:, None]
    edge = region.half_width_km
    sites = [region.latlon(p) for p in ((0, 0), (-edge, -edge), (-edge, edge), (edge, -edge), (edge, edge))]
    observers = [(geodetic_to_ecef_km(lat, lon, 0.), ecef_to_enu_matrix(lat, lon)) for lat, lon in sites]
    support = np.zeros((len(active), len(scan.norads)), bool)
    sign = support.copy()
    best = np.full(support.shape, np.inf)
    visible_cells = 0
    for phase in PHASES_S:
        p, v = phase_shifted_states(scan.sky, unique, phase)
        for observer, rotation in observers:
            _, elevation, _, range_rate = look_angles(p, v, observer, rotation)
            prediction = (-11.5e9/299792.458)*range_rate
            contrast = scale*np.einsum("ij,kij->ik", weights, prediction[:, indices], optimize=False)
            visible = np.all(elevation[:, indices] >= 0., axis=2).T
            visible_cells += np.count_nonzero(visible)
            update_ordering(best, sign, support, observed, contrast, visible)
    result = []
    for j, (i, record) in enumerate(active):
        t = scan.tracks[i]
        best_cost = np.min(best[j])
        result.append(dict(key=t["key"], receiver=t["receiver"], rf_hz=t["rf_hz"],
                           observation_ids=t["observation_ids"], nonzero_columns=record["nonzero_columns"],
                           visible=int(np.count_nonzero(support[j])), sign_compatible=int(np.count_nonzero(sign[j])),
                           best_abs_hz=float(best_cost) if np.isfinite(best_cost) else None,
                           order=stable_order(scan.norads, best[j]).tolist()))
    return dict(nodes=len(sites)*len(PHASES_S), epochs=len(unique), phases_s=PHASES_S,
                visible_cells=int(visible_cells), tracks=result)
