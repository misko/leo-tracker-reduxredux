"""Locate the measured half-time gap in the first 71 verified DS30 pairs."""

import argparse
import json
from math import fsum, inf, isfinite
from pathlib import Path
from statistics import median

from .ds30_oracle_routing import PLAN, digest, frozen_order
from .ds30_routing_first64 import CASE_KEY, PLAN_FIELDS, restricted_json
from .field_fallback_first70 import HERE, PRODUCER, Reads, scored_pairs
from .full_successor_score import ARMS, BUILDS, PINS, VERIFIED, outcomes_summary, paired_timing


N = 71
EXPORT = "sha256:d981a774503de51fa4a814b53f7269f5ee5b4c96dead1ef4e1a6bea822039abb"
SEAL = "sha256:1e628323feaed6169df6627a8801672c519592df09285addba181171e7ba31aa"
METRICS = {"wall": "elapsed_s", "cpu": "cpu_s"}
STRATA = ("lost", "gained", "both_pass", "neither_pass", "unscored")


def loss_class(stock, candidate):
    if stock is None or candidate is None:
        return "unscored"
    return {(True, False): "lost", (False, True): "gained", (True, True): "both_pass",
            (False, False): "neither_pass"}[stock <= 1., candidate <= 1.]


def stats(pairs):
    result = dict(count=len(pairs))
    for name, metric in METRICS.items():
        signed = [b[metric] - .5 * a[metric] for a, b in pairs]
        result[name] = dict(**paired_timing(pairs, metric), installed_s=fsum(a[metric] for a, _ in pairs),
                            successor_s=fsum(b[metric] for _, b in pairs), net=fsum(signed),
                            median_deficit=median(signed) if signed else None,
                            positive=fsum(d for d in signed if d > 0), surplus=fsum(-d for d in signed if d < 0),
                            at_half=sum(d <= 0 for d in signed))
    result["at_both_halves"] = sum(all(b[k] <= .5*a[k] for k in METRICS.values()) for a, b in pairs)
    return result


