"""Reclassify the sealed held-out odd-short forecasts using signed CFO residuals."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import sys

from . import odd_short_interpolation as odd
from directed_donor import arrival_phase


ORIGINAL_PIN = "f7c721cd320c0b002b999aff47a2b47b930a7143832e32bef7eb3bf593af11fc"
ORIGINAL_PATH = odd.HERE / "measurements/odd-short-interpolation-plan.json.gz"
PROTOCOL = odd.HERE / "held-cfo-innovation-protocol.md"
HERTZ, SAMPLES = odd.WINDOWS[0]
HASH_SEED = b"held-cfo-innovation:v1:"
CATEGORY = ("installed_empty", "wrong_cfo", "delay_only", "original_strict_hit")


def select(held, forecasts, original):
    if not forecasts.keys() <= held.keys():
        raise ValueError("Only pre-masked held visits may have forecasts")
    if any(not original[oid]["short"] for oid in held):
        raise ValueError("The pre-masked opportunities must all be short")
    positive = {oid for oid in held if original[oid]["factor"] is not None}
    differences = {oid: abs(forecasts[oid]["cfo_hz"] - original[oid]["factor"][odd.HERTZ])
                   for oid in sorted(forecasts.keys() & positive)}
    selected = [oid for oid, hz in differences.items() if hz > HERTZ]
    hashed = sorted(differences, key=lambda oid: sha256(HASH_SEED + oid.encode("ascii")).digest())
    return positive, dict(absolute_innovation_hz=differences, selected=selected,
                          equal_count_hash=hashed[:len(selected)])


def category(error):
    if error is None:
        return "installed_empty"
    if error["hz"] > HERTZ:
        return "wrong_cfo"
    return "delay_only" if error["samples"] > SAMPLES else "original_strict_hit"


def original_errors(positive, original, stock):
    all_errors = {}
    for oid in positive:
        row = original[oid]
        c = row["counter"]
        value, reference = row["factor"], stock[oid]["factor"]
        original_value = dict(cfo_hz=value[odd.HERTZ], arrival=arrival_phase(c,value))
        all_errors[oid] = odd.errors_for(original_value,c,reference) if reference is not None else None
    return all_errors


def partition(ids, errors):
    counts = Counter(category(errors[oid]) for oid in ids)
    return {name: counts[name] for name in CATEGORY}


def evaluate(ids, forecasts, errors, original, stock):
    totals = dict.fromkeys(("closer", "farther", "equal", "wrong_cfo_closer", "cfo_restored",
                            "cfo_spoiled", "strict_restored_keep_arrival", "strict_spoiled_keep_arrival",
                            "strict_restored_forecast_arrival", "strict_spoiled_forecast_arrival"),0)
    shifts = []
    for oid in ids:
        old = errors[oid]
        if old is None:
            continue
        new = odd.errors_for(forecasts[oid],original[oid]["counter"],stock[oid]["factor"])
        difference = new["hz"] - old["hz"]
        shifts.append(difference)
        totals["closer" if difference < 0 else "farther" if difference > 0 else "equal"] += 1
        old_cfo, new_cfo = old["hz"] <= HERTZ, new["hz"] <= HERTZ
        old_arrival = old["samples"] <= SAMPLES
        old_joint = old_cfo and old_arrival
        totals["wrong_cfo_closer"] += not old_cfo and difference < 0
        totals["cfo_restored"] += not old_cfo and new_cfo
        totals["cfo_spoiled"] += old_cfo and not new_cfo
        for arrival, label in ((old_arrival, "keep_arrival"), (new["samples"] <= SAMPLES, "forecast_arrival")):
            joint = new_cfo and arrival
            totals["strict_restored_" + label] += not old_joint and joint
            totals["strict_spoiled_" + label] += old_joint and not joint
    return dict(queries=len(ids), original_categories=partition(ids,errors), **totals,
                median_frequency_error_change_hz=median(shifts) if shifts else None)


def continuation(case):
    gated = case["corrections"]["innovation"]
    baseline = case["corrections"]["equal_count_hash"]
    eligible_wrong = case["eligible_categories"].get("wrong_cfo",0)
    gated_present = gated["queries"] - gated["original_categories"].get("installed_empty",0)
    if eligible_wrong < 10 or gated_present < 10:
        return "extend_sparse"
    if (gated["original_categories"].get("wrong_cfo",0) > baseline["original_categories"].get("wrong_cfo",0)
            and gated["cfo_restored"] > baseline["cfo_restored"]
            and gated["strict_restored_keep_arrival"] > gated["strict_spoiled_keep_arrival"]):
        return "extend_positive"
    return "stop"


def frozen_inputs(case, baseline):
    pair, result, native, _, clock = odd.candidate(case)
    masked, held, modes = odd.mask(native)
    frozen = baseline["cases"][case]
    if (modes != clock["native_calls"] or frozen["native_sha256"] != result["native_sha256"]
            or frozen["masked_sha256"] != odd.signed.canonical(masked)
            or frozen["held_order_sha256"] != odd.signed.canonical(list(held))):
        raise ValueError("The original blind forecast belongs to another masked Graph or detector")
    original = odd.signed.opportunities(native)
    positive, selections = select(held,frozen["proposals"],original)
    plan = dict(candidate_sha256=result["native_sha256"], original_short_calls=modes["short_primary"],
                held_lanes=len(held), held_positive_lanes=len(positive), **selections)
    return plan, positive, original, pair, result, native, frozen["proposals"]


def identity(baseline):
    if baseline["sources"] != odd.source_pins() or set(baseline["cases"]) != set(odd.CASES):
        raise ValueError("Need the exact separately sealed forecast archive")
    return dict(original_seal=ORIGINAL_PIN, protocol_sha256=odd.signed.tag(PROTOCOL.read_bytes()))


def predict(baseline):
    return dict(**identity(baseline), cases={case: frozen_inputs(case,baseline)[0] for case in odd.CASES})


def score(baseline, selection, pin):
    if any(selection[key] != value for key,value in identity(baseline).items()) or set(selection["cases"]) != set(odd.CASES):
        raise ValueError("Selection archive mismatches the frozen experiment")
    cases = {}
    for case in odd.CASES:
        plan, positive, original, pair, result, native, forecasts = frozen_inputs(case,baseline)
        if plan != selection["cases"][case]:
            raise ValueError("The score must use the sealed candidate-only selection")
        installed_pair, installed, pub = odd.original(case,"installed")
        if pair != installed_pair or installed["raw_identity"] != result["raw_identity"]:
            raise ValueError("Both detector packets must describe the same original acquisition")
        stock_native = odd.signed.read_native(pub,installed["native_sha256"])
        if stock_native["provenance"]["detector_sha256"] != "sha256:" + odd.signed.FULL:
            raise ValueError("Need the released full-aperture detector")
        stock = odd.signed.opportunities(stock_native)
        odd.signed.bind_pair(stock_native,native,stock,original)
        errors = original_errors(positive,original,stock)
        eligible = plan["absolute_innovation_hz"]
        corrections = {name: evaluate(ids,forecasts,errors,original,stock)
                       for name,ids in (("all_forecasts",eligible),("innovation",plan["selected"]),
                                        ("equal_count_hash",plan["equal_count_hash"]))}
        cases[case] = dict(candidate_sha256=result["native_sha256"], installed_sha256=installed["native_sha256"],
                           held_lanes=plan["held_lanes"], held_positive_lanes=len(positive),
                           original_short_calls=plan["original_short_calls"], eligible_positive_lanes=len(eligible),
                           untouched_positive_lanes=len(positive)-len(plan["selected"]),
                           held_positive_categories=partition(positive,errors),
                           eligible_categories=partition(eligible,errors), corrections=corrections)
    return dict(**identity(baseline), selection_sha256=pin, cases=cases,
                continuation=continuation(cases["DS30-0086"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("predict")
    scoring = sub.add_parser("score")
    scoring.add_argument("selection", type=Path)
    scoring.add_argument("sha256")
    args = parser.parse_args()
    sys.addaudithook(odd.deny_backing)
    if args.action == "predict":
        sys.addaudithook(odd.deny_installed_outcomes)
    original = odd.signed.document(ORIGINAL_PATH,ORIGINAL_PIN)
    report = (predict(original) if args.action == "predict"
              else score(original,odd.signed.document(args.selection,args.sha256),args.sha256))
    print(json.dumps(report,sort_keys=True,separators=(",",":"),allow_nan=False))
