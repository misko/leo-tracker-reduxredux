"""Conditional three-point denoising on the original signed candidate Graph."""

import argparse
from collections import Counter, defaultdict
import json
from math import remainder
from pathlib import Path
import sys
from unittest.mock import patch

from .anchor_cfo_innovation import compare_errors
from .calibration_transport import FIELD, FIRST30, signed_attempt
from .capped_revisit import HERTZ, SAMPLE_RATE, STREAM, candidate_packet, saved_only, signed
from .ds30_paired_inputs import checked, digest
from signed_cfo_time import ALIAS, blocks, epoch


HERE = Path(__file__).resolve().parent
DATA = HERE / "measurements"
OLD_GRAPH = "734598d6f5588e9ce36a012ae32215b601628e11a8c421474bdc3e5d48b675f9"
COHORTS = {"development": ("DS30-0049",), "held": ("DS30-0019", "DS30-0274", "DS30-0086")}
DEVELOPMENT_PLAN = "53b74ecf735c731ddf2df5604715a205403d4c9256fd42b552bc166246d91c04"


def bracket(left, center, right):
    """Return interpolation minus the measured middle in its original signed lift."""
    rows = (left, center, right)
    if not center["short"]:
        return None, "full_center"
    if len({tuple(row["row"][key] for key in STREAM) for row in rows}) != 1:
        return None, "rf_lane"
    a, b = ((center["counter"]-left["counter"])/SAMPLE_RATE,
            (right["counter"]-center["counter"])/SAMPLE_RATE)
    if not (0 < a <= 1 and 0 < b <= 1 and a*b <= .25):
        return None, "spacing"
    # Differences in original Graph lifts keep the short measurement's native signed branch.
    f = center["factor"][HERTZ]
    lo, hi = (row["factor"][HERTZ]-f+(row["lift"]-center["lift"])*ALIAS for row in (left, right))
    if abs(hi-lo) > 8_000*(a+b):
        return None, "slope"
    amount = (b*lo+a*hi)/(a+b)
    if abs(amount) > 250:
        return None, "innovation"
    return amount, "eligible"


def proposed_offsets(pieces):
    support, proposals = set(), {}
    counts = Counter()
    for group in pieces.values():
        support.update(row["id"] for row in group if row["short"])
        for left, center, right in zip(group, group[1:], group[2:]):
            amount, reason = bracket(left, center, right)
            counts[reason] += 1
            if amount is not None:
                aperture = f"{2-int(left['short'])-int(right['short'])}_full_neighbors"
                proposals[center["id"]] = dict(interpolation_minus_center_hz=amount,
                                                neighbors=[left["id"], right["id"]], donor_aperture=aperture,
                                                graph_alias_changes=any(row["lift"] != center["lift"]
                                                                        for row in (left, right)))
    return sorted(support), proposals, dict(counts)


def original_pairs(snapshot, cohort):
    raw = checked(snapshot / "rows-with-relocations.jsonl", FIRST30)
    cases = COHORTS[cohort]
    engaged = [row for line in raw.splitlines() if (row := json.loads(line))["verified_pair"] is True
               and row["case"] in cases]
    pairs = {(row["case"], row["algorithm"]): row for row in engaged}
    if (len(engaged) != 2*len(cases)
            or set(pairs) != {(case, role) for case in cases for role in ("installed", "successor")}):
        raise ValueError("The frozen DS30 enrollment does not contain all the needed saved pairs")
    return pairs


def graph_pins():
    from leo.analysis import glrt_frequency_input, graph_tracklets, polynomial_tracklets, tracklet_fitting
    from leo.analysis.localization_v3 import tracks
    from polynomial_fit_cache import SOURCE_PINS

    modules = (graph_tracklets, glrt_frequency_input, polynomial_tracklets, tracklet_fitting, tracks)
    for module in modules:
        path = Path(module.__file__).resolve()
        pin = signed.PINS.get(str(path.relative_to(signed.RELEASE))) or SOURCE_PINS[path.stem]
        checked(path, pin)


