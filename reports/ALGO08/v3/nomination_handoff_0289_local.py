"""Run the unchanged local saved solver pair on the preregistered third DS30 case."""

import argparse
from gzip import decompress
import json
from pathlib import Path
from statistics import median
import sys

from reports.ALGO08.v3 import nomination_handoff_0419_local as shared
from reports.ALGO08.v3.nomination_handoff_0419_admission import digest, enrollment


CASE = "DS30-0289"
RANK_HASH = "0b8fdea3caa8213541ab9af6eaf8af4a67a93f6f58ca40a0a4e14df712a9ffae"
PAIR_PIN = "1604ab43b65e06fa48d5efd3677dbfc2fbd4020f1989171ae77589594dd5fc66"
EARLIER = Path(__file__).with_name("measurements") / "nomination-handoff-0419-local.json.gz"
EARLIER_PIN = "cf0f8f0673f3b1f6043d7766b6f4925083376c74d1d129d128fb5813dc0c9f70"


def assigned():
    assignment = enrollment(ranked=3, case=CASE, ranking_hash=RANK_HASH, pair_pin=PAIR_PIN)
    return assignment | {"order": assignment["planned_order"], "archived_pair_sha256": PAIR_PIN}


def previous_blind():
    body = decompress(EARLIER.read_bytes())
    if digest(body) != EARLIER_PIN:
        raise ValueError("The prior independent publication receipt differs")
    ready = json.loads(body)
    if ready["case"] != "DS30-0419" or ready["admission"]["assignment"]["rank"] != 2:
        raise ValueError("Expected the original rank-two independent result")
    return ready


def independent_pool(earlier, current):
    rows = earlier, current
    modes = ("installed", "routed")
    timing = {}
    for metric in ("elapsed_s", "cpu_s"):
        times = {mode: [row["time"][metric][mode] for row in rows] for mode in modes}
        ratios = [b / a for a, b in zip(times["installed"], times["routed"], strict=True)]
        named, routed = (sum(times[mode]) for mode in modes)
        admission = sum(row["admission"]["setup"][metric] for row in rows)
        timing[metric] = dict(named=named, routed=routed, summed_speedup=named / routed,
                              median_paired_speedup=1 / median(ratios), common_admission=admission,
                              summed_with_common_admission=(named + admission) / (routed + admission))
    return dict(cases=[row["case"] for row in rows],
                fixes={mode: sum(row["jobs"][mode]["decision"] == "complete" for row in rows) for mode in modes},
                candidate_minus_installed_horizontal_m={
                    row["case"]: row["candidate_minus_installed_horizontal_m"] for row in rows},
                geographic={row["case"]: row["geographic"] for row in rows}, timing=timing)


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    opts = cli.parse_args()
    if opts.action == "launch":
        shared.launch(opts.root, assign=assigned)
    else:
        shared.score(opts.root, assign=assigned, previous_blind=previous_blind(), pool_blind=independent_pool)
