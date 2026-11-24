"""Seal exact charted second-screen counts before joining the verified field outcomes."""

import argparse
from collections import Counter
from fractions import Fraction
from itertools import combinations
import json
from math import fsum, sqrt
from pathlib import Path
from statistics import median

from .ds30_grid_triage import (
    ARMS, BUILDS, CAMPAIGN, OFFER, PINS, RAW_FIELDS, REFERENCE, case_group, paired_rows, roster,
    selected_rows, verified_attempt, verified_capture, verified_overlay,
)
from .ds30_oracle_routing import PLAN, checked, digest, frozen_order


CONTROLS = {
    "DS30-0220": "sha256:b8be7fef63a425d3fd15de1ca206f6ec40be65b96afa8d114fb0e8808c8a36eb",
    "DS30-0086": "sha256:5d775bbb9ff01ca9943c8001ed316cd2d65925da8348368452ddd8c0855ae084",
}
FIRST30 = "sha256:2994fe3bd068dc661fb7c4a6f9667e370218acae226106f7dd0b05636d71f8c5"
NEXT = ("DS30-0067", "DS30-0413")
SCREEN_SOURCES = tuple(f"reports/ALGO08/v3/{name}.py" for name in
                       ("history_risk_route", "blind_joint_route", "blind_joint_finish",
                        "certified_salvage", "lighter_joint_estimator"))
PROTOCOL = Path(__file__).with_name("ds30-second-screen-attrition-protocol.md")
THRESHOLD = Fraction(1, 10)


def inputs(campaign, snapshot, cohort):
    plan = json.loads(checked(snapshot/"plan.json", PLAN))
    offer = json.loads(checked(campaign/"offer.json", "sha256:"+OFFER))
    seal_body = (snapshot/"rows-with-relocations-seal.json").read_bytes()
    seal = json.loads(seal_body)
    combined = seal["combined_sha256"]
    order = frozen_order(plan)
    if (seal["plan_sha256"] != PLAN or order[29]["case"] != "DS30-0238"
            or tuple(e["case"] for e in order[30:32]) != NEXT
            or (cohort == "first30" and combined != FIRST30)):
        raise ValueError("Expected the frozen assigned original cohort")
    entries = order[:30] if cohort == "first30" else order[30:32]
    rows = selected_rows(checked(snapshot/"rows-with-relocations.jsonl", combined), tuple(e["case"] for e in entries))
    build = json.loads(checked(campaign/"frozen-build/build.json", PINS["successor"]))
    pins = dict(plan=PLAN, combined=combined, seal=digest(seal_body), build=PINS["successor"], offer="sha256:"+OFFER,
                sealed_ordinary=seal["ledger_snapshot_sha256"], protocol=digest(PROTOCOL.read_bytes()),
                source=digest(Path(__file__).read_bytes()), screen_sources={key: build["sources"][key] for key in SCREEN_SOURCES})
    return entries, rows, offer, seal, pins


def measured_screen(support):
    """Read the common pre-repair measurement mask counters, including exact structural zero."""
    keys = ("initial_curved", "full_curved", "rechecked_curved")
    if not all(type(support.get(key)) is int for key in keys):
        return None
    initial, full, kept = (support[key] for key in keys)
    restored = support.get("curved_restored")
    if "curved_restored" not in support and full == initial and support.get("cold_rejected_tracks") == []:
        restored = 0
    rejects = support.get("second_curved_rejections")
    if type(restored) is not int or not isinstance(rejects, list):
        return None
    entered = initial + restored
    if not (0 < initial <= entered <= full and 0 <= kept <= entered) or restored < 0:
        return None
    removed = entered-kept
    if bool(rejects) != bool(removed):
        return None
    return dict(entered=entered, retained=kept, dropped=removed, initial=initial, restored=restored)