def predict(snapshot, cohort):
    graph_pins()
    pairs = original_pairs(snapshot, cohort)
    previous = signed.document(DATA / "signed-cfo-time-plan.json.gz", OLD_GRAPH)["candidate_only"]
    plans = {}
    for case in COHORTS[cohort]:
        row = pairs[case, "successor"]
        attempt, native, opportunities, _ = candidate_packet(row)
        _, pieces, scope = signed.graph(native, opportunities)
        if case in previous:
            prior = previous[case]
            block_plan = [dict(piece=list(key), rows=pair, curved=group[0]["curved"])
                          for key, group in pieces.items() for pair in blocks(group)]
            if prior["accepted_candidate_sha256"] != signed.canonical(native) or prior["scope"] != scope or (
                    block_plan != prior["proposed_pairs"]):
                raise ValueError("The archived candidate-only Graph piece plan changed")
        kept, proposals, counts = proposed_offsets(pieces)
        plans[case] = dict(native_sha256=attempt["native_sha256"], scope=scope, matches_previous_graph_plan=case in previous,
                           all_unambiguous_graph_shorts=kept, proposals=proposals, eligibility=counts)
    return dict(cohort=cohort, ledger_sha256=FIRST30, old_graph_plan_sha256=OLD_GRAPH, cases=plans,
                protocol_sha256=digest((HERE / "track-cfo-denoise-protocol.md").read_bytes()))


def development_graph_handoff(snapshot):
    """Expose the candidate-only proposal and original raw and lifted Graph values."""
    from leo.analysis.localization_v3 import tracks

    graph_pins()
    case = COHORTS["development"][0]
    row = original_pairs(snapshot, "development")[case, "successor"]
    result, native, opportunities, _ = candidate_packet(row)
    archived = signed.document(DATA / "track-cfo-denoise-development-plan.json.gz", DEVELOPMENT_PLAN)["cases"][case]
    graph = tracks.prepare_tracks
    packets = []

    def capture(*args, **kwargs):
        packet = graph(*args, **kwargs)
        packets.append(packet)
        return packet

    with patch.object(tracks, "prepare_tracks", capture):
        _, pieces, scope = signed.graph(native, opportunities)
    kept, corrections, audit = proposed_offsets(pieces)
    if archived != dict(native_sha256=result["native_sha256"], scope=scope, matches_previous_graph_plan=True,
                        all_unambiguous_graph_shorts=kept, proposals=corrections, eligibility=audit):
        raise ValueError("The Graph handoff did not reproduce the sealed DS30-0049 proposal")
    packet, = packets
    actual = {oid: (float(t), float(f)) for track in packet["tracks"] for oid, t, f in
              zip(track["observation_ids"], track["times"], track["values"], strict=True)}
    rows = []
    for key, group in pieces.items():
        for item in group:
            oid = item["id"]
            t, lifted = actual[oid]
            proposal = corrections.get(oid)
            rows.append(dict(observation_id=oid, piece=list(key), ordinal=item["ordinal"], sample_counter=item["counter"],
                             graph_time_s=t, measured_signed_cfo_hz=item["factor"][HERTZ], graph_alias_lift=item["lift"],
                             graph_lifted_cfo_hz=lifted, short=item["short"], **{
                                 name: item["row"][name] for name in STREAM},
                             half_blend_delta_hz=None if proposal is None else .5*proposal["interpolation_minus_center_hz"],
                             donor_ids=None if proposal is None else proposal["neighbors"]))
    if len(rows) != len(actual) or len(actual) != scope["assigned"]:
        raise ValueError("The development handoff lacks an original Graph observation")
    return dict(case=case, candidate_native_sha256=result["native_sha256"], prediction_sha256=DEVELOPMENT_PLAN,
                configuration_sha256=signed.PINS["assets/tracks.json"], graph=scope, observation_rows=rows)


def paired_rows(stock, candidate, plan):
    scope = defaultdict(list)
    coverage = Counter()
    for oid in plan["all_unambiguous_graph_shorts"]:
        narrow, wide = candidate[oid]["factor"], stock[oid]["factor"]
        if wide is None:
            coverage["candidate_only"] += 1
            continue
        if abs(epoch(narrow)-epoch(wide)) > 2:
            coverage["outside_epoch_window"] += 1
            continue
        before = narrow[HERTZ]-wide[HERTZ]
        proposed = plan["proposals"].get(oid)
        addition = proposed["interpolation_minus_center_hz"] if proposed else 0.
        row = (before, addition, proposed is not None)
        scope["epoch_close"].append(row)
        if abs(before) <= 250:
            scope["strict"].append(row)
            if proposed:
                scope[proposed["donor_aperture"]].append(row)
        elif abs(remainder(before, ALIAS)) <= 250:
            coverage["foldable_alias_epoch_close"] += 1
    coverage["proposed_without_strict_pair"] = len(plan["proposals"])-sum(p for _, _, p in scope["strict"])
    return scope, dict(coverage)