def quartiles(pairs):
    ranked = sorted(pairs, key=lambda pair: pair[0]["elapsed_s"])
    return [ranked[i*len(ranked)//4:(i+1)*len(ranked)//4] for i in range(4)]


def minimum_scope(pairs, seconds):
    """Price the same proportional reduction wherever this exact scope is measured."""
    if len(pairs) % 2 != 1:
        raise ValueError("This median crossing expects an odd population")
    deficits = [b["elapsed_s"] - .5*a["elapsed_s"] for a, b in pairs]
    costs = [seconds.get(a["case"], 0) for a, _ in pairs]
    if any(not 0 <= cost < b["elapsed_s"] for (_, b), cost in zip(pairs, costs, strict=True)):
        raise ValueError("Stage is outside its paid wall enclosure")
    need = [0 if d <= 0 else d/cost if cost else inf for d, cost in zip(deficits, costs, strict=True)]
    total = fsum(costs)
    summed = max(0., fsum(deficits))/total if total else inf
    median_crossing = sorted(need)[len(pairs)//2]
    return dict(stage_s=total, eligible=sum(c > 0 for c in costs),
                first_fraction_sum=summed if isfinite(summed) else None,
                first_fraction_median=median_crossing if isfinite(median_crossing) else None,
                net_if_free=fsum(deficits)-total,
                at_half_if_free=sum(f <= 1. for f in need))


def enroll(snapshot, read):
    plan = read.load(snapshot/"plan.json", "snapshot", PLAN, cap=250_000)
    seal = read.load(snapshot/"rows-with-relocations-seal.json", "snapshot", SEAL)
    source = read.load(snapshot/"rows-with-relocations.jsonl", "snapshot", EXPORT, cap=1_400_000, raw=True)
    order = frozen_order(plan)
    if (seal["plan_sha256"] != PLAN or seal["combined_sha256"] != EXPORT
            or [e["case"] for e in order[69:71]] != ["DS30-0003", "DS30-0036"]):
        raise ValueError("Unexpected verified first-71 prefix and seal")
    entries = {row["case"]: row for row in order[:N]}
    rows = {}
    for record in restricted_json(source.splitlines(), CASE_KEY, entries):
        row = json.loads(record)
        key = row["case"], row["algorithm"]
        entry = entries[row["case"]]
        if (key in rows or row["algorithm"] not in BUILDS or row["build_sha256"] != PINS[row["algorithm"]]
                or row["verified_pair"] is not True or row["acquisition_verified"] is not True
                or row["outcome"] not in VERIFIED or row["actual_order"] != entry["order"]
                or row["first"] != entry["order"][0] or any(row[k] != entry[k] for k in PLAN_FIELDS)
                or row.get("relocation_proof_sha256") != seal["proofs"].get(row["case"])):
            raise ValueError("Selected row differs from the verified original")
        rows[key] = row, digest(record)
    if len(rows) != 2*N:
        raise ValueError("Both arms of all 71 assigned originals are required")
    return entries, rows


def audited_scopes(pairs, read):
    source = read.load(HERE/"first64-producer-transfer.json.gz", "stage_archive", PRODUCER)
    if set(row["case"] for row in source["rows"]) != {a["case"] for a, _ in pairs[:64]}:
        raise ValueError("Stage denominator differs from the verified first-64 pairs")
    archived = {row["case"]: row for row in source["rows"]}
    result = {}
    for a, b in pairs[:64]:
        row = archived[a["case"]]
        if (row["stock_result"] != a["attempt_result_sha256"]
                or row["pins"]["result"] != b["attempt_result_sha256"]
                or row["actual_wall_s"] != b["elapsed_s"]):
            raise ValueError("Measured stage belongs to another timed pair")
        acq, native, solve = (row[k] for k in ("acquisition_s", "native_detector_s", "solver"))
        if not 0 <= native <= acq or not 0 <= solve <= b["elapsed_s"] - acq:
            raise ValueError("Invalid acquisition or solver stage enclosure")
        result[a["case"]] = dict(acquisition=acq, input_other=acq-native, native=native, solver=solve,
                                 producer_cap=min(acq-native, row["worker_cpu"]), hit_bytes=row["hit_bytes"])
    return result


def report(snapshot):
    read = Reads()
    entries, rows = enroll(snapshot, read)
    pairs = scored_pairs(entries, rows, snapshot, read)
    stages = audited_scopes(pairs, read)
    phase_summary = {}
    bands = quartiles(pairs)
    scopes = [k for k in next(iter(stages.values())) if k != "hit_bytes"]
    for group, members in (("all", pairs), ("top_quartile", bands[-1])):
        positions = {a["case"] for a, _ in members}
        phase_summary[group] = {
            stage: minimum_scope(pairs, {case: costs[stage] for case, costs in stages.items() if case in positions})
            for stage in scopes}
    comparison = {arm: {label: [] for label in STRATA} for arm in ARMS}
    either_lost = []
    measurements = {}
    for a, b in pairs:
        case = a["case"]
        classes = {arm: loss_class(a[arm+"_error_km"], b[arm+"_error_km"]) for arm in ARMS}
        for arm, label in classes.items():
            comparison[arm][label].append((a, b))
        if "lost" in classes.values():
            either_lost.append((a, b))
        measurements[case] = dict(quality=classes, stage=stages.get(case), attempts={
            role: {key: member[key] for key in ("attempt_result_sha256", "outcome", *METRICS.values(),
                                               *(arm+"_error_km" for arm in ARMS))}
            for role, member in zip(BUILDS, (a, b), strict=True)})
    second = bands[1]
    acquisition_need = [(b["elapsed_s"]-.5*a["elapsed_s"])/stages[a["case"]]["acquisition"]
                        for a, b in second if a["case"] in stages]
    read.bytes["reference_export"] = read.bytes.pop("six_case_survey")
    return dict(plan=PLAN, export=EXPORT, seal=SEAL, cases=list(entries), all=stats(pairs),
                baseline_wall_quartiles=[dict(cases=[a["case"] for a, _ in group],
                                              range_s=[group[i][0]["elapsed_s"] for i in (0, -1)],
                                              measures=stats(group)) for group in bands],
                quality={arm: {label: stats(group) for label, group in groups.items()}
                         for arm, groups in comparison.items()}, either_lost=stats(either_lost),
                accuracy={role: outcomes_summary([pair[i] for pair in pairs], entries) for i, role in enumerate(BUILDS)},
                paid_scope_sensitivity=phase_summary, second_quartile_acquisition=dict(
                    audited=len(acquisition_need), median_fraction_to_half=median(acquisition_need)),
                measurements=measurements, read_bytes=dict(read.bytes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    print(json.dumps(report(args.snapshot), sort_keys=True, allow_nan=False, indent=2))
