"""Translate observed saved-publication ratios into conditional full-receiver budgets."""

import argparse
import gzip
import json
from hashlib import sha256
from math import isfinite

from acquisition_throughput import minimum_rate
from history_risk_route_panel import read_sealed_panel
from regional_dense_budget import DATA, HERE, select
from staged_budget import checked
from tools.pipeline_eval.qualification.score_paired_holdout import elapsed_ratios


RAW_CLOCKS_SHA = "fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a"


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
    rows = json.loads(checked(DATA / "acquisition-throughput.json", RAW_CLOCKS_SHA))["rows"]
    stages = json.loads(checked(HERE / "development/stages.json",
        "0bc940b1181b6fdb5f52ec1c5b768bfdbd6d2334e721fe8350cfc9ad3ca643c3"))["stages"]
    groups = {size: select(rows, [r["case"] for r in stages[size]["cases"]]) for size in ("4", "16")}
    groups["55"] = rows
    return {size: {name: receiver_budget(group, speed) for name, speed in speeds.items()}
            for size, group in groups.items()}


def matched_budget(raw, saved):
    """Transfer only the within-case saved time difference to v3's raw downstream clock."""
    acquisition, solve, tail = raw["stages"]
    named, candidate = (saved[mode]["elapsed_s"] for mode in ("named", "candidate"))
    mb = raw["compressed_MB"]
    if not all(isfinite(v) and v > 0 for v in (acquisition, solve, tail, named, candidate, mb)):
        raise ValueError("Expected complete positive acquisition, publication and byte counts")
    downstream = solve + tail - (named - candidate)
    if downstream <= 0:
        raise ValueError("Saved wall reduction exceeds original raw downstream time")
    total = acquisition + solve + tail
    available = total / 2 - downstream
    return dict(raw_v3_s=total, original_acquisition_s=acquisition, saved_improvement_s=named-candidate,
                modeled_downstream_s=downstream, acquisition_budget_s=available, compressed_MB=mb,
                required_MB_s=mb/available if available > 0 else None)


def exact_case_report(size=3):
    panels = {
        3: ("exact-named-saved-panel.json", "1b78a16f6ca23ca7dad27db73b482aeda6ab1858343118d7e9815b5a7622385b"),
        4: ("exact-named-saved-panel-four.json", "ffabb26e6e518afc44e026396efa06ce28609e1380223090bfb2bb6a85902b43"),
    }
    filename, digest = panels[size]
    panel = json.loads(checked(DATA / filename, digest))
    raw = json.loads(checked(DATA / "acquisition-throughput.json", RAW_CLOCKS_SHA))["rows"]
    prefixes = json.loads(gzip.decompress(checked(DATA / "physical-stage-envelope.json.gz",
        "f8ec74a516fe6682a3f08b133a6a3a180052734ccbcc30f4ef585d9e089d24bf")))
    cases = {}
    hashes = panel["earlier_receipts"] | {"0374": panel["dense_receipt_sha256"]}
    if size == 4:
        hashes["0402"] = panel["fourth_receipt_sha256"]
    for row in select(raw, list(panel["per_case"])):
        case = row["case"]
        content = gzip.decompress((DATA / f"exact-named-{case}.json.gz").read_bytes())
        evidence = json.loads(content)
        receipt = evidence["artifacts"]["named"]["worker"]["receipt"]
        if (sha256(content).hexdigest() != hashes[case.split("-")[1]] or not evidence["exact"]
                or receipt["session_id"] != "fast-" + row["inventory_sha256"].removeprefix("sha256:")[:32]
                or receipt["window_count"] != row["windows"] or evidence["clocks"] != panel["per_case"][case]["clocks"]):
            raise ValueError(f"Raw and saved evidence do not match for {case}")
        cases[case] = matched_budget(row, evidence["clocks"])
    verify = [a["cpu_ns"] for a in prefixes["arms"] if a["arm"] == "verify"]
    # Credit the faster CPU-only traversal with zero I/O wait and zero detector cost.
    rate = prefixes["nominal_compressed_bytes_per_arm"] * 1e3 / min(verify)
    projected = [(r["raw_v3_s"], r["modeled_downstream_s"] + r["compressed_MB"]/rate)
                 for r in cases.values()]
    median_gate, summed_gate = elapsed_ratios(projected)
    return dict(cases=cases, hypothetical_verify_only_MB_s=rate,
                median_ratio_at_verify_only_rate=median_gate, summed_ratio_at_verify_only_rate=summed_gate)


