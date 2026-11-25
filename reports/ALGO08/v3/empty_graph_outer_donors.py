"""Screen original empty-lane queries using two original donors on each side."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import isfinite, remainder
from pathlib import Path
from statistics import median
import sys

from .calibration_transport import FIELD, FIRST30, signed_attempt
from .capped_revisit import HERTZ, candidate_packet, saved_only, signed
from .directed_donor import ADC, LOOSE, PERIOD, PHASE_LIMIT, arrival_phase
from .ds30_paired_inputs import digest
from .empty_graph_rescue import stream
from .empty_lane_arrival import prepare, score_group
from .track_cfo_denoise import COHORTS, DATA, HERE, graph_pins, original_pairs
from satellite_set_transfer import named_rows
from signed_cfo_time import ARMS


PLAN_PINS = {"development": "adcde673c80fd9a58a81380b90795b6e844f6f9ad236c945e83d4bdbc07354d3",
             "held": "b0e349e702dabf6743c7640156c5fd5cb9ea6f6b3291b0097d4da4af9b7851c5"}
PLANS = {"development": DATA / "empty-graph-rescue-development-plan.json.gz",
         "held": Path("/srv/postgres-nvme/leo-ds30-research-worktrees/ds30-empty-graph-rescue-evidence/"
                      "empty-graph-rescue-held-plan.json.gz")}
PHASE_SEAL = "9971473052ea2c2d9b2f8db1a82e45f82fcd19f5c165af30dc6c351f361829f9"
HASH_SEED = b"empty-outer-donors:v1:"


def side_at(left, right, target):
    a, b = left["counter"], right["counter"]
    if not (a < b < target or target < a < b):
        raise ValueError("Both forecast donors must be on the same strict side")
    dt = (b-a)/ADC
    fa, fb = (row["factor"][HERTZ] for row in (left,right))
    pa, pb = (arrival_phase(row["counter"],row["factor"]) for row in (left,right))
    if not all(map(isfinite,(fa,fb,pa,pb))):
        return None, "nonfinite"
    step = remainder(pb-pa, PERIOD)
    if abs(fb-fa) > 8_000*dt:
        return None, "carrier_rate"
    if abs(step) > PHASE_LIMIT*dt:
        return None, "phase_rate"
    fraction = (target-b)/(b-a)
    frequency = fb+fraction*(fb-fa)
    if abs(frequency) >= ADC/2:
        return None, "signed_out_of_adc_range"
    return dict(signed_cfo_hz=frequency, phase_samples=(pb+fraction*step)%PERIOD), None


def evaluate_donors(target, left_inner, right_inner, rows):
    i, j = left_inner, right_inner
    if j != i+1 or not rows[i]["counter"] < target["counter"] < rows[j]["counter"]:
        raise ValueError("The original bracket isn't consecutive in its sealed Graph piece")
    if i == 0 or j == len(rows)-1:
        return None, "missing_outer_donor"
    donors = rows[i-1:j+2]
    t = target["counter"]
    if any(stream(d) != stream(target) for d in donors):
        return None, "different_lane"
    if t-donors[0]["counter"] > 4*ADC or donors[-1]["counter"]-t > 4*ADC:
        return None, "outer_spacing"
    if len({d["lift"] for d in donors}) != 1:
        return None, "different_lifts"
    left, left_problem = side_at(donors[0],donors[1],t)
    right, right_problem = side_at(donors[2],donors[3],t)
    if left_problem or right_problem:
        return None, left_problem or right_problem
    fd = abs(left["signed_cfo_hz"]-right["signed_cfo_hz"])
    pd = abs(remainder(left["phase_samples"]-right["phase_samples"],PERIOD))
    if fd > LOOSE[0] or pd > LOOSE[1]:
        return None, ("both_disagree" if fd > LOOSE[0] and pd > LOOSE[1]
                      else "carrier_disagrees" if fd > LOOSE[0] else "arrival_disagrees")
    return dict(donor_ids=[d["id"] for d in donors], left=left, right=right, carrier_gap_hz=fd,
                arrival_gap_samples=pd, outer_future_delay_s=(donors[-1]["counter"]-t)/ADC), None


def equal_count_hash(queries, count):
    return sorted(queries, key=lambda oid: sha256(HASH_SEED+oid.encode("ascii")).digest())[:count]


def plans_and_phase():
    phase = signed.document(DATA / "empty-lane-arrival-seal.json", PHASE_SEAL)
    plans = {c:signed.document(path, PLAN_PINS[c]) for c,path in PLANS.items()}
    if phase["prediction_inputs"] != PLAN_PINS or any(
            p["ledger_sha256"] != FIRST30 or p["cohort"] != c for c,p in plans.items()):
        raise ValueError("The earlier sealed carrier and arrival inputs changed")
    return plans, phase["cases"]


def original_queries(plan, candidate, phase_proof, candidate_pin):
    empty, query, proof = prepare(plan,candidate)
    proof.update(empty_short=len(empty),candidate_sha256=candidate_pin)
    if phase_proof != proof:
        raise ValueError("The original candidate-only carrier and phase proposals did not reproduce")
    return empty, query


def predict(snapshot):
    graph_pins()
    saved, phase = plans_and_phase()
    report = {}
    for cohort,cases in COHORTS.items():
        entries = original_pairs(snapshot,cohort)
        for case in cases:
            result, native, candidate, _ = candidate_packet(entries[case,"successor"])
            plan = saved[cohort]["cases"][case]
            empty, query = original_queries(plan,candidate,phase[case],result["native_sha256"])
            _, pieces, scope = signed.graph(native,candidate)
            if scope != plan["graph"]:
                raise ValueError("Candidate Graph scope differs from the original carrier plan")
            indices = {key:{row["id"]:i for i,row in enumerate(rows)} for key,rows in pieces.items()}
            kept, counts = {}, Counter()
            for oid in query:
                one, = plan["opportunities"][oid]["brackets"]
                piece = tuple(one["piece"])
                i, j = (indices[piece][one[endpoint]["observation_id"]] for endpoint in ("left","right"))
                change, why = evaluate_donors(candidate[oid],i,j,pieces[piece])
                counts[why or "retained"] += 1
                if change is not None:
                    kept[oid] = change
            report[case] = dict(graph=scope, candidate_native_sha256=result["native_sha256"], original_queries=len(query),
                                all_empty_short=len(empty), gate_counts=dict(counts), kept=kept,
                                equal_count_hash_ids=equal_count_hash(query,len(kept)))
    return dict(ledger_sha256=FIRST30, baseline_plan_sha256=PLAN_PINS, baseline_phase_sha256=PHASE_SEAL,
                protocol_sha256=digest((HERE / "empty-graph-outer-donors-protocol.md").read_bytes()), cases=report)


def measure(ids, empty, original, stock, owners):
    query = {oid:original[oid] for oid in ids}
    native = score_group(empty,query,stock)
    owned = None
    if owners is not None:
        owned = {arm:dict(owned=score_group(empty,query,stock,owners[arm]),
                          nonowned=score_group(empty,query,stock,empty-owners[arm].keys())) for arm in ARMS}
    return dict(queries=len(query), installed_empty_queries=len(query)-native["installed_positive_queries"],
                whole_scope=native, exact_owner_scope=owned)


def score(snapshot, path, pin):
    blind = signed.document(path,pin)
    if (blind["ledger_sha256"] != FIRST30 or blind["baseline_plan_sha256"] != PLAN_PINS
            or blind["baseline_phase_sha256"] != PHASE_SEAL
            or blind["protocol_sha256"] != digest((HERE / "empty-graph-outer-donors-protocol.md").read_bytes())
            or set(blind["cases"]) != {case for cases in COHORTS.values() for case in cases}):
        raise ValueError("The blinded plan belongs to a different experiment")
    saved, phase = plans_and_phase()
    results = {}
    for cohort, cases in COHORTS.items():
        entries = original_pairs(snapshot,cohort)
        for case in cases:
            case_plan = blind["cases"][case]
            row = entries[case,"installed"]
            old = signed_attempt(FIELD,row)
            result, mixed, candidate, _ = candidate_packet(entries[case,"successor"])
            if case_plan["candidate_native_sha256"] != result["native_sha256"]:
                raise ValueError("The blinded selection does not match this candidate packet")
            empty, query = original_queries(saved[cohort]["cases"][case],candidate,phase[case],result["native_sha256"])
            if (not case_plan["kept"].keys() <= query.keys() or sum(case_plan["gate_counts"].values()) != len(query)
                    or case_plan["equal_count_hash_ids"] != equal_count_hash(query,len(case_plan["kept"]))):
                raise ValueError("The screened or equal-count plan changed")
            full = signed.read_native((FIELD / row["attempt"]).parent / "publication",old["native_sha256"])
            if old["raw_identity"] != result["raw_identity"] or full["provenance"]["detector_sha256"] != "sha256:"+signed.FULL:
                raise ValueError("Need the paired installed full receiver on the same signed source")
            stock = signed.opportunities(full)
            signed.bind_pair(full,mixed,stock,candidate)
            witness = named_rows(case,old)
            owners = signed.owners(witness,old["evidence"]["owners"]) if witness else None
            controls = {"original":query.keys(), "consistent":case_plan["kept"].keys(),
                        "equal_count_hash":case_plan["equal_count_hash_ids"]}
            variants = {k: measure(v,empty,query,stock,owners) for k,v in controls.items()}
            uniform = {label: count["interpolated"]*len(controls["consistent"])/len(query) if query else 0.
                       for label,count in variants["original"]["whole_scope"]["windows"].items()}
            delays = [row["outer_future_delay_s"] for row in case_plan["kept"].values()]
            results[case] = dict(cohort=cohort, all_empty_short=len(empty), gate_counts=case_plan["gate_counts"],
                                 same_count_uniform_expected_joint_hits=uniform, variants=variants,
                                 outer_future_delay_median_s=median(delays) if delays else None,
                                 outer_future_delay_max_s=max(delays,default=None), installed_sha256=old["native_sha256"])
    return dict(prediction_sha256=pin, cases=results)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("snapshot",type=Path)
    sub = p.add_subparsers(dest="action",required=True)
    sub.add_parser("predict")
    p_score = sub.add_parser("score")
    p_score.add_argument("prediction",type=Path)
    p_score.add_argument("sha256")
    args = p.parse_args()
    sys.addaudithook(lambda event,params: saved_only(event,params,prediction=args.action=="predict"))
    answer = predict(args.snapshot) if args.action=="predict" else score(args.snapshot,args.prediction,args.sha256)
    print(json.dumps(answer,sort_keys=True,separators=(",",":"),allow_nan=False))
