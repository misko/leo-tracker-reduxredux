"""Test whether frame-frequency curvature identifies a receiver settling time.

No satellite, orbit, GPS or localization score enters this diagnostic. Linear
within-window ramps alone cannot calibrate an asymptotic frequency correction.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from probe_dsx01_pilot_clock import write


def profile(windows, taus):
    """Shared time constant; independent frequency and amplitude per window."""
    costs = np.zeros((len(windows), len(taus)))
    for i, window in enumerate(windows):
        t, y, w = [np.array(window[k]) for k in ("time", "frequency", "weight")]
        yc = y - np.average(y, weights=w)
        for j, tau in enumerate(taus):
            basis = t if np.isinf(tau) else -tau * np.expm1(-t / tau)
            b = basis - np.average(basis, weights=w)
            slope = np.sum(w * b * yc) / max(1e-30, np.sum(w * b * b))
            costs[i, j] = np.sum(w * (yc - slope * b) ** 2)
    return costs


def summarize(windows, *, bootstrap=128):
    taus = np.r_[np.geomspace(0.0005, 0.100, 129), np.inf]
    costs = profile(windows, taus)
    total = costs.sum(axis=0)
    best = int(np.argmin(total))
    rng = np.random.default_rng(20261018)
    draws = [
        int(np.argmin(costs[rng.integers(0, len(windows), len(windows))].sum(axis=0)))
        for _ in range(bootstrap)
    ]
    improvement = float(1 - total[best] / total[-1])
    interior = best >= 2 and best < len(taus) - 3
    stable = float(np.mean((np.array(draws) >= 2) & (np.array(draws) < len(taus) - 3)))
    identified = bool(interior and improvement >= 0.02 and stable >= 0.9)
    return dict(
        windows=len(windows),
        tau_grid_ms=[None if np.isinf(t) else float(t * 1000) for t in taus],
        weighted_sse=total.tolist(),
        best_index=best,
        best_tau_ms=None if np.isinf(taus[best]) else float(taus[best] * 1000),
        improvement_over_free_linear=improvement,
        bootstrap_interior_fraction=stable,
        bootstrap_indices=draws,
        identified_for_extrapolation=identified,
        support_rule="interior min,>=2percent curvature gain,>=90percent window-bootstrap interior",
    )


def run(source, output):
    data = json.loads(source.read_text())
    groups = {str(i): [] for i in range(4)}
    for oid, row in data["points"].items():
        f = row["midpoint300"]
        t, y, m = [
            np.array(f[k])
            for k in ["frame_time_from_midpoint_s", "frame_frequencies_hz", "frame_margins"]
        ]
        good = (m >= 0.02) & (abs(y) <= 750)
        if good.sum() < 10 or np.ptp(t[good]) < 0.010:
            continue
        weights = np.minimum(m[good] ** 2, 4 * np.median(m[good] ** 2))
        weights /= weights.mean()
        groups[str(2 * (row["receiver"] - 1) + int(row["channel"] > 4))].append(
            dict(observation_id=oid, time=t[good], frequency=y[good], weight=weights)
        )
    result = {g: summarize(w) for g, w in groups.items() if len(w) >= 20}
    write(
        output,
        dict(
            results=result,
            no_GPS_TLE_or_satellite_labels=True,
            linear_ramps_cannot_authorize_asymptotic_corrections=True,
            profile_is_descriptive_not_calibrated_likelihood=True,
        ),
    )
    print(
        json.dumps(
            {
                g: {
                    k: v
                    for k, v in d.items()
                    if k not in ["tau_grid_ms", "weighted_sse", "bootstrap_indices"]
                }
                for g, d in result.items()
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    run(a.source, a.output)
