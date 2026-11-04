"""Frozen family support weights and full-catalogue conditional identity screening."""

import numpy as np

from leo.analysis.localization_v3.history_position import problem
from leo.analysis.localization_v3.retained_position import phase_widths
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD


def competitor_confidence(costs, incumbent):
    """Conditional identity weight, never advertised as calibrated probability."""
    costs = np.asarray(costs, float)
    delta = np.clip((costs - np.nanmin(costs)) / 2, 0, 700)
    probabilities = np.exp(-delta)
    probabilities /= probabilities.sum()
    others = costs.copy()
    others[incumbent] = np.inf
    return float(probabilities[incumbent]), float(np.min(others) - costs[incumbent])


def candidate_profile(y, f, derivative, elevation, sigma, widths):
    """All-bank phase/constant screening under causal zero-centered priors.

    Radio calibration is frozen; orbital modes are omitted in this proposal
    approximation. Every final identity is scored with the full physical model.
    """
    y, f, d = np.asarray(y), np.asarray(f), np.asarray(derivative)
    n, variance = len(y), sigma**2
    alias = np.rint((f.mean(axis=1) - y.mean()) / PERIOD).astype(int)
    raw = y[None] + alias[:, None] * PERIOD - f
    bden = n + variance / 1000**2
    sy, sd = raw.sum(axis=1), d.sum(axis=1)
    information = np.maximum(0, (d * d).sum(axis=1) - sd**2 / bden)
    phi = ((raw * d).sum(axis=1) - sd * sy / bden) / (information + variance / widths**2)
    phi = np.clip(phi, -15, 15)
    bias = (sy - sd * phi) / bden
    residual = raw - phi[:, None] * d - bias[:, None]
    # Determinant of I + whitened two-column design Gram.
    a = 1 + n * 1000**2 / variance
    b = 1000 * widths * sd / variance
    c = 1 + widths**2 * (d * d).sum(axis=1) / variance
    cost = (residual**2).sum(axis=1) / variance + (bias / 1000) ** 2 + (phi / widths) ** 2
    cost += np.log(np.maximum(1, a * c - b * b))
    cost[np.min(elevation, axis=1) < 0] = np.inf
    return dict(
        cost=cost,
        aliases=alias,
        phase_s=phi,
        bias_hz=bias,
        rms_hz=np.sqrt(np.mean(residual**2, axis=1)),
    )


def family_weights(rows, members, tracks, confidence, method, active_counts=None):
    active_counts = (
        np.array([len(tracks[i]["times"]) for i in members])
        if active_counts is None
        else np.asarray(active_counts)
    )
    if len(active_counts) != len(rows) or np.any(active_counts < 0):
        raise ValueError("one nonnegative retained count per original fragment required")
    owners = {
        j: {
            (tracks[i]["receiver"], tracks[i]["channel"])
            for r, i, n in zip(rows, members, active_counts, strict=True)
            if r["candidate_index"] == j and n > 0
        }
        for j in {r["candidate_index"] for r in rows}
    }
    counts = {
        j: sum(n for r, n in zip(rows, active_counts, strict=True) if r["candidate_index"] == j)
        for j in owners
    }
    values = []
    for r, c in zip(rows, confidence, strict=True):
        j = r["candidate_index"]
        cross = len({rx for rx, ch in owners[j]}) >= 2
        replicated = len(owners[j]) >= 2 and c >= 0.95
        support = 1.0 if cross else (0.6 if replicated else 0.2)
        if method == "cross_rx_support":
            value = support
        elif method == "family_cap50":
            value = min(1.0, 50 / max(counts[j], 1))
        elif method == "cross_rx_cap100":
            value = support * min(1.0, 100 / max(counts[j], 1))
        else:
            raise ValueError("unknown frozen method")
        values.append(value)
    return np.array(values), owners, counts


def confidence_for(scan, node, keep, baseline):
    saved = baseline["arms"]["c0"]["record"]
    p = problem(scan, node, "c0", keep, np.asarray(saved["phase_reference"]))
    point = np.asarray(saved["endpoint_east_north_km"])
    state = p.state(point)
    widths, _ = phase_widths(scan, list(range(len(scan.norads))))
    weights = []
    anchors = [point] + [
        np.clip(point + d, -scan.search_region.half_width_km, scan.search_region.half_width_km)
        for d in (np.array([2, 0]), np.array([-2, 0]), np.array([0, 2]), np.array([0, -2]))
    ]
    for anchor in anchors:
        f, e, d = phase_linear_frequency(scan.geometry, *scan.search_region.latlon(anchor))
        row_weights = []
        for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
            tr, ix = scan.tracks[i], scan.index[i]
            active = keep[sl]
            if not active.any():
                row_weights.append(0.0)
                continue
            q = tr["rf_hz"] / 11.5e9
            y = (
                tr["values"]
                - scan.hardware(tr, state["beta"])
                - q * scan.rx_basis[i] @ state["smooth"][tr["receiver"] - 1]
            )
            profile = candidate_profile(
                y[active],
                q * f[:, ix][:, active],
                q * d[:, ix][:, active],
                e[:, ix][:, active],
                scan.radio_sigma_hz,
                widths,
            )
            row_weights.append(competitor_confidence(profile["cost"], row["candidate_index"])[0])
        weights.append(row_weights)
    return np.min(weights, axis=0)
