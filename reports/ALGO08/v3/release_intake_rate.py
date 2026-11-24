"""Translate both release timing gates into a compressed-input throughput target."""

import argparse
import json
from pathlib import Path
from statistics import median

from reports.ALGO08.v3.release_stage_budget import checked


STAGES = "bf5e6488d1b59ba49ca091b6707b6d3fed099664f528bc7540bcbbed7afbc4be"
EXTENTS = "fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a"


def byte_bounds(pages, members, page_size):
    # The original cache observer rounds each nonempty compressed payload up to a page.
    if min(members, page_size) <= 0 or pages < members:
        raise ValueError("Invalid original member and page counts")
    high = pages * page_size
    return high - members * (page_size-1), high


def load_rows(stages, extents, panel):
    known = {r["case"]: r for r in extents["rows"]}
    rows = []
    for stage in stages["rows"]:
        case = stage["case"]
        data = json.loads(checked(panel / case / "pair.json", stage["pair_sha256"]))
        cache = data["cache_observation"]
        observed = cache["arms"]["candidate"]
        if observed["unavailable"] or observed["members"] != observed["observed_members"]:
            raise ValueError(f"Incomplete payload observation for {case}")
        low, high = byte_bounds(observed["observed_file_pages"], observed["members"], cache["page_size_bytes"])
        if case in known:
            original = known[case]
            size = round(original["compressed_MB"] * 1_000_000)
            if original["members"] != observed["members"] or not low <= size <= high:
                raise ValueError(f"Original sealed byte count contradicts the observed pages for {case}")
            low = high = size
        rows.append(dict(case=case, byte_low=low, byte_high=high, elapsed_s=stage["elapsed_s"],
                         pre_s=stage["pre_s"], post_s=stage["post_s"],
                         resident_fraction=stage["resident_fraction"]))
    if len(rows) != 100 or len(known) != 55 or not known.keys() <= {r["case"] for r in rows}:
        raise ValueError("Expected the historical 100-recording panel and 55 exact extents")
    return rows


def rate_gates(rows, byte_field, mb_per_second, post_speedup, startup_s):
    times = [r["elapsed_s"] if r["post_s"] is None else
             startup_s + (r[byte_field]/1_000_000)/mb_per_second + r["post_s"]/post_speedup
             for r in rows]
    return dict(median_ratio=median(t/r["elapsed_s"] for t, r in zip(times, rows, strict=True)),
                sum_ratio=sum(times)/sum(r["elapsed_s"] for r in rows))


def required_rate(rows, byte_field, post_speedup, startup_s):
    def ratios(rate):
        return rate_gates(rows, byte_field, rate, post_speedup, startup_s)

    if max(ratios(float("inf")).values()) >= .5:
        return None
    low, high = 0., 1.
    while max(ratios(high).values()) > .5:
        high *= 2
    for _ in range(60):
        middle = (low+high)/2
        if max(ratios(middle).values()) > .5:
            low = middle
        else:
            high = middle
    return dict(required_MB_s=high, **ratios(high))


def summarize(rows):
    groups = {}
    timed = [r for r in rows if r["pre_s"] is not None]
    for key, items in (("all", timed), ("cold", [r for r in timed if r["resident_fraction"] <= .01]),
                       ("warm", [r for r in timed if r["resident_fraction"] >= .99])):
        if items:
            groups[key] = dict(n=len(items), effective_MB_s=[
                sum(r[field] for r in items)/1e6/sum(r["pre_s"] for r in items)
                for field in ("byte_low", "byte_high")])
    scenarios = [dict(post_speedup=speed, startup_s=cost,
                      low=required_rate(rows, "byte_low", speed, cost),
                      high=required_rate(rows, "byte_high", speed, cost))
                 for speed in (1., 1.25, 1.5, 1.6, 2.) for cost in (0., .5)]
    return dict(groups=groups, scenarios=scenarios,
                original_bytes=[sum(r[k] for r in rows) for k in ("byte_low", "byte_high")])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("stages", "exact_extents", "archived_panel", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    rows = load_rows(json.loads(checked(args.stages, STAGES)), json.loads(checked(args.exact_extents, EXTENTS)),
                     args.archived_panel)
    args.output.write_text(json.dumps(dict(stage_sha256=STAGES, extent_sha256=EXTENTS,
                                          rows=rows, summary=summarize(rows)), indent=2, allow_nan=False)+"\n")
