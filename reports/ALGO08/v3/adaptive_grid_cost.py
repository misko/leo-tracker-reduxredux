"""Price only the measured predictive geometry on matching genuine dense grid rows."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from leo.contracts.digests import canonical_digest
from .adaptive_grid_screen import DATA, ARMS, coordinates, screen


def geometry_cost(calls, selected, grid):
    points = {coordinates(row) for row in grid["points"]}
    # Each arm replays its own fitted endpoint without another predictive call.
    expected = {(p, arm) for p in points for arm in ARMS if p != tuple(grid["endpoints"][arm])}
    seen = set()
    totals = Counter()
    for row in calls:
        p = tuple(row["point"])
        key = p, row["arm"]
        if key not in expected or key in seen or not row["exact"]:
            raise ValueError("Invalid or duplicate paired predictive geometry clock")
        seen.add(key)
        for mode in ("released", "prepared"):
            totals[mode+"_all"] += row["clocks_ns"][mode]
            if p in selected:
                totals[mode+"_kept"] += row["clocks_ns"][mode]
    if seen != expected:
        raise ValueError("Missing predictive measurements for genuine objective calls")
    return {k: v / 1e9 for k, v in totals.items()}


def evaluate():
    def saved(name):
        return json.loads(gzip.decompress((DATA/name).read_bytes()))
    control = saved("dense-full-short-crossover.json.gz")["saved_replay"]
    paired = saved("grid-phase-state-reuse.json.gz")
    if (paired["science_sha256"] != control["science"] or canonical_digest(control["grid"]) != control["science"]["grid"]
            or paired["input_sha256"] != control["raw"]["raw_native_sha256"] or not all(paired["checks"].values())):
        raise ValueError("Require the same signed input, graph, grid and path")
    adaptive = screen(control["grid"])
    kept = set(map(tuple, adaptive["selected_xy"]))
    budget = json.loads((DATA/"dense-measured-budget.json").read_bytes())
    installed = budget["modeled"]["short_installed"]
    target = installed["scenarios"]["fastest_prefix"]["dense_solve_budget_s"]
    times = geometry_cost(paired["calls"], kept, control["grid"])
    return dict(grid_sha256=control["science"]["grid"], input_sha256=paired["input_sha256"],
                adaptive={k:v for k,v in adaptive.items() if k!="selected_xy"}, geometry_cpu_s=times,
                complete_matched_solve_cpu_s=installed["solve_cpu_s"],
                historical_model_dense_solve_budget_s=target,
                gap_to_fastest_prefix_s=installed["solve_cpu_s"]-target,
                measured_geometry_saving_all_points_s=times["released_all"]-times["prepared_all"],
                measured_geometry_saving_kept_points_s=times["released_kept"]-times["prepared_kept"],
                cost_of_omitted_released_geometry_s=times["released_all"]-times["released_kept"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    value = evaluate()
    with args.output.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
