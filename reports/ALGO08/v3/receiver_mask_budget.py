"""Price selective short-receiver work against the signed DS30 four- and sixteen-case rosters."""

import gzip
import json
from statistics import median

from prospective_small_physical import ROSTER, ROSTER_PINS, checked
from solver_transfer_budget import DATA


SOURCES = {
    "roster-savings.json": "69acdc6e9be9eefaab162bbee8df40ec4ff5d584bd1d3b279bff799a0ac4cd1d",
    "dense-full-short-raw.json.gz": "51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38",
    "quiet-cycle.json": "630281cbc0b9dc331846dd47420133843b0ae563275e413a1076ec7a4e0bfc36",
}


def short_calls_upper_bound(processed):
    # Each RF stream starts with an anchor on both radios and repeats every eight visits.
    # Sum of ceil(stream_count / 8) is at least ceil(total_processed / 8).
    return 2 * (processed - (processed + 7) // 8)


def ratios(rows, fraction, short_price_s, extra_s=0.):
    times = [r["modeled_s"] - fraction * r["short_lanes"] * short_price_s + extra_s
             if r["adjustable"] else r["modeled_s"] for r in rows]
    return (median(value / row["v3_s"] for value, row in zip(times, rows, strict=True)),
            sum(times) / sum(row["v3_s"] for row in rows))


def minimum_fraction(rows, price, extra_s):
    def passes(fraction):
        return max(ratios(rows, fraction, price, extra_s)) <= .5
    if passes(0.):
        return 0.
    if not passes(1.):
        return None
    lo, hi = 0., 1.
    for _ in range(54):
        mid = (lo + hi) / 2
        if passes(mid):
            hi = mid
        else:
            lo = mid
    return hi


def source(name):
    data = checked(DATA / name, SOURCES[name])
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)


def study():
    budgets = source("roster-savings.json")["panels"]
    dense = source("dense-full-short-raw.json.gz")
    native = dense["candidate"]["recipe"]["receiver_audit"]["native"]
    dense_calls = native["native_calls"]["short_primary"]
    prices = {"dense": native["native_cpu_ns"]["short_primary"] / (1e9 * dense_calls),
              "weak": source("quiet-cycle.json")["weak_short_cpu_s_per_call"]}
    roster = json.loads(checked(ROSTER / "panel.json", ROSTER_PINS["panel.json"]))
    assigned = [row["case"] for row in roster["cases"]]
    pairs = json.loads(checked(ROSTER / "final/decision.json", ROSTER_PINS["final/decision.json"]))["pair_sha256"]
    census = {}
    for case in assigned[:16]:
        pair = json.loads(checked(ROSTER / "publications" / case / "pair.json", pairs[case]))
        run = pair["runs"]["candidate"]["receipt"]
        if pair["candidate_specification_digest"] != "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f":
            raise ValueError("Expected the signed ALGO08v3 control")
        counts = run["counts"]
        if sum(counts.values()) != run["window_count"]:
            raise ValueError("Admission counts do not cover the recording")
        upper = short_calls_upper_bound(counts["processed"])
        exact = dense_calls if case == dense["binding"]["case"] else None
        if exact is not None and (exact > upper or 2 * counts["processed"] != sum(native["native_calls"].values())):
            raise ValueError("Native call and processed counts disagree")
        census[case] = dict(processed=counts["processed"], short_lanes=exact if exact is not None else upper,
                            exact=exact is not None, windows=run["window_count"], pair_sha256=pairs[case])
    panels = {}
    for size, panel in budgets.items():
        rows = panel["rows"]
        if [r["case"] for r in rows] != assigned[:int(size)] or any(
                r["windows"] != census[r["case"]]["windows"] for r in rows):
            raise ValueError("Modeled roster disagrees with original named assignments")
        rows = [r | census[r["case"]] for r in rows]
        prices_result = {}
        for name, price in prices.items():
            prices_result[name] = {
                "fractions_required": {str(wait): minimum_fraction(rows, price, wait) for wait in (0, .25, 1, 5)},
                "fraction_cases": {str(f): ratios(rows, f, price) for f in (.25, .375, .5)}}
        panels[size] = dict(rows=rows, prices=prices_result)
    return dict(source_sha256=SOURCES, short_call_cpu_s=prices, panels=panels)


if __name__ == "__main__":
    print(json.dumps(study(), sort_keys=True, indent=2, allow_nan=False))
