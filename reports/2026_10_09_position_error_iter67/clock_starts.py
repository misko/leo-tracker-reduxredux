"""Reference-free receiver-pair clock starts for ordinary joint hypotheses."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_08_position_error_iter36"))
from consensus import propose, wrap  # noqa: E402


def singleton_pairs(times_s, rf_hz, receiver):
    """Same millisecond/RF grouping as iteration34; ambiguous groups excluded."""
    groups = {}
    for i, (time, rf, rx) in enumerate(zip(times_s, rf_hz, receiver, strict=True)):
        key = (int(round(float(time) * 1000)), float(rf))
        groups.setdefault(key, {}).setdefault(int(rx), []).append(i)
    pairs = [
        (rx[0][0], rx[1][0])
        for _, rx in sorted(groups.items())
        if len(rx.get(0, [])) == len(rx.get(1, [])) == 1
    ]
    return np.asarray(pairs, dtype=int).reshape(-1, 2)


def pair_residuals(times_s, rf_hz, receiver, measured_hz, nuisance_hz, time_center_s):
    """No satellite association, position or reference metadata input."""
    pairs = singleton_pairs(times_s, rf_hz, receiver)
    corrected = np.asarray(measured_hz) - np.asarray(nuisance_hz)
    times = np.asarray(times_s)[pairs[:, 0]] - time_center_s
    residual = wrap(corrected[pairs[:, 1]] - corrected[pairs[:, 0]])
    return pairs, times, residual


def clock_starts(seed, times, residual, slope_limit=60):
    """Preserve other parameters; both anchors, explicit rejection, no clipping."""
    seed = np.asarray(seed, dtype=float)
    proposals = propose(times, residual) if len(times) else []
    starts = [("continued-original", seed.copy())]
    rejected = []
    for i, proposal in enumerate(proposals):
        for anchor in (0, 1):
            candidate = seed.copy()
            receiver, sign = (1, 1) if anchor == 0 else (0, -1)
            candidate[2 + receiver * 2] += sign * proposal["intercept_hz"]
            candidate[3 + receiver * 2] += sign * proposal["slope_hz_s"]
            name = f"proposal-{i + 1}-anchor-{anchor}"
            if abs(candidate[3 + receiver * 2]) > slope_limit:
                rejected.append(
                    dict(
                        name=name,
                        reason="affine slope outside hard60",
                        slope_hz_s=float(candidate[3 + receiver * 2]),
                    )
                )
            else:
                starts.append((name, candidate))
    return proposals, starts, rejected
