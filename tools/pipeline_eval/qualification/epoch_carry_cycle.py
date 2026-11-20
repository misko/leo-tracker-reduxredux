"""Measure the same causal holdover rule across one authenticated retune cycle."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from unittest.mock import patch

from ..__main__ import save_json
from ..variants import epoch_carry
from . import epoch_carry_results
from . import epoch_carry_trial as trial
from .full_v5_check import _sha

OUT = trial.OUT / "cycle"


def feasibility():
    rows = []
    for item in trial.roster():
        source = trial.load(item)["source"]
        old = {}
        spacing = []
        for probe in source["probes"]:
            port, now = trial.lane(probe), probe["valid_start_counter"]
            if port in old:
                spacing.append((now - old[port]) / source["sample_rate_hz"])
            old[port] = now
        counts = defaultdict(int)
        for elapsed in spacing:
            for cutoff in (0.12, 0.40):
                if elapsed <= cutoff:
                    counts[str(cutoff)] += 1
        rows.append(
            dict(
                id=item["id"],
                gaps=len(spacing),
                minimum_s=min(spacing),
                median_s=median(spacing),
                supported=counts,
            )
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("predict", "score"))
    args = parser.parse_args()
    if args.action == "predict":
        save_json(
            OUT / "cycle-lock.json",
            dict(
                launcher=_sha(Path(__file__)),
                maximum_hold_s=0.4,
                prior_short_seal=_sha(trial.OUT / "prediction-lock.json"),
                timing_feasibility=feasibility(),
            ),
        )
    with patch.object(trial, "OUT", OUT), patch.object(epoch_carry, "MAX_HOLD_S", 0.4):
        if args.action == "predict":
            trial.main()
            lock = json.loads((OUT / "prediction-lock.json").read_bytes())
            lock["files"]["cycle-lock.json"] = _sha(OUT / "cycle-lock.json")
            save_json(OUT / "prediction-lock.json", lock)
        else:
            epoch_carry_results.main()


if __name__ == "__main__":
    main()
