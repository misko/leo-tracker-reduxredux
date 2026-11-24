"""Score two-sided signed carrier proposals on measured-empty short visits."""

import argparse
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from itertools import pairwise
import json
from math import remainder
from pathlib import Path
from statistics import median
import sys

from .calibration_transport import FIELD, FIRST30, signed_attempt
from .capped_revisit import HERTZ, SAMPLE_RATE, STREAM, candidate_packet, saved_only, signed
from .ds30_paired_inputs import digest
from .track_cfo_denoise import graph_pins
from satellite_set_transfer import ledger, named_rows
from signed_cfo_time import ALIAS, ARMS


HERE = Path(__file__).resolve().parent
DEVELOPMENT = "DS30-0049"
EXACT = {DEVELOPMENT, "DS30-0086"}
SINGLE = "unique_signed_bracket"


def stream(row):
    return tuple(row["row"][key] for key in STREAM)


def donor(row):
    factor = row["factor"]
    return dict(observation_id=row["id"], counter=row["counter"], signed_cfo_hz=factor[HERTZ],
                graph_alias_lift=row["lift"], integer_epoch_sample=factor["integer_epoch_sample"],
                fractional_epoch_offset_samples=factor["fractional_epoch_offset_samples"])


def bracket(piece, left, target, right):
    a, b = target-left["counter"], right["counter"]-target
    if not (0 < a <= 2*SAMPLE_RATE and 0 < b <= 2*SAMPLE_RATE):
        return None, "bracket_spacing"
    fraction = a/(a+b)
    x, y = (row["factor"][HERTZ]+row["lift"]*ALIAS for row in (left,right))
    if abs(y-x)*SAMPLE_RATE > 8_000*(a+b):
        return None, "lifted_secant_out_of_range"
    lifted = x+fraction*(y-x)
    if left["lift"] == right["lift"]:
        p, q = (row["factor"][HERTZ] for row in (left,right))
        choices = [p+fraction*(q-p)]
    else:
        choices = [lifted-lift*ALIAS for lift in sorted({left["lift"],right["lift"]})]
    if any(abs(hz) >= SAMPLE_RATE/2 for hz in choices):
        return None, "outside_adc_range"
    return dict(piece=list(piece), left=donor(left), right=donor(right), right_weight=fraction,
                lifted_cfo_hz=lifted, signed_centers_hz=choices, half_width_hz=min(2_250., 400.+500*a*b/SAMPLE_RATE**2)), None


def proposals(opportunities, pieces):
    empties = {oid: row for oid,row in opportunities.items() if row["short"] and row["factor"] is None}
    by_lane = defaultdict(list)
    for oid, row in empties.items():
        by_lane[stream(row)].append((row["counter"], oid))
    index = {key: (tuple(pair[0] for pair in ordered), tuple(pair[1] for pair in ordered))
             for key, group in by_lane.items() if (ordered := sorted(group))}
    gathered, rejected = defaultdict(list), defaultdict(set)
    for piece, rows in pieces.items():
        lane = stream(rows[0])
        if lane not in index or any(stream(row) != lane for row in rows):
            continue
        counters, ids = index[lane]
        for left, right in pairwise(rows):
            start, end = bisect_right(counters,left["counter"]), bisect_left(counters,right["counter"])
            for ordinal in range(start,end):
                oid = ids[ordinal]
                record, why = bracket(piece,left,counters[ordinal],right)
                if record is None:
                    rejected[oid].add(why)
                else:
                    gathered[oid].append(record)
    considered = {}
    for oid, candidates in gathered.items():
        target = empties[oid]
        state = ("multiple_graph_pieces" if len(candidates) != 1 else
                 "different_neighbor_alias_lifts" if len(candidates[0]["signed_centers_hz"]) != 1 else SINGLE)
        considered[oid] = dict(observation_id=oid, counter=target["counter"], visit_index=target["row"]["visit_index"],
                               radio=target["radio"], **{name:target["row"][name] for name in STREAM[:3]},
                               status=state, brackets=candidates)
    avoided = {oid: sorted(reasons) for oid,reasons in rejected.items() if oid not in gathered}
    return dict(empty_short_count=len(empties), opportunities=considered,
                rejected_bracket_counts=dict(Counter(why for reasons in avoided.values() for why in reasons)),
                rejected_targets_without_other_bracket=len(avoided),
                no_piece_bracket=len(empties)-len(considered)-len(avoided))


