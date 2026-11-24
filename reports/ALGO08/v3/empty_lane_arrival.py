"""Score joint carrier and arrival proposals on the receiver's original empty short lanes."""

import argparse
from collections import Counter
import json
from math import isfinite, remainder
from pathlib import Path
from statistics import median
import sys

from .directed_donor import ADC, PERIOD, arrival_phase
from .missed_owner_support import (ARMS, COHORTS, FIELD, FIRST30, HERTZ, candidate_packet, named_rows,
                                   original_pairs, saved_only, signed, signed_attempt)


WINDOWS = {"primary": (250., 2.), "historical_tight": (400., 1.), "historical_loose": (2250., 6.),
           "wider_timing": (250., 128.)}
PHASES = ("interpolated", "left_only", "quarter_period_control")


def phases(left, target_counter, right):
    """Interpolate physical arrival phase without converting large counters into floats."""
    start, stop = left["counter"], right["counter"]
    if not start < target_counter < stop:
        raise ValueError("The candidate neighbors must strictly bracket the target in hardware time")
    a = arrival_phase(start, left["factor"])
    b = arrival_phase(stop, right["factor"])
    if not isfinite(a) or not isfinite(b):
        raise ValueError("Expected finite observed frame epochs")
    fraction = (target_counter-start)/(stop-start)
    predicted = (a + fraction * remainder(b-a, PERIOD)) % PERIOD
    return dict(interpolated=predicted, left_only=a, quarter_period_control=(predicted+PERIOD/4) % PERIOD)


def hits(queries, observed_hz, observed_phase, frequency_limit, phase_limit):
    """Union of complete hypotheses. Carrier and phase must agree on the same bracket."""
    result = dict.fromkeys(("carrier_only", *PHASES), False)
    for query in queries:
        if not any(abs(hz-observed_hz) <= frequency_limit for hz in query["centers_hz"]):
            continue
        result["carrier_only"] = True
        for method in PHASES:
            result[method] |= abs(remainder(query["phase"][method]-observed_phase, PERIOD)) <= phase_limit
    return result


def prepare(plan, candidate):
    """Bind every proposed epoch to its original observed neighbor before scoring."""
    out, delays = {}, []
    empty = {oid for oid, r in candidate.items() if r["short"] and r["factor"] is None}
    if len(empty) != plan["empty_short_count"] or not plan["opportunities"].keys() <= empty:
        raise ValueError("Plan differs from actual empty short lanes")
    for oid, target in plan["opportunities"].items():
        if target["status"] != "unique_signed_bracket":
            continue
        lane = candidate[oid]
        counter = target["counter"]
        if counter != lane["counter"] or oid != target["observation_id"] or lane["radio"] != target["radio"]:
            raise ValueError("Candidate target window identity changed")
        bracket, = target["brackets"]
        center, = bracket["signed_centers_hz"]
        for endpoint in ("left", "right"):
            donor = bracket[endpoint]
            ref = candidate[donor["observation_id"]]
            factor = ref["factor"]
            if (ref["counter"] != donor["counter"] or ref["radio"] != lane["radio"]
                    or any(ref["row"][key] != lane["row"][key] for key in ("edge","channel","actual_rf_hz"))
                    or factor is None or factor[HERTZ] != donor["signed_cfo_hz"]
                    or any(factor[key] != donor[key] for key in ("integer_epoch_sample","fractional_epoch_offset_samples"))):
                raise ValueError("A phase donor differs from its signed candidate window")
        left, right = (candidate[bracket[key]["observation_id"]] for key in ("left","right"))
        weight = (counter-left["counter"])/(right["counter"]-left["counter"])
        if weight != bracket["right_weight"] or not isfinite(center):
            raise ValueError("Interpolation weight or signed CFO changed")
        out[oid] = dict(centers_hz=[center], phase=phases(left, counter, right))
        delays.append((right["counter"]-counter)/ADC)
    return empty, out, dict(queries=len(out), projection_sha256=signed.canonical(out),
                            right_neighbor_median_s=median(delays) if delays else None,
                            right_neighbor_max_s=max(delays, default=None))


