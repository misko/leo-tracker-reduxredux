"""Score a past-only short CFO offset inferred from original full anchors."""

import argparse
from collections import Counter, defaultdict, deque
import json
from math import isfinite, remainder, sqrt
from pathlib import Path
from statistics import fmean, median
import sys

from .calibration_transport import FIELD, FIRST30, signed_attempt
from .capped_revisit import HERTZ, SAMPLE_RATE, STREAM, candidate_packet, forecast, saved_only, signed
from .ds30_paired_inputs import checked, digest
from signed_cfo_time import ALIAS, epoch


HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"
CASES = {"development": ("DS30-0049",), "held": ("DS30-0086", "DS30-0220", "DS30-0407")}
FREQUENCY_LIMIT = 250.
AGE_LIMIT = 2*SAMPLE_RATE
FACTORIAL = "4af8b73101dce9b71a06b38a10e2484ef04b74f42b5221cfec1e818d21ea3b58"
FIRST30_AGREEMENT = "c9f14a2380f5d1fc58cefdeaf03ff40368b73f1f5beefc921f0a84d016863ed8"


def infer_offsets(opportunities):
    history = defaultdict(lambda: deque(maxlen=12))
    calibration = {}
    anchors, offsets = {}, {}
    audit = Counter()
    for oid, lane in opportunities.items():
        key = tuple(lane["row"][field] for field in STREAM)
        past = history[key]
        now, short, factor = lane["counter"], lane["short"], lane["factor"]
        if (len(lane["row"]["candidates"]) != int(factor is not None) or (past and now <= past[-1][0])
                or (factor is not None and not all(isfinite(x) for x in (factor[HERTZ], epoch(factor))))):
            raise ValueError("Expected an original ordered, finite singleton-factor stream")
        if not short:
            audit["full_lanes"] += 1
            calibration.pop(key, None)
            if factor is not None:
                audit["full_positives"] += 1
                if factor["candidate_rank"] == 0:
                    audit["rank_zero_full_positives"] += 1
                    predicted = forecast(past, now)
                    if predicted is not None:
                        audit["rank_zero_with_forecast"] += 1
                        innovation = factor[HERTZ]-predicted[0]
                        anchors[oid] = innovation
                        if abs(innovation) <= FREQUENCY_LIMIT:
                            audit["eligible_full_anchors"] += 1
                            calibration[key] = now, .5*innovation, oid
        elif factor is not None:
            audit["short_positives"] += 1
            record = calibration.get(key)
            if record is not None and 0 < now-record[0] <= AGE_LIMIT:
                audit["short_after_calibrated_anchor"] += 1
                predicted = forecast(past, now)
                if predicted is not None and abs(factor[HERTZ]-predicted[0]) <= FREQUENCY_LIMIT:
                    offsets[oid] = [record[1], record[2]]
        # A full visit is a timed empty for the past short-only trajectory, not a short CFO operand.
        past.append((now, factor[HERTZ] if short and factor is not None else None))
    return dict(counts=dict(audit), anchor_innovations_hz=anchors, short_offsets=offsets)


def original_pairs(snapshot, cohort):
    raw = checked(snapshot / "rows-with-relocations.jsonl", FIRST30)
    cases = CASES[cohort]
    rows = [x for line in raw.splitlines() if (x := json.loads(line))["verified_pair"] is True and x["case"] in cases]
    by_key = {(x["case"], x["algorithm"]): x for x in rows}
    if (len(rows) != len(cases)*2 or set(by_key) != {(c, m) for c in cases for m in ("installed", "successor")}):
        raise ValueError("Need the exact sealed original case pair for each enrolled recording")
    return by_key


def predict(snapshot, cohort):
    pairs = original_pairs(snapshot, cohort)
    cases = {}
    for case in CASES[cohort]:
        row = pairs[case, "successor"]
        result, _, opportunities, _ = candidate_packet(row)
        cases[case] = dict(infer_offsets(opportunities), candidate_result_sha256=row["attempt_result_sha256"],
                           candidate_native_sha256=result["native_sha256"])
    return dict(cohort=cohort, ledger_sha256=FIRST30, cases=cases,
                protocol_sha256=digest((HERE / "anchor-cfo-innovation-protocol.md").read_bytes()))


