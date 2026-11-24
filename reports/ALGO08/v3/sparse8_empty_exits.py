"""Price perfect negative decisions at actual boundaries of the timed 8 ms receiver."""

import argparse
import json
from math import fsum
from pathlib import Path
from statistics import median

from .receiver_solver_targets import first30, held_clocks
from .sparse8_native_profile import HERE, STAGES, checked, field_receipt


PROFILE = "c050491c6628b3f76a364917d388878580269a4cc70e07fd0f6b9a5ee3cb157b"


def price(rows, clocks, first_skipped):
    remaining = STAGES[STAGES.index(first_skipped):]
    # Unassigned bookkeeping has no known position within the callback.
    # Only the pre-entry oracle gets credit for avoiding that interval.
    eligible = fsum(clocks["empty"][s] for s in remaining if s != "other" or first_skipped == "input_mix")
    empty_time, positive_time = (fsum(clocks[label].values()) for label in ("empty", "positive"))
    base, predicted, credits = [], [], []
    for row in rows:
        n, p = row["short_lanes"], row["short_positives"]
        if not 0 <= p <= n or (n == 0 and row["short_s"] != 0):
            raise ValueError("Inconsistent paid short calls or selected factors")
        empty = n - p
        total = empty * empty_time + p * positive_time
        saving = row["short_s"] * empty * eligible / total if n else 0.
        credits.append(saving)
        base.append(row["installed_s"])
        predicted.append(row["candidate_s"] - row["solver_s"] * (1 - 1 / 1.4) - saving)
    return dict(pairs=len(rows), saved_short_wall_s=fsum(credits), summed_speedup=fsum(base) / fsum(predicted),
                median_paired_speedup=1 / median(b / a for a, b in zip(base, predicted, strict=True)),
                excess_above_half_s=fsum(predicted) - .5 * fsum(base))


def evaluate(campaign):
    profile = json.loads(checked(HERE / "measurements/sparse8-native-profile.json", PROFILE))
    originals = {r["case"]: r for r in first30()}
    development = []
    for census in field_receipt()["cases"]:
        r = originals[census["case"]]
        if r["pins"]["result"] != census["candidate_join_sha256"]:
            raise ValueError("Development clocks and native counts differ in worker identity")
        mode = census["modes"]["short_primary"]
        n = mode.get("lanes", 0)
        development.append(dict(installed_s=r["stock_wall_s"], candidate_s=r["actual_wall_s"],
                                solver_s=r["phases"]["outer"]["elapsed_s"]["solve"], short_s=mode["elapsed_ns"] / 1e9,
                                short_lanes=n, short_positives=n - mode.get("empty_lanes", 0)))
    later = held_clocks(campaign, split_apertures=True)
    result = {}
    for prefix, donor in profile["cases"].items():
        clocks = {k: donor["summary"][k]["exclusive_per_lane_cpu_ns"] for k in ("empty", "positive")}
        groups = (("first30", development), ("next16", later), ("first46", development + later))
        result[prefix] = {
            group: {cut: price(rows, clocks, cut) for cut in
                    ("input_mix", "lag_timing", "carrier_grid", "full_rate_refine", "verifier_load")}
            for group, rows in groups}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    print(json.dumps(evaluate(parser.parse_args().campaign.resolve(strict=True)), indent=2, allow_nan=False))