def score_group(empty, predictions, installed, owner_ids=None):
    missing = {oid for oid in empty if installed[oid]["factor"] is not None}
    targets = missing if owner_ids is None else missing.intersection(owner_ids)
    result = dict(installed_positive_denominator=len(targets), installed_positive_queries=len(targets & predictions.keys()))
    by_window = {}
    for label, (hz, samples) in WINDOWS.items():
        count = Counter(dict.fromkeys(("carrier_only", *PHASES), 0))
        for oid in targets.intersection(predictions):
            lane = installed[oid]
            factor = lane["factor"]
            count.update(hits([predictions[oid]], factor[HERTZ], arrival_phase(lane["counter"],factor), hz, samples))
        by_window[label] = dict(count)
    result["windows"] = by_window
    return result


def run(snapshot, paths, expected, seal=None):
    totals = {}
    for cohort, cases in COHORTS.items():
        plan = signed.document(paths[cohort], expected[cohort])
        if plan["ledger_sha256"] != FIRST30 or plan["cohort"] != cohort:
            raise ValueError("Input belongs to a different study")
        rows = original_pairs(snapshot, cohort)
        for case in cases:
            c = plan["cases"][case]
            result, native, candidate, _ = candidate_packet(rows[case,"successor"])
            if c["candidate_native_sha256"] != result["native_sha256"]:
                raise ValueError("Changed candidate input")
            empty, predictions, proof = prepare(c, candidate)
            proof.update(empty_short=len(empty), candidate_sha256=result["native_sha256"])
            if seal is None:
                totals[case] = proof
                continue
            if seal["prediction_inputs"] != expected or seal["cases"][case] != proof:
                raise ValueError("Queries must reproduce the pre-reference phase predictions")
            entry = rows[case,"installed"]
            old = signed_attempt(FIELD, entry)
            stock = signed.read_native((FIELD/entry["attempt"]).parent/"publication", old["native_sha256"])
            if old["raw_identity"] != result["raw_identity"] or stock["provenance"]["detector_sha256"] != "sha256:"+signed.FULL:
                raise ValueError("Expected the signed original full receiver on the same input")
            installed = signed.opportunities(stock)
            signed.bind_pair(stock, native, installed, candidate)
            overall = score_group(empty, predictions, installed)
            exact = named_rows(case, old)
            owners = signed.owners(exact, old["evidence"]["owners"]) if exact else None
            totals[case] = dict(**proof, installed_sha256=old["native_sha256"], all_missing=overall,
                                installed_empty_queries=len(predictions)-overall["installed_positive_queries"],
                                owners={arm:score_group(empty, predictions, installed, owners[arm])
                                        for arm in ARMS} if owners is not None else None)
    return dict(prediction_inputs=expected, ledger_sha256=FIRST30, cases=totals)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot", type=Path)
    for name in COHORTS:
        p.add_argument("--"+name, type=Path, required=True)
        p.add_argument("--"+name+"-sha256", required=True)
    p.add_argument("--seal", type=Path)
    p.add_argument("--seal-sha256")
    args = p.parse_args()
    if bool(args.seal) != bool(args.seal_sha256):
        p.error("Must specify both the phase seal and its digest or neither")
    sys.addaudithook(lambda event, params: saved_only(event, params, prediction=args.seal is None))
    seal = signed.document(args.seal, args.seal_sha256) if args.seal else None
    scores = run(args.snapshot, {k:getattr(args,k) for k in COHORTS},
                 {k:getattr(args,k+"_sha256") for k in COHORTS}, seal)
    if seal:
        scores["phase_seal_sha256"] = args.seal_sha256
    print(json.dumps(scores, indent=2, sort_keys=True, allow_nan=False))