def enrollment(snapshot, cohort):
    pairs = ledger(snapshot, FIELD, 30, FIRST30)
    return {case: pair for case,pair in pairs.items() if (case == DEVELOPMENT) == (cohort == "development")}


def predict(snapshot, cohort):
    graph_pins()
    plans = {}
    for case, pair in enrollment(snapshot, cohort).items():
        path, row = pair["successor"]
        result, native, opportunities, clock = candidate_packet(row)
        boot = signed.document(path.parent / "publication/unified-short-bootstrap.json")
        proof = boot["graph_proof"]
        no_graph = proof is not None and proof["proven"] is True
        if no_graph:
            if proof["native_sha256"] != result["native_sha256"] or result["outcome"] != "withheld":
                raise ValueError("The early graph certificate does not match this selected packet")
            pieces, scope = {}, None
        else:
            _, pieces, scope = signed.graph(native,opportunities)
        plans[case] = dict(proposals(opportunities,pieces), graph=scope, early_graph_withhold=no_graph,
                           candidate_native_sha256=result["native_sha256"], native_clock=clock)
    return dict(cohort=cohort, ledger_sha256=FIRST30, cases=plans,
                protocol_sha256=digest((HERE / "empty-graph-rescue-protocol.md").read_bytes()))


def factor_readout(ids, installed, nominations):
    output = Counter()
    errors = []
    for oid in ids:
        stock = installed[oid]["factor"]
        entry = nominations.get(oid)
        if stock is not None:
            output["installed_positives"] += 1
        if entry is None:
            continue
        if entry["status"] != SINGLE:
            output[entry["status"]] += 1
            continue
        output["selected"] += 1
        if stock is None:
            output["installed_empty_selected"] += 1
            continue
        output["installed_positive_selected"] += 1
        one, = entry["brackets"]
        error = stock[HERTZ]-one["signed_centers_hz"][0]
        errors.append(abs(error))
        if abs(error) <= 400.:
            output["signed_400_hz_hits"] += 1
        if abs(error) <= one["half_width_hz"]:
            output["interval_hits"] += 1
        elif abs(remainder(error, ALIAS)) <= one["half_width_hz"]:
            output["alias_roll_only_hits"] += 1
        else:
            output["outside_interval_and_alias"] += 1
    output["all_empty_opportunities"] = len(ids)
    selected = output["selected"]
    available = output["installed_positives"]
    return dict(counts=dict(output), interval_precision=output["interval_hits"]/selected if selected else None,
                interval_recall=output["interval_hits"]/available if available else None,
                selected_positive_median_abs_error_hz=median(errors) if errors else None)


def assignment_status(original, candidate, entry):
    one, = entry["brackets"]
    left, right = (candidate.get(one[side]["observation_id"]) for side in ("left", "right"))
    if left is None or right is None:
        return "unassigned_donor"
    if left[0] != right[0]:
        return "donors_disagree"
    return "both_match_installed" if left[0] == original[0] else "both_other_owner"


def owner_scoring(case, old, witness, empty, stock, proposals_):
    rows = named_rows(case, old)
    if rows is None:
        raise ValueError("The prespecified exact owner witness is unavailable")
    owner_maps = signed.owners(rows, old["evidence"]["owners"])
    evidence = witness["evidence"]
    charted = signed.owners(evidence["owner_rows"], evidence["owner_maps"])
    exact = {}
    for arm in ARMS:
        owners = owner_maps[arm]
        targets = empty & owners.keys()
        if any(stock[oid]["factor"] is None for oid in targets):
            raise ValueError("An installed owner has no selected measurement")
        remaining = {oid for oid in empty-targets if stock[oid]["factor"] is not None}
        status = Counter()
        for oid in targets:
            entry = proposals_.get(oid)
            if entry and entry["status"] == SINGLE:
                one, = entry["brackets"]
                if abs(stock[oid]["factor"][HERTZ]-one["signed_centers_hz"][0]) <= one["half_width_hz"]:
                    status[assignment_status(owners[oid],charted[arm],entry)] += 1
        exact[arm] = dict(owned_misses=factor_readout(targets,stock,proposals_),
                          nonowned_installed_misses=factor_readout(remaining,stock,proposals_),
                          hit_donor_assignment=dict(status))
    return exact


