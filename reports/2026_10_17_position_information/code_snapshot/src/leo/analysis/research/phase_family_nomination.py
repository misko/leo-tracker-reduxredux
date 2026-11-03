"""Conservative curved-only nominations for previously unused clipped phases."""

import numpy as np


def nominate_clipped_families(
    rows_c0, rows_fitted_c, norads, phases_s, bounds_s, *, minimum_members=2
):
    """Use one common c0 nomination population, excluding either arm's old labels.

    No linear fragment estimates, ranks or locks a phase. Only candidates
    already supported by admitted curved measurements have established phases.
    The returned families need separate physical competition and gates.
    """
    if minimum_members < 2:
        raise ValueError("at least two curved fragments required")
    for rows in (rows_c0, rows_fitted_c):
        if len({r["component"] for r in rows}) != len(rows):
            raise ValueError("duplicate fragment nomination")
    norads, phases, bounds = np.asarray(norads), np.asarray(phases_s), np.asarray(bounds_s)
    if phases.shape != norads.shape or bounds.shape != norads.shape:
        raise ValueError("one phase and bound per candidate required")
    accepted = [r for r in [*rows_c0, *rows_fitted_c] if r["compatible"] and r["active_curvature"]]
    locked = {int(r["candidate_norad"]) for r in accepted}
    occupied = {r["component"] for r in accepted}
    lookup = {int(n): i for i, n in enumerate(norads)}
    families = {}
    for row in rows_c0:
        n = int(row["candidate_norad"])
        if row["component"] in occupied or n in locked or not row["active_curvature"]:
            continue
        j = lookup[n]
        if bounds[j] <= 0 or abs(phases[j]) < 0.995 * bounds[j]:
            continue
        families.setdefault(n, []).append(row)
    return [
        dict(
            norad=n,
            members=sorted(r["component"] for r in rows),
            points=sum(r["points"] for r in rows),
            previous_phase_s=float(phases[lookup[n]]),
            bound_s=float(bounds[lookup[n]]),
        )
        for n, rows in sorted(families.items())
        if len(rows) >= minimum_members
    ]