def routed_case_report(size=3):
    panel = read_sealed_panel(size)["enrolled"]
    raw = json.loads(checked(DATA / "acquisition-throughput.json", RAW_CLOCKS_SHA))["rows"]
    cases, modeled, paid_saved_pairs = {}, [], []
    for row in select(raw, ["DS30-" + key for key in panel]):
        case = row["case"]
        evidence = panel[case.removeprefix("DS30-")]
        result = evidence["result"]
        receipt = result["published"]["worker"]["receipt"]
        if (result["case"] != case or receipt["window_count"] != row["windows"]
                or receipt["session_id"] != "fast-" + row["inventory_sha256"].removeprefix("sha256:")[:32]
                or result["clock"]["exit_code"] != 0 or result["archive_stock_clock"]["exit_code"] != 0):
            raise ValueError(f"Raw and saved routed evidence do not match for {case}")
        charged = result["clock"]["elapsed_s"] + evidence["source_stage"]["preflight"]["elapsed_ns"] / 1e9
        paid_saved_pairs.append((result["archive_stock_clock"]["elapsed_s"], charged))
        budget = matched_budget(row, dict(named=result["archive_stock_clock"], candidate=dict(elapsed_s=charged)))
        cases[case] = budget
        downstream = budget["modeled_downstream_s"]
        # Preserve the measured baseline total while supplying the transferred downstream
        # clock to the same median/sum throughput solver used for the historical cohorts.
        modeled.append(dict(row, stages=(budget["raw_v3_s"] - downstream, downstream, 0)))
    median_saved, summed_saved = elapsed_ratios(paid_saved_pairs)
    return dict(cases=cases, median_gate_MB_s=minimum_rate(modeled, 1, 0),
                summed_gate_MB_s=minimum_rate(modeled, 1, 1),
                measured_saved_median_ratio=median_saved, measured_saved_summed_ratio=summed_saved)


def unseen_cut(rows, matched, rate, target):
    """Minimum uniform downstream reduction on the other split cases, for each gate."""
    if not isfinite(rate) or rate <= 0 or not 0 < target < 1:
        raise ValueError("Expected a positive acquisition rate and a target ratio between zero and one")
    parts = []
    for row in rows:
        acquisition, solve, tail = row["stages"]
        downstream = solve + tail
        original = acquisition + downstream
        # Keep the entire original clock on unsplit recordings, even when their size is known.
        if acquisition == 0:
            parts.append((original, original, 0))
        elif row["case"] in matched:
            parts.append((original, row["compressed_MB"]/rate + matched[row["case"]]["modeled_downstream_s"], 0))
        else:
            parts.append((original, row["compressed_MB"]/rate, downstream))

    def gates(cut):
        return elapsed_ratios([(v3, fixed + (1-cut)*unknown) for v3, fixed, unknown in parts])

    unchanged, ideal = gates(0), gates(1)
    costs = {}
    for index, name in enumerate(("median", "summed")):
        if unchanged[index] <= target:
            costs[name] = 0.0
        elif ideal[index] > target:
            costs[name] = None
        else:
            lo, hi = 0.0, 1.0
            for _ in range(50):
                middle = (lo+hi)/2
                if gates(middle)[index] <= target:
                    hi = middle
                else:
                    lo = middle
            costs[name] = hi
    return costs


def historical_transfer_report(size=4):
    matched = routed_case_report(size)["cases"]
    rows = json.loads(checked(DATA / "acquisition-throughput.json", RAW_CLOCKS_SHA))["rows"]
    split = [r for r in rows if r["stages"][0] > 0]
    included = select(split, list(matched))
    def duration(row):
        return sum(row["stages"])

    def downstream(row):
        return sum(row["stages"][1:])

    ranks = {row["case"]: dict(raw_time_rank=1 + sum(duration(r) < duration(row) for r in split),
                               downstream_time_rank=1 + sum(downstream(r) < downstream(row) for r in split))
             for row in included}
    return dict(recordings=len(rows), split_count=len(split), matched_ranks=ranks,
                matched_share_of_raw_elapsed=sum(map(duration, included))/sum(map(duration, rows)),
                matched_share_of_split_downstream=sum(map(downstream, included))/sum(map(downstream, split)),
                required_unseen_downstream_cut={
                    rate: {speed: unseen_cut(rows, matched, rate, 1/speed) for speed in (1.6, 2)}
                    for rate in (225, 250, 325, 375, 400)})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    kind = cli.add_mutually_exclusive_group()
    kind.add_argument("--exact-cases", type=int, nargs="?", const=3, choices=(3, 4),
                     help="Use the three- or four-recording panel's measured solver savings (default 3)")
    kind.add_argument("--routed-cases", type=int, nargs="?", const=3, choices=(3, 4, 5),
                      help="Charge orbit-risk launch checks on the selected saved panel")
    kind.add_argument("--historical-transfer", type=int, nargs="?", const=4, choices=(4, 5),
                      help="Price unmeasured downstream savings across the historical 55 after four or five cases")
    args = cli.parse_args()
    if args.historical_transfer:
        result = historical_transfer_report(args.historical_transfer)
    elif args.routed_cases:
        result = routed_case_report(args.routed_cases)
    elif args.exact_cases:
        result = exact_case_report(args.exact_cases)
    else:
        result = report()
    print(json.dumps(result, indent=2, allow_nan=False))
