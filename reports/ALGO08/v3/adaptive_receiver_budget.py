"""Translate observed saved-publication ratios into conditional full-receiver budgets."""

import gzip
import json

from acquisition_throughput import minimum_rate
from regional_dense_budget import DATA, HERE, select
from staged_budget import checked


def receiver_budget(rows, publication_speedup):
    """Uniform effective MB/s from launch to sealed detections, including I/O waits."""
    if publication_speedup <= 0 or not rows:
        raise ValueError("A positive publication speedup and an enrolled panel are required")
    combined = []
    for row in rows:
        acquisition, solve, tail = row["stages"]
        # The measured saved clocks include figures and process exit. For cases
        # without a stage split the original budget function charges the full clock.
        combined.append(dict(row, stages=(acquisition, solve + tail, 0)))
    rates = [minimum_rate(combined, 1 / publication_speedup, gate) for gate in (0, 1)]
    return dict(median_MB_s=rates[0], summed_MB_s=rates[1],
                both_MB_s=None if None in rates else max(rates))


def report():
    held = json.loads(gzip.decompress(checked(DATA / "held-adaptive-0160.json.gz",
        "f5245f109ddd368c5ced7e55bb9e21cde6fbf053a7585f0ec0dd24a1d491d91c")))
    dense = json.loads(gzip.decompress(checked(DATA / "named-hybrid-baseline.json.gz",
        "d9c03be94e87bd34ccfa2f96330eebb097d3349be39fb166d81acd578ed5eb55")))["result"]["document"]
    speeds = dict(unchanged=1.0, held_medium=held["speedup"]["elapsed_s"],
                  dense_first_use=dense["saved_elapsed_speed_ratio_first_use"],
                  dense_prebuilt=dense["saved_elapsed_speed_ratio"])
    rows = json.loads(checked(DATA / "acquisition-throughput.json",
        "fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a"))["rows"]
    stages = json.loads(checked(HERE / "development/stages.json",
        "0bc940b1181b6fdb5f52ec1c5b768bfdbd6d2334e721fe8350cfc9ad3ca643c3"))["stages"]
    groups = {size: select(rows, [r["case"] for r in stages[size]["cases"]]) for size in ("4", "16")}
    groups["55"] = rows
    return {size: {name: receiver_budget(group, speed) for name, speed in speeds.items()}
            for size, group in groups.items()}


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, allow_nan=False))
