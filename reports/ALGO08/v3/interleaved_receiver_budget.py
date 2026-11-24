"""Cost envelope for replacing both odd-visit short callbacks on the measured panel."""

import argparse
import json
from math import fsum
from pathlib import Path
from statistics import median

from .receiver_solver_targets import first30, held_clocks
from .sparse8_native_profile import field_receipt


def omitted_lanes(full, short):
    if any(type(n) is not int or n < 0 or n % 2 for n in (full, short)) or short > 7 * full:
        raise ValueError("Expected stereo lane counts from cycles with 0–7 short visits")
    cycles, visits = full // 2, short // 2
    # Each cycle with k short visits withholds ceil(k/2) stereo visits.
    # An even k is at most 6, an odd k is at least 1, and sum(k) fixes parity.
    low = max(0, visits - 6 * cycles)
    high = min(cycles, visits)
    return visits + low + (visits-low) % 2, visits + high - (high-visits) % 2


def price(rows, solver_rate, added_us, bound):
    if bound not in ("favorable", "conservative") or not rows or solver_rate < 1 or added_us < 0:
        raise ValueError("Expected measured rows, a solver rate and a nonnegative marginal cost")
    choose = min if bound == "favorable" else max
    base, times = [], []
    for r in rows:
        n = r["short_lanes"]
        if not n and r["short_s"]:
            raise ValueError("Short time requires measured short callbacks")
        mean_short = r["short_s"] / n if n else 0.
        per_lane_change = added_us / 1e6 - mean_short
        low, high = omitted_lanes(r["full_lanes"], n)
        change = choose(low * per_lane_change, high * per_lane_change)
        times.append(r["candidate_s"] - r["solver_s"] * (1 - 1/solver_rate) + change)
        base.append(r["installed_s"])
    return dict(summed_speedup=fsum(base)/fsum(times),
                median_paired_speedup=1/median(t/b for t,b in zip(times, base, strict=True)),
                slack_to_half_total_s=fsum(base)/2-fsum(times))


def budget(rows, rate, bound):
    def met(us):
        v = price(rows, rate, us, bound)
        return min(v["summed_speedup"], v["median_paired_speedup"]) >= 2
    free = price(rows, rate, 0., bound)
    limit = None
    if met(0.) and any(omitted_lanes(r["full_lanes"], r["short_lanes"])[0] for r in rows):
        # Beyond this upper bound even one affected case exceeds half the baseline total.
        low, high = 0., 1e6 * fsum(r["installed_s"]+r["short_s"] for r in rows)
        for _ in range(62):
            mid = (low+high)/2
            if met(mid):
                low = mid
            else:
                high = mid
        limit = low
    return dict(free_replacement=free, maximum_us_per_omitted_lane=limit)


def evaluate(campaign):
    cases = {r["case"]:r for r in first30()}
    dev = []
    for census in field_receipt()["cases"]:
        src = cases[census["case"]]
        if census["candidate_join_sha256"] != src["pins"]["result"]:
            raise ValueError("Field timing and receiver counts belong to different attempts")
        modes = census["modes"]
        dev.append(dict(installed_s=src["stock_wall_s"], candidate_s=src["actual_wall_s"],
                        solver_s=src["phases"]["outer"]["elapsed_s"]["solve"],
                        short_s=modes["short_primary"]["elapsed_ns"]/1e9,
                        short_lanes=modes["short_primary"].get("lanes", 0), full_lanes=modes["full"].get("lanes", 0)))
    later = held_clocks(campaign, split_apertures=True)
    groups = {}
    for label, rows in (("first30",dev), ("next16",later), ("first46",dev+later)):
        counts = [omitted_lanes(r["full_lanes"], r["short_lanes"]) for r in rows]
        groups[label] = dict(pairs=len(rows), short_lanes=sum(r["short_lanes"] for r in rows),
                             omitted_lane_range=[sum(x) for x in zip(*counts)])
        for rate in (1.,1.4):
            groups[label][str(rate)] = {side:budget(rows,rate,side) for side in ("favorable","conservative")}
    return groups


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    print(json.dumps(evaluate(parser.parse_args().campaign.resolve(strict=True)), indent=2, allow_nan=False))
