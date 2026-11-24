"""Separate failed proposals from their fallback on the frozen field schedule."""

import argparse
from collections import Counter
import json
from math import isfinite
from pathlib import Path
from statistics import median

from .ds30_oracle_routing import CAMPAIGN, PLAN, checked, digest, frozen_order
from .full_successor_score import ARMS, outcomes_summary, paired_rows, paired_timing, roster


FIRST = "sha256:db3e4869a95d2f8279873723158c4bd0e8ee93cbc228f5123ec58317712babc9"
FIRST_SEAL = "sha256:9a39a071caa2469be3aadeea358f7dc51709be55e62b03ed299d1ace7ca01818"
METRICS = ("elapsed_s", "cpu_s")


def clock(data):
    values = {m: data[m] for m in METRICS}
    if any(not isfinite(v) or v < 0 for v in values.values()):
        raise ValueError("Invalid solver stopwatch")
    return values


def route_times(witness, outcome):
    zero = dict.fromkeys(METRICS, 0.0)
    if witness["raw_route"] == "authenticated_installed_graph_ineligible":
        if outcome != "withheld" or witness.get("timing") or witness.get("ports"):
            raise ValueError("Graph-ineligible outcome has inconsistent solve evidence")
        return dict(route="before_solver", solve=zero, rejected=zero, fallback=zero)
    solve, = witness["timing"]["solve"]
    solve = clock(solve)
    history = witness["ports"]["history_risk"]
    attempts = history["lean_attempts"]
    mode = history["choice"]["route"]
    if mode == "lean":
        attempt, = attempts
        decision = attempt["decision"]
        used_fallback = decision == "fallback"
        if used_fallback != ("fallback_clocks" in attempt):
            raise ValueError("Fallback decision disagrees with the recorded enclosure")
        if decision not in ("fallback", "complete", "withheld"):
            raise ValueError("Unknown lean decision")
        before = clock(attempt["candidate_pre_evidence_clocks"]) if used_fallback else zero
        after = clock(attempt["fallback_clocks"]) if used_fallback else zero
        if any(before[m] + after[m] > solve[m] + 1e-6 for m in METRICS):
            raise ValueError("Disjoint proposal and fallback clocks exceed the whole solve")
        return dict(route="lean_then_fallback" if used_fallback else "lean_" + decision,
                    solve=solve, rejected=before, fallback=after, reason=attempt.get("reason"))
    if mode != "named" or attempts:
        raise ValueError("Unknown route or mismatched direct named call")
    return dict(route="direct_named", solve=solve, rejected=zero, fallback=zero)


def scenario(records, pieces):
    pairs = []
    removed = dict.fromkeys(METRICS, 0.)
    for a, b, route in records:
        candidate = dict(b)
        for metric in METRICS:
            saving = sum(route[piece][metric] for piece in pieces)
            removed[metric] += saving
            candidate[metric] -= saving
            if candidate[metric] <= 0:
                raise ValueError("Counterfactual exceeds the recorded end-to-end cost")
        pairs.append((a, candidate))
    return dict(removed=removed, wall=paired_timing(pairs, "elapsed_s"), cpu=paired_timing(pairs, "cpu_s"),
                wall_above_half_s=sum(b["elapsed_s"] - .5*a["elapsed_s"] for a,b in pairs))


def summarize(records):
    cases = {a["case"] for a, _, _ in records}
    arms = {}
    for arm in ARMS:
        column = arm + "_error_km"
        delta = [b[column] - a[column] for a,b,_ in records if a[column] is not None and b[column] is not None]
        arms[arm] = dict(shared=len(delta), median_error_change_km=median(delta) if delta else None)
        for i, role in enumerate(("installed", "successor")):
            measures = outcomes_summary([row[i] for row in records], cases)[arm]
            arms[arm][role] = {k: measures[k] for k in ("fixes", "within_1km", "within_2km")}
    return dict(count=len(records), slower=sum(b["elapsed_s"] > a["elapsed_s"] for a,b,_ in records),
                calibrations=arms, counterfactuals={name: scenario(records, discard) for name, discard in
                (("observed", ()), ("skip_failed_proposal", ("rejected",)), ("free_named_fallback", ("fallback",)),
                 ("both_free", ("rejected","fallback")))})


def study(snapshot, seal_pin, transfer=False):
    seal = json.loads(checked(snapshot/"rows-with-relocations-seal.json", seal_pin))
    if seal["plan_sha256"] != PLAN or (not transfer and (seal_pin != FIRST_SEAL or seal["combined_sha256"] != FIRST)):
        raise ValueError("Unexpected combined export or plan")
    plan = json.loads(checked(snapshot/"plan.json", PLAN))
    order = [row["case"] for row in frozen_order(plan)]
    target = set(order[24:27] if transfer else order[:24])
    rows = [r for line in checked(snapshot/"rows-with-relocations.jsonl", seal["combined_sha256"]).splitlines()
            if (r := json.loads(line))["case"] in target]
    if any(r["verified_pair"] is not True or r.get("relocation_proof_sha256") != seal["proofs"].get(r["case"])
           for r in rows):
        raise ValueError("Await all specified, verified original pairs")
    assigned = roster()
    matched = paired_rows(rows, {case:assigned[case] for case in target})
    routes, receipts, records = {}, {}, []
    by_key = {(r["case"], r["algorithm"]):r for r in rows}
    for a,b in matched:
        case = a["case"]
        for member in (a,b):
            r = by_key[case, member["algorithm"]]
            path = (CAMPAIGN/r["attempt"]).resolve(strict=True)
            if not path.is_relative_to(CAMPAIGN):
                raise ValueError("Attempt outside saved field campaign")
            attempt = json.loads(checked(path, r["attempt_result_sha256"]))
            if any(r[k] != attempt[k] for k in (*METRICS,"algorithm","outcome","authority_sha256","generation")):
                raise ValueError("Mismatch with the original paid attempt")
        pub = path.parent/"publication"  # The second member is always the candidate.
        marker = json.loads((pub/"algo08v3-successor-release.json").read_bytes())
        body = (pub/"exact-named-raw-witness.json").read_bytes()
        witness = json.loads(body)
        detail = witness["evidence"]["detail"]
        if (r["algorithm"] != "successor" or marker["build_sha256"] != r["build_sha256"] or
                marker["terminal_sha256"] != r["terminal_sha256"] or marker["authority_sha256"] != r["authority_sha256"] or
                marker["decision"] != r["outcome"] or detail["terminal_sha256"] != marker["terminal_sha256"] or
                detail["input_sha256"] != attempt["native_sha256"]):
            raise ValueError("Solver witness is not the selected candidate publication")
        accounting = route_times(witness, b["outcome"])
        if any(accounting["solve"][m] > b[m] for m in METRICS):
            raise ValueError("Solve cost exceeds measured end-to-end time")
        routes[case] = accounting
        receipts[case] = dict(witness=digest(body), installed=by_key[case,"installed"]["attempt_result_sha256"],
                              candidate=r["attempt_result_sha256"])
        records.append((a,b,accounting))
    classes = Counter(v["route"] for v in routes.values())
    return dict(export=seal["combined_sha256"], seal=seal_pin, receipts=receipts, routes=routes,
                all=summarize(records), by_route={key:summarize([r for r in records if r[2]["route"]==key])
                                                  for key in sorted(classes)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--seal-pin", default=FIRST_SEAL)
    parser.add_argument("--transfer", action="store_true")
    args = parser.parse_args()
    print(json.dumps(study(args.snapshot, args.seal_pin, args.transfer), sort_keys=True, allow_nan=False))