def read_witness(result, root, offer, source_pins, development=None):
    raw = result["raw_identity"]
    evidence = result["evidence"]
    receipt = evidence["receipt"]
    if raw["region_sha256"].removeprefix("sha256:") != OFFER or receipt.get("region") != offer:
        return dict(state="different_offer")
    witness_path = root/"exact-named-raw-witness.json"
    if not witness_path.is_file():
        return dict(state="missing_witness")
    body = witness_path.read_bytes()
    pin = digest(body)
    witness = json.loads(body)
    detail = witness["evidence"]["detail"]
    if (detail["terminal_sha256"] != receipt.get("terminal_sha256") or detail["input_sha256"] != result["native_sha256"]
            or detail["session_id"] != raw["session_id"] or detail["raw_authority"] != evidence["raw_authority"]
            or detail["region"] != offer or detail["state"] != result["outcome"]
            or (result["outcome"] == "complete" and witness["evidence"]["owner_maps"] != evidence["owners"])
            or (development is not None and development != pin)):
        return dict(state="unbound_witness")
    meta = dict(witness=pin, native=result["native_sha256"], terminal=detail["terminal_sha256"])
    risk = (witness.get("ports") or {}).get("history_risk")
    if risk is None:
        return meta | dict(state="screen_not_run", route=witness["raw_route"])
    if (any(witness["source_sha256"].get(key) != val for key, val in source_pins.items())
            or witness["solver_recipe"]["archive_sha256"] != raw["archive_sha256"]
            or risk["choice"].get("census", {}).get("cutoff_utc_ns") != raw["causal_cutoff_utc_ns"]):
        return meta | dict(state="unbound_screen_source")
    attempts = risk.get("lean_attempts", [])
    if not attempts:
        return meta | dict(state="screen_not_run", route=risk["choice"]["route"])
    if len(attempts) != 1 or risk["choice"]["route"] != "lean":
        return meta | dict(state="ambiguous_screen_attempt", attempts=len(attempts))
    attempt, = attempts
    repair = attempt.get("repair", {}).get("status")
    origin = attempt.get("decision")
    if origin == "complete" and repair == "complete":
        route = "accepted_repair"
    elif origin == "complete" and attempt.get("provisional_salvage", {}).get("status") == "adopted":
        route = "adopted_provisional_salvage"
    elif origin == "complete":
        route = "complete_without_repair"
    else:
        route = origin
    meta |= dict(route=route, repair=repair, fallback_clocks=attempt.get("fallback_clocks"))
    signal = measured_screen(attempt.get("support", {}))
    if signal is None:
        return meta | dict(state="exact_screen_counts_unavailable")
    return meta | dict(state="measured", counts=signal)


def predict(campaign, snapshot, cohort):
    entries, rows, offer, seal, pins = inputs(campaign, snapshot, cohort)
    overlay = verified_overlay(campaign, seal) if cohort == "first30" else None
    records = []
    for entry in entries:
        case = entry["case"]
        base = dict(case=case, development_control=case in CONTROLS)
        group = case_group(campaign, entry, rows[case], overlay)
        if group is None:
            records.append(base | dict(state="pair_pending"))
            continue
        row = rows[case]["successor"]
        candidate, root = verified_attempt(campaign, group, row)
        values = read_witness(candidate, root, offer, pins["screen_sources"], CONTROLS.get(case))
        records.append(base | values | dict(pair=group[2], attempt=row["attempt_result_sha256"], outcome=candidate["outcome"]))
    return dict(cohort=cohort, pins=pins, rows=records, retry_fraction=[THRESHOLD.numerator, THRESHOLD.denominator])


def attrition(row):
    counts = row["signal"].get("counts")
    return None if counts is None else Fraction(counts["dropped"], counts["entered"])


def concordance(rows):
    counts = Counter()
    for (x, y), (u, v) in combinations(rows, 2):
        a, b = (x > u)-(x < u), (y > v)-(y < v)
        label = ("both_tied" if a == b == 0 else "signal_tied" if a == 0 else "error_tied" if b == 0
                 else "concordant" if a == b else "discordant")
        counts[label] += 1
    good, bad = (counts[key] for key in ("concordant", "discordant"))
    denom = sqrt((good + bad + counts["signal_tied"])*(good + bad + counts["error_tied"]))
    return dict(n=len(rows), tau_b=(good-bad)/denom if denom else None,
                **{k: counts[k] for k in ("concordant", "discordant", "signal_tied", "error_tied", "both_tied")})


def ranking(rows, arm):
    pairs = []
    for row in rows:
        x = attrition(row)
        stock, candidate = (row[role][arm+"_error_km"] for role in BUILDS)
        if None not in (x, stock, candidate):
            pairs.append((x, stock, candidate))
    return dict(excess=concordance([(x, b-a) for x, a, b in pairs]),
                absolute_installed=concordance([(x, a) for x, a, _ in pairs]),
                absolute_candidate=concordance([(x, b) for x, _, b in pairs]))