def describe(rows):
    result = {}
    for label in ("strict", "epoch_close", "0_full_neighbors", "1_full_neighbors", "2_full_neighbors"):
        samples = rows.get(label, [])
        updated = [x for x in samples if x[2]]
        views = result[label] = dict(proposed=len(updated))
        for name, subset in (("all", samples), ("proposed_only", updated)):
            metrics = {method: compare_errors([a+weight*d for a,d,_ in subset])
                       for method, weight in (("as_observed", 0.), ("half_blend", .5), ("interpolation_only", 1.))}
            views[name] = metrics
    return result


def advances(cases, pooled):
    pooled_summary = pooled["strict"]["proposed_only"]
    if not pooled_summary["as_observed"] or pooled_summary["half_blend"]["mae_hz"] > .95*pooled_summary["as_observed"]["mae_hz"]:
        return False
    for item in cases.values():
        values = item["errors"]["strict"]
        if values["proposed"] < 100:
            return False
        a, b = (values["proposed_only"][method] for method in ("as_observed", "half_blend"))
        if b["rms_hz"] >= a["rms_hz"] or b["p95_absolute_hz"] > a["p95_absolute_hz"]:
            return False
    return True


def score(snapshot, path, sha):
    plans = signed.document(path, sha)
    cohort = plans["cohort"]
    if plans["ledger_sha256"] != FIRST30 or set(plans["cases"]) != set(COHORTS[cohort]):
        raise ValueError("The sealed candidate plan has unexpected custody or enrollment")
    rows = original_pairs(snapshot, cohort)
    totals, results = defaultdict(list), {}
    for case in COHORTS[cohort]:
        entry = rows[case, "installed"]
        subject = rows[case, "successor"]
        old = signed_attempt(FIELD, entry)
        stock = signed.read_native((FIELD / entry["attempt"]).parent / "publication", old["native_sha256"])
        result, native, candidate, _ = candidate_packet(subject)
        plan = plans["cases"][case]
        if old["raw_identity"] != result["raw_identity"] or stock["provenance"]["detector_sha256"] != "sha256:"+signed.FULL:
            raise ValueError("The installed packet is not the same authenticated field input")
        original = signed.opportunities(stock)
        signed.bind_pair(stock, native, original, candidate)
        witness = signed.document((FIELD / subject["attempt"]).parent / "publication/exact-named-raw-witness.json")
        graph_scope = witness["ports"]["graph"]["graph"]
        if (plan["native_sha256"] != result["native_sha256"]
                or witness["evidence"]["detail"]["input_sha256"] != plan["native_sha256"]
                or witness["evidence"]["detail"]["terminal_sha256"] != subject["terminal_sha256"]
                or any(plan["scope"][key] != graph_scope[key] for key in ("tracks", "assigned"))):
            raise ValueError("The candidate Graph replay does not match the exact field witness")
        observations, coverage = paired_rows(original, candidate, plan)
        for k, values in observations.items():
            totals[k].extend(values)
        results[case] = dict(errors=describe(observations), coverage=coverage, graph=plan["scope"],
                             eligibility=plan["eligibility"], proposed_count=len(plan["proposals"]),
                             proposed_alias_crossings=sum(x["graph_alias_changes"] for x in plan["proposals"].values()),
                             installed_native_sha256=old["native_sha256"])
    pooled = describe(totals)
    return dict(cohort=cohort, prediction_sha256=sha, cases=results, pooled=pooled,
                advances=cohort == "held" and advances(results, pooled))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    command = parser.add_subparsers(dest="action", required=True)
    command.add_parser("predict").add_argument("cohort", choices=COHORTS)
    command.add_parser("development-graph-handoff")
    sc = command.add_parser("score")
    sc.add_argument("prediction", type=Path)
    sc.add_argument("sha256")
    args = parser.parse_args()
    sys.addaudithook(lambda event, values: saved_only(event, values, prediction=args.action != "score"))
    if args.action == "predict":
        output = predict(args.export, args.cohort)
    elif args.action == "development-graph-handoff":
        output = development_graph_handoff(args.export)
    else:
        output = score(args.export, args.prediction, args.sha256)
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
