"""Run the frozen regional receiver against the offered regions for one case."""

import json
from pathlib import Path
from time import perf_counter

from ..reference import receiver


def run(case, work_dir):
    boundary = "frozen regional receiver from anonymous tracks and causal TLE to position"
    if not case.get("observation_path") or not case.get("catalog_path"):
        return dict(
            status="unavailable",
            reason="portable tracks or catalog unavailable",
            boundary=boundary,
            metrics={},
        )
    observation = json.loads(Path(case["observation_path"]).read_bytes())
    catalog = Path(case["catalog_path"]).read_bytes()
    start = perf_counter()
    answer = receiver.solve(observation, case["regions"], catalog)
    elapsed = perf_counter() - start
    point = answer["latlon"]
    arm = dict(latlon=point, forced_latlon=answer["best_latlon"])
    return dict(
        status="ok" if point is not None else "withheld",
        reason=answer["reason"],
        boundary=boundary,
        metrics={"candidate_s": elapsed, "calibration_invariant": True},
        arms={"c0": dict(arm), "fitted_c": dict(arm)},
    )