def score(snapshot, prediction, pin):
    frozen = signed.document(prediction, pin)
    cohort = frozen["cohort"]
    pairs = enrollment(snapshot,cohort)
    if set(frozen["cases"]) != set(pairs) or frozen["ledger_sha256"] != FIRST30:
        raise ValueError("The sealed proposal does not cover the registered panel")
    reports, totals = {}, Counter()
    for case,pair in pairs.items():
        plan = frozen["cases"][case]
        path, row = pair["installed"]
        old = signed_attempt(FIELD,row)
        native = signed.read_native(path.parent/"publication",old["native_sha256"])
        candidate_path, candidate_row = pair["successor"]
        new, sparse, candidate, clock = candidate_packet(candidate_row)
        if (new["native_sha256"] != plan["candidate_native_sha256"] or new["raw_identity"] != old["raw_identity"]
                or native["provenance"]["detector_sha256"] != "sha256:"+signed.FULL or clock != plan["native_clock"]):
            raise ValueError("The score would use a different source or selection than the frozen plan")
        stock = signed.opportunities(native)
        signed.bind_pair(native,sparse,stock,candidate)
        empty = {oid for oid,lane in candidate.items() if lane["short"] and lane["factor"] is None}
        selected = plan["opportunities"]
        if len(empty) != plan["empty_short_count"] or not selected.keys() <= empty:
            raise ValueError("The empty short enrollment changed")
        witness = None
        witness_path = candidate_path.parent / "publication/exact-named-raw-witness.json"
        if witness_path.exists():
            witness = signed.document(witness_path)
            detail = witness["evidence"]["detail"]
            recorded = (witness["ports"].get("graph") or {}).get("graph")
            if detail["terminal_sha256"] != candidate_row["terminal_sha256"] or detail["input_sha256"] != new["native_sha256"]:
                raise ValueError("The Graph witness belongs to another publication")
            if plan["graph"] and recorded and recorded.get("calls") and any(
                    recorded[k] != plan["graph"][k] for k in ("assigned", "tracks")):
                raise ValueError("The Graph replay differs from its recorded scope")
        result = factor_readout(empty,stock,selected)
        totals.update(result["counts"])
        callbacks = result["counts"].get("selected",0)
        full_calls = clock["native_calls"].get("full",0)
        if callbacks and not full_calls:
            raise ValueError("Selected proposals have no same-recording full callback price")
        prices = {m: callbacks*clock[f"native_{m}_ns"]["full"]/full_calls/1.e9 if callbacks else 0.
                  for m in ("cpu","wall")}
        reports[case] = dict(native=result, installed_native_sha256=old["native_sha256"],
                             current_half_time_wall_deficit_s=candidate_row["elapsed_s"] - row["elapsed_s"]/2,
                             modeled_full_recheck=prices,
                             exact_owners=owner_scoring(case,old,witness,empty,stock,selected) if case in EXACT else None)
    px = totals["interval_hits"]/totals["selected"] if totals["selected"] else 0.
    rx = totals["interval_hits"]/totals["installed_positives"] if totals["installed_positives"] else 0.
    advance = (cohort == "held" and px >= .2 and rx >= .1 and all(
        r["owned_misses"]["interval_recall"] >= .2 for r in reports["DS30-0086"]["exact_owners"].values()))
    return dict(cohort=cohort, prediction_sha256=pin, cases=reports, pooled_counts=dict(totals),
                pooled_interval_precision=px, pooled_interval_recall=rx, advances=advance)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("predict").add_argument("cohort", choices=("development","held"))
    score_parser = commands.add_parser("score")
    score_parser.add_argument("prediction", type=Path)
    score_parser.add_argument("sha256")
    args = parser.parse_args()
    sys.addaudithook(lambda event, params: saved_only(event, params, prediction=args.action == "predict"))
    result = predict(args.export,args.cohort) if args.action == "predict" else score(args.export,args.prediction,args.sha256)
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