def compare_errors(values):
    if not values:
        return None
    absolute = sorted(map(abs, values))
    p = .95*(len(absolute)-1)
    lo = int(p)
    p95 = absolute[lo]+(p-lo)*(absolute[min(lo+1, len(absolute)-1)]-absolute[lo])
    return dict(n=len(values), mean_signed_hz=fmean(values), mae_hz=fmean(absolute), median_absolute_hz=median(absolute),
                p95_absolute_hz=p95, rms_hz=sqrt(fmean(x*x for x in values)), over_150_hz=sum(v>150 for v in absolute),
                over_250_hz=sum(v>250 for v in absolute))


def paired_measurements(installed, candidate, offsets):
    same_epoch, strict, foldable = "epoch_close", "strict", "foldable_aliases"
    observed = {name: [] for name in (same_epoch, strict, foldable)}
    membership = Counter()
    for oid, lane in candidate.items():
        original, measured = installed[oid]["factor"], lane["factor"]
        if not lane["short"] or measured is None:
            continue
        update = offsets.get(oid)
        if original is None:
            membership["candidate_without_installed"] += 1
            membership["corrected_without_installed"] += update is not None
            continue
        before = measured[HERTZ]-original[HERTZ]
        after = before+update[0] if update is not None else before
        membership["both_selected"] += 1
        if abs(epoch(measured)-epoch(original)) <= 2:
            row = (before, after, update is not None)
            observed[same_epoch].append(row)
            if abs(before) <= FREQUENCY_LIMIT:
                observed[strict].append(row)
            elif abs(remainder(before, ALIAS)) <= FREQUENCY_LIMIT:
                observed[foldable].append(row)
    membership["corrected_without_strict_pair"] = len(offsets)-sum(use for _,_,use in observed[strict])
    return observed, dict(membership)


def summarize(pairs):
    result = {}
    for label, observations in pairs.items():
        corrected = [(a, b) for a, b, used in observations if used]
        report = result[label] = {"n_corrected": len(corrected)}
        for name, values in (("all", [(a,b) for a,b,_ in observations]), ("corrected_only", corrected)):
            a = compare_errors([a for a, _ in values])
            b = compare_errors([b for _, b in values])
            report[name] = dict(before=a, after=b, fractional_mae_gain=(a["mae_hz"]-b["mae_hz"])/a["mae_hz"]
                                if a and a["mae_hz"] else None,
                                closer=sum(abs(y)<abs(x) for x,y in values), farther=sum(abs(y)>abs(x) for x,y in values))
    return result


def earlier_paid_pairs(development, innovations):
    raw = signed.document(DATA / "ds30-0049-receiver-factorial.json.gz", FACTORIAL)
    paid = raw["native-rows.json"]["document"]
    index = {(row["counter"], row["radio"]): (oid, row) for oid, row in development.items()}
    stats, differences, errors, compatible_errors = Counter(), [], [], []
    for row in paid:
        if row["anchor"]:
            stats["full_anchor_lanes"] += 1
            meta = row["opportunity"]
            oid, lane = index[meta["valid_start_counter"], meta["receiver_id"]]
            left, right = ({k:v for k,v in r.items() if k != "candidates"} for r in (meta, lane["row"]))
            full = signed.winner({"candidates":row["alternatives"]["20-two"]})
            short = signed.winner({"candidates":row["alternatives"]["8-primary"]})
            if lane["short"] or left != right or lane["factor"] != full:
                raise ValueError("The separately paid native anchors do not reproduce the original mixed anchors")
            stats["short_nonempty"] += short is not None
            stats["full_nonempty"] += full is not None
            if full is None or short is None:
                continue
            stats["both_nonempty"] += 1
            observed = full[HERTZ]-short[HERTZ]
            if abs(observed) > FREQUENCY_LIMIT or abs(epoch(full)-epoch(short)) > 2:
                continue
            stats["coincident_20_and_8_positives"] += 1
            if oid in innovations:
                estimate = innovations[oid]
                stats["coincident_with_previous_short_forecast"] += 1
                stats["equal_sign"] += (estimate>0) == (observed>0)
                differences.append(observed)
                errors.append(estimate-observed)
                if abs(estimate) <= FREQUENCY_LIMIT:
                    stats["coincident_and_passes_innovation_gate"] += 1
                    stats["compatible_equal_sign"] += (estimate>0) == (observed>0)
                    compatible_errors.append(estimate-observed)
    return dict(counts=dict(stats), paid_delta_on_coincident_forecast_rows=compare_errors(differences),
                extrapolated_delta_disagreement_hz=compare_errors(errors),
                compatible_extrapolated_delta_disagreement_hz=compare_errors(compatible_errors), source_sha256=FACTORIAL)