def retry_policy(rows):
    hits = {row["case"] for row in rows if (value := attrition(row)) is not None and value >= THRESHOLD}
    routed = [(row, row["installed"] if row["case"] in hits else row["successor"]) for row in rows]
    summary = dict(retried=[r["case"] for r in rows if r["case"] in hits], clocks={}, outcomes={})
    if not rows:
        return summary
    for key in ("elapsed_s", "cpu_s"):
        stock = fsum(row["installed"][key] for row in rows)
        candidate = fsum(row["successor"][key] for row in rows)
        paid = fsum(row["installed"][key] for row in rows if row["case"] in hits)
        summary["clocks"][key] = dict(installed_s=stock, candidate_s=candidate, replay_s=paid, total_s=candidate+paid,
                                      sum_ratio=(candidate+paid)/stock, median_ratio=median(
                                          row["successor"][key]/row["installed"][key] + (row["case"] in hits) for row in rows))
    for arm in ARMS:
        totals = {role: [r[role][arm+"_error_km"] for r in rows] for role in BUILDS}
        totals["retry"] = [value[arm+"_error_km"] for _, value in routed]
        summary["outcomes"][arm] = {role: dict(fixes=sum(x is not None for x in values),
                                              within_1km=sum(x is not None and x <= 1 for x in values),
                                              within_2km=sum(x is not None and x <= 2 for x in values))
                                    for role, values in totals.items()}
    return summary


def score(campaign, snapshot, path, pin):
    prediction = json.loads(checked(path, pin))
    cohort = prediction["cohort"]
    entries, rows, _, seal, pins = inputs(campaign, snapshot, cohort)
    if (prediction["pins"] != pins or prediction["retry_fraction"] != [THRESHOLD.numerator, THRESHOLD.denominator]
            or [m["case"] for m in prediction["rows"]] != [e["case"] for e in entries]):
        raise ValueError("Expected the independently sealed attrition forecast")
    overlay = verified_overlay(campaign, seal) if cohort == "first30" else None
    assigned = roster()
    records, excluded = [], {}
    for mark, entry in zip(prediction["rows"], entries, strict=True):
        case = entry["case"]
        if mark["state"] == "pair_pending":
            excluded[case] = "pair_pending"
            continue
        group = case_group(campaign, entry, rows[case], overlay)
        if group[2] != mark["pair"] or mark["attempt"] != rows[case]["successor"]["attempt_result_sha256"]:
            raise ValueError("Forecast charted witness disagrees with the paid pair")
        stock, candidate = (verified_attempt(campaign, group, rows[case][role])[0] for role in BUILDS)
        a, b = (worker["raw_identity"] for worker in (stock, candidate))
        if any(a[k] != b[k] for k in (*RAW_FIELDS, "region_sha256")) or a["region_sha256"].removeprefix("sha256:") != OFFER:
            excluded[case] = "raw_or_offer_mismatch"
            continue
        verified_capture(campaign, entry, rows[case], assigned[case], overlay)
        ((a, b),) = paired_rows(rows[case].values(), {case: assigned[case]})
        keep = ("elapsed_s", "cpu_s", "outcome", "timing_scope", *(arm+"_error_km" for arm in ARMS))
        records.append(dict(case=case, signal=mark, installed={k: a[k] for k in keep}, successor={k: b[k] for k in keep}))
    data = [r for r in records if r["case"] not in CONTROLS]
    controls = [r for r in records if r["case"] in CONTROLS]
    routes = sorted({r["signal"].get("route") or "unavailable" for r in data})
    return dict(cohort=cohort, prediction=pin, reference=REFERENCE, excluded=excluded, controls=controls, records=data,
                applicability=dict(Counter(r["signal"]["state"] for r in data)),
                outcomes={role: dict(Counter(r[role]["outcome"] for r in data)) for role in BUILDS},
                rank={arm: ranking(data, arm) for arm in ARMS},
                routes={route: {arm: ranking([r for r in data if (r["signal"].get("route") or "unavailable") == route], arm)
                                for arm in ARMS} for route in routes},
                policy=retry_policy(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--campaign", type=Path, default=CAMPAIGN)
    parser.add_argument("--cohort", choices=("first30", "next2"), default="first30")
    parser.add_argument("--score", nargs=2, metavar=("SEALED_PREDICTION", "SHA256"))
    args = parser.parse_args()
    if args.score:
        path, pin = args.score
        result = score(args.campaign, args.snapshot, Path(path), pin)
    else:
        result = predict(args.campaign, args.snapshot, args.cohort)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
