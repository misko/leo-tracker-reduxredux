"""Transfer the frozen carrier and arrival query to the saved South history route."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from . import track_cfo_denoise_south as south
from .capped_revisit import owner_bounds, saved_only, signed
from .ds30_paired_inputs import digest
from .empty_graph_rescue import proposals
from .empty_lane_arrival import WINDOWS, prepare, score_group
from .track_cfo_denoise import DATA, HERE, graph_pins


def aperture_accounting(opportunities, audit, held):
    if held["choice"]["route"] != "history" or held["refinement_calls"]:
        raise ValueError("Expected an erasure-only history selection")
    calls, winners = Counter(), Counter()
    for row in opportunities.values():
        mode = "short_primary" if row["short"] else "full"
        calls[mode] += 1
        winners[mode] += row["factor"] is not None
    original = audit["factors"]
    if (dict(calls) != audit["native_calls"] or set(original) != set(calls)
            or sum(original.values()) != held["observed"] or sum(winners.values()) != held["selected"]):
        raise ValueError("Original paid native counts and the selected packet disagree")
    result = {}
    for mode in calls:
        if not 0 <= winners[mode] <= original[mode] <= calls[mode]:
            raise ValueError("Impossible short or anchor history enrollment")
        result[mode] = dict(calls=calls[mode], native_positives=original[mode],
                            selected_positives=winners[mode], native_empty=calls[mode]-original[mode],
                            erased_by_history=original[mode]-winners[mode],
                            selected_empty=calls[mode]-winners[mode])
    return result


def source():
    saved, native, opportunities, pin = south.candidate()
    freeze = signed.document(DATA / "frozen-build-geography.json", south.FREEZE)
    root = Path(saved["packets"]["integrated"]["path"]).parents[3]
    seal = signed.document(root / "prediction-seal.json",
                           freeze["south_existing_raw"]["containing_prediction_seal_sha256"])
    bootstrap = "candidate/unified-short-bootstrap.json"
    raw = signed.document(root / bootstrap, seal[bootstrap])
    held = raw["held_anchor_route"]
    accounting = aperture_accounting(opportunities, raw["receiver_audit"]["native"], held)
    return saved, native, opportunities, pin, accounting, held["parent_native_sha256"]


def predict():
    graph_pins()
    _, native, candidate, pin, accounting, parent = source()
    _, pieces, scope = signed.graph(native, candidate)
    plan = proposals(candidate, pieces)
    empty, query, proof = prepare(plan, candidate)
    if len(empty) != accounting["short_primary"]["selected_empty"]:
        raise ValueError("The frozen empty short scope does not match the candidate")
    return dict(recording="South containing simulation", candidate_native_sha256=pin, parent_native_sha256=parent,
                original_aperture_counts=accounting, graph=scope, carrier_plan=plan, phase_queries=query,
                phase_proof=proof, per_target_parent_packet="unavailable in bound saved artifacts",
                protocol_sha256=digest((HERE / "south-empty-graph-arrival-protocol.md").read_bytes()))


def score(prediction, pin):
    plan = signed.document(prediction, pin)
    saved, native, candidate, candidate_pin, accounting, parent = source()
    witness = signed.document(south.SAVED_GRAPH, south.SAVED_GRAPH_SHA)
    recorded = witness["ports"]["graph"]["graph"]
    if (candidate_pin != plan["candidate_native_sha256"] or accounting != plan["original_aperture_counts"]
            or parent != plan["parent_native_sha256"] or witness["evidence"]["detail"]["input_sha256"] != candidate_pin
            or any(plan["graph"][key] != recorded[key] for key in ("assigned", "tracks"))):
        raise ValueError("The plan does not use the authentic ordinary South Graph")
    empty, query, proof = prepare(plan["carrier_plan"], candidate)
    if query != plan["phase_queries"] or proof != plan["phase_proof"]:
        raise ValueError("The candidate-only projections changed after their seal")
    original = saved["packets"]["installed"]
    named = signed.document(south.NAMED, south.NAMED_SHA)
    if (named["qualified"] is not True or named["named"]["native_sha256"] != "sha256:"+original["sha256"]
            or named["named"]["verified"]["raw_authority"] != "sha256:"+saved["raw_authority_sha256"]):
        raise ValueError("The installed South reference does not match the signed acquisition")
    path = Path(original["path"])
    stock = signed.read_native(path.parent, original["sha256"], path=path)
    if stock["provenance"]["detector_sha256"] != "sha256:"+signed.FULL:
        raise ValueError("The comparison requires the original installed full detector")
    installed = signed.opportunities(stock)
    signed.bind_pair(stock, native, installed, candidate)
    readout = score_group(empty, query, installed)
    short = accounting["short_primary"]
    return dict(recording=plan["recording"], prediction_sha256=pin, graph=plan["graph"], phase_proof=proof,
                installed_native_sha256=original["sha256"], candidate_native_sha256=candidate_pin,
                parent_native_sha256=parent, original_aperture_counts=accounting, eligible_selected_empty=len(empty),
                quiet_reference_queries=len(query)-readout["installed_positive_queries"],
                native_empty_queries_possible=owner_bounds(short["native_empty"], len(empty), len(query)),
                history_erased_queries_possible=owner_bounds(short["erased_by_history"], len(empty), len(query)),
                carrier_abstention={k: plan["carrier_plan"][k] for k in (
                    "no_piece_bracket", "rejected_bracket_counts", "rejected_targets_without_other_bracket")},
                bracketed_target_status_counts=dict(Counter(e["status"] for e in plan["carrier_plan"]["opportunities"].values())),
                windows_hz_and_samples=WINDOWS, selected_empty_results=readout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("predict")
    score_parser = commands.add_parser("score")
    score_parser.add_argument("prediction", type=Path)
    score_parser.add_argument("sha256")
    args = parser.parse_args()
    sys.addaudithook(lambda event, params: saved_only(event, params, prediction=args.action == "predict"))
    result = predict() if args.action == "predict" else score(args.prediction, args.sha256)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