def ordinary_anchor_census():
    agreement = signed.document(DATA / "first30-native-agreement.json.gz", FIRST30_AGREEMENT)
    counts = Counter()
    for row in agreement["cases"]:
        counts.update(row["counts"]["anchor"])
    return dict(signed_cases=len(agreement["cases"]), known_same_window_short_operands=0,
                counts=dict(counts), source_sha256=FIRST30_AGREEMENT)


def score(snapshot, path, sha):
    frozen = signed.document(path, sha)
    cohort = frozen["cohort"]
    if frozen != predict(snapshot, cohort):
        raise ValueError("The sealed candidate-only predictions changed")
    rows, reports = original_pairs(snapshot, cohort), {}
    combined = defaultdict(list)
    paid_control = None
    for case in CASES[cohort]:
        entry = rows[case, "installed"]
        old = signed_attempt(FIELD, entry)
        new, native, candidate, _ = candidate_packet(rows[case, "successor"])
        installed = signed.read_native((FIELD / entry["attempt"]).parent / "publication", old["native_sha256"])
        if old["raw_identity"] != new["raw_identity"] or installed["provenance"]["detector_sha256"] != "sha256:"+signed.FULL:
            raise ValueError("The installed packet binds a different signed original")
        stock = signed.opportunities(installed)
        signed.bind_pair(installed, native, stock, candidate)
        plan = frozen["cases"][case]
        measured, membership = paired_measurements(stock, candidate, plan["short_offsets"])
        for label, values in measured.items():
            combined[label].extend(values)
        reports[case] = dict(metrics=summarize(measured), membership=membership, prediction_counts=plan["counts"],
                             installed_native_sha256=old["native_sha256"], n_offsets=len(plan["short_offsets"]))
        if case == "DS30-0049":
            paid_control = earlier_paid_pairs(candidate, plan["anchor_innovations_hz"])
    pooled = summarize(combined)
    advances = cohort == "held" and (pooled["strict"]["corrected_only"]["fractional_mae_gain"] or 0) >= .05
    for case in reports.values():
        strict = case["metrics"]["strict"]
        score_ = strict["corrected_only"]
        advances &= (strict["n_corrected"] >= 30 and score_["fractional_mae_gain"] is not None
                     and score_["fractional_mae_gain"] > 0
                     and score_["after"]["p95_absolute_hz"] <= score_["before"]["p95_absolute_hz"])
    return dict(cohort=cohort, advances=advances, prediction_sha256=sha, cases=reports, pooled=pooled,
                ordinary_anchor_census=ordinary_anchor_census(), separately_paid_anchor_control=paid_control)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("export", type=Path)
    actions = cli.add_subparsers(dest="action", required=True)
    actions.add_parser("predict").add_argument("cohort", choices=CASES)
    compare = actions.add_parser("score")
    compare.add_argument("prediction", type=Path)
    compare.add_argument("sha256")
    args = cli.parse_args()
    sys.addaudithook(lambda event, values: saved_only(event, values, prediction=args.action == "predict"))
    result = predict(args.export, args.cohort) if args.action == "predict" else score(args.export, args.prediction, args.sha256)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
