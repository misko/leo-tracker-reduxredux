"""Minimum summed wall time for a zero-cost choice that preserves installed error coverage."""

import argparse
import json
from math import fsum, isfinite
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csc_matrix

from .ds30_oracle_routing import coverage, meets
from .ds30_stage_progress import verified_measurements
from .full_successor_score import frozen_stage_order, roster


def fastest_route(pairs, fraction=1., cutoffs=None):
    """One binary choice per recording, shared by both calibrations at every threshold."""
    if not pairs or not 0 <= fraction <= 1:
        raise ValueError("Expected measured pairs and a candidate time fraction in [0,1]")
    groups = coverage(pairs, cutoffs)
    size = len(pairs)
    # Each selected candidate adds or subtracts one covered recording at a threshold.
    rows = {tuple(((candidate >> i) & 1) - ((base >> i) & 1) for i in range(size))
            for group in groups.values() for _, base, candidate in group}
    # A row containing only gains can never reduce installed coverage.
    rows = sorted(row for row in rows if min(row) < 0)
    baseline = np.array([a["elapsed_s"] for a, _ in pairs])
    candidate = np.array([b["elapsed_s"] for _, b in pairs])
    if not all(np.all(np.isfinite(t) & (t > 0)) for t in (baseline, candidate)):
        raise ValueError("Both build times must be positive and finite")
    constraints = LinearConstraint(csc_matrix(rows), 0, np.inf) if rows else None
    result = milp(fraction * candidate - baseline, integrality=np.ones(size),
                  bounds=Bounds(0., 1.), constraints=constraints, options={"mip_rel_gap": 0.})
    if not result.success:
        raise ValueError(f"Routing optimum unresolved: {result.message}")
    flags = np.rint(result.x).astype(bool)
    route = sum(1 << i for i, use in enumerate(flags) if use)
    baseline_s = fsum(baseline)
    selected_s = fsum(np.where(flags, fraction * candidate, baseline))
    lower_bound_s = baseline_s + result.mip_dual_bound
    if not (meets(groups, route) and isfinite(lower_bound_s) and abs(lower_bound_s - selected_s) < 1e-5):
        raise ValueError("Routing witness or objective bound did not verify")
    return dict(pairs=size, time_fraction=fraction, candidate_choices=int(flags.sum()),
                installed_total_s=baseline_s, optimum_total_s=selected_s, dual_bound_s=lower_bound_s,
                within_half_total=selected_s <= .5 * baseline_s,
                candidate_cases=[a["case"] for (a, _), use in zip(pairs, flags, strict=True) if use])


def timing_requirement(pairs, cutoffs=None):
    measured = fastest_route(pairs, 1., cutoffs)
    free = fastest_route(pairs, 0., cutoffs)
    result = dict(measured=measured, free_candidate=free)
    if measured["within_half_total"]:
        return dict(**result, feasible_fraction=1., infeasible_fraction=None)
    if not free["within_half_total"]:
        return dict(**result, feasible_fraction=None, infeasible_fraction=0.)
    # The minimum over routes of nondecreasing affine wall times is nondecreasing.
    lo, hi = 0., 1.
    for _ in range(14):
        mid = (lo + hi) / 2
        if fastest_route(pairs, mid, cutoffs)["within_half_total"]:
            lo = mid
        else:
            hi = mid
    return dict(**result, feasible_fraction=lo, infeasible_fraction=hi)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--limit", type=int, help="Use the first N verified recordings in frozen enrollment order")
    args = parser.parse_args()
    assigned = roster()
    order = frozen_stage_order({k: (r["case_id"], r["physical_content"]) for k, r in assigned.items()})
    seal = json.loads(args.export.with_name("rows-with-relocations-seal.json").read_bytes())
    pairs = {a["case"]: (a, b) for a, b in verified_measurements(args.export.read_bytes(), seal, assigned)}
    prefix = next((i for i, case in enumerate(order) if case not in pairs), len(order))
    limit = prefix if args.limit is None else args.limit
    if not 1 <= limit <= prefix:
        raise ValueError("Requested cohort exceeds the verified prefix or is empty")
    selected = [pairs[case] for case in order[:limit]]
    output = dict(export_sha256=seal["combined_sha256"], limit=limit,
                  full_curve=timing_requirement(selected), one_two_km=timing_requirement(selected, (1., 2.)))
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
