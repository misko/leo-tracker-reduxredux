"""Freeze omitted-lane proposals from a masked original Graph, then score."""

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import gzip
import json
from math import isfinite, remainder
from pathlib import Path
from statistics import median
import sys

from .ds30_evidence_transfer import INSTALLED_0049, INSTALLED_0049_SHA, bind_publication, deny_backing, signed
from .track_cfo_denoise import graph_pins
from directed_donor import ADC, PERIOD, arrival_phase


HERE = Path(__file__).resolve().parent
PROTOCOL = HERE/"odd-short-interpolation-protocol.md"
CASES = {
    "DS30-0049": (2, "7514497ea681194487e8d85aecf2d739e996abf2b90566d446f81fe38875c36b"),
    "DS30-0086": (1, "407765fa47754cc99556143888b286e88f4674ab21836d3f437ac8af4c2ca439"),
}
STREAM = ("edge", "channel", "actual_rf_hz")
LANE = (*STREAM, "receiver_id")
HERTZ = "fractional_tracking_cfo_hz"
WINDOWS = ((250, 2), (2250, 6))
SOURCE_RECIPE = ["full", *(["short_primary"]*7)]
OWNER_0086 = Path("/tmp/leo-v3-field-stock-saved-0086-01/candidate/crossover-worker.json")
OWNER_0086_PIN = "36c964fe7e2cf12ed2d322bf85dc52f82f3f67877fbeb929ce35873f63b2bcf5"


def mask(native):
    """Use only visit authority and erase held candidates before any selection."""
    source, provenance = native["source"], native["provenance"]
    session = source["session_id"]
    count, previous = Counter(), {}
    visit_ids, masked, held, modes = [], [], {}, Counter()
    rows = source["probes"]
    for left, right in zip(rows[::2], rows[1::2], strict=True):
        stream = tuple(left[k] for k in STREAM)
        counter, visit = left["valid_start_counter"], left["visit_index"]
        if ([left["receiver_id"], right["receiver_id"]] != [0, 1]
                or any(left[k] != right[k] for k in (*STREAM, "valid_start_counter", "visit_index"))
                or stream in previous and previous[stream] >= counter):
            raise ValueError("Expected the original ordered stereo opportunity")
        visit_ids.append(visit)
        index = count[stream]
        count[stream] += 1
        previous[stream] = counter
        modes["full" if index % 8 == 0 else "short_primary"] += 2
        for row in (left, right):
            visible = dict(row, candidates=[]) if index % 2 else row
            if index % 2:
                oid = signed.tag(f"{session}:{visible['receiver_id']}:{counter}".encode())
                if oid in held:
                    raise ValueError("Repeated unmeasured lane")
                held[oid] = dict(lane=tuple(visible[k] for k in LANE), counter=counter, visit=visit)
            masked.append(visible)
    excluded = [row["visit"] for row in provenance["excluded_windows"]]
    if (visit_ids != sorted(visit_ids) or sorted(visit_ids + excluded) != list(range(provenance["window_count"]))
            or len(visit_ids) != provenance["processed_windows"]):
        raise ValueError("Admitted and excluded source visits must partition the signed acquisition")
    detector = provenance["detector_sha256"]
    digest = signed.canonical(["cancellation", source["raw_recording_authority_digest"], detector[7:], masked])
    return dict(native, source=dict(source, probes=masked, analysis_manifest_sha256=digest),
                provenance=dict(provenance, run_id="odd-short-graph-"+digest[7:39])), held, dict(modes)


def interpolate(left, middle, right):
    a = middle-left["counter"]
    b = right["counter"]-middle
    if not (0 < a <= ADC and 0 < b <= ADC and 4*a*b <= ADC**2):
        return None, "spacing"
    if left["lift"] != right["lift"]:
        return None, "ambiguous_alias_branch"
    lift = left["lift"]
    native_a, native_b = (row["factor"][HERTZ] for row in (left, right))
    lifted_a, lifted_b = (f+lift*signed.ALIAS for f in (native_a, native_b))
    if abs(lifted_b-lifted_a)*ADC > 8_000*(a+b):
        return None, "slope"
    start, end = (arrival_phase(row["counter"], row["factor"]) for row in (left, right))
    delta = remainder(end-start, PERIOD)
    if not isfinite(delta) or abs(delta) == PERIOD/2:
        return None, "ambiguous_arrival_arc"
    fraction = a/(a+b)
    lifted = lifted_a+fraction*(lifted_b-lifted_a)
    return dict(cfo_hz=lifted-lift*signed.ALIAS, lifted_cfo_hz=lifted, graph_alias_lift=lift,
                arrival=(start+fraction*delta) % PERIOD,
                donors=[left["id"], right["id"]], donor_counters=[left["counter"], right["counter"]],
                donor_full=[not row["short"] for row in (left,right)],
                left_wait_samples=a, right_wait_samples=b), "proposed"


def nominate(held, opportunities, graph):
    adjacent = defaultdict(list)
    for oid, row in opportunities.items():
        if oid in held and row["factor"] is not None:
            raise ValueError("No held candidate may enter the original Graph")
        if row["factor"] is not None:
            adjacent[tuple(row["row"][k] for k in LANE)].append(row)
    counters = {lane: [row["counter"] for row in rows] for lane, rows in adjacent.items()}
    proposals, reasons = {}, Counter()
    for oid, target in held.items():
        lane, counter = target["lane"], target["counter"]
        rows = adjacent.get(lane, ())
        middle = bisect_left(counters.get(lane, ()), counter)
        if middle == 0 or middle == len(rows):
            reasons["not_bracketed"] += 1
            continue
        left, right = (graph.get(row["id"]) for row in rows[middle-1:middle+1])
        if left is None or right is None:
            reasons["unassigned_or_ambiguous"] += 1
            continue
        if left["piece"] != right["piece"] or right["ordinal"] != left["ordinal"]+1:
            reasons["different_or_nonadjacent_piece"] += 1
            continue
        result, reason = interpolate(left, counter, right)
        reasons[reason] += 1
        if result is not None:
            proposals[oid] = result
    return proposals, dict(reasons)


def original(case, role):
    generation, pin = CASES[case]
    folder = signed.CAMPAIGN/case
    pair = signed.document(folder/"pair.json", pin)
    if (pair["state"] != "observed_pair" or not pair["verified_pair"] or not pair["chronological"]
            or pair["generation"] != generation):
        raise ValueError("Expected the exact original paired recording")
    result, pub, _ = bind_publication(folder/role/f"attempt-{generation:06d}",
                                     pair["attempt_result_sha256"][role], role, pair)
    return pair, result, pub


def candidate(case):
    pair, result, pub = original(case, "successor")
    raw = signed.document(pub/"unified-short-bootstrap.json")
    identity = result["raw_identity"]
    native, witness, _ = signed.qualified_candidate(pub, raw, result["native_sha256"], identity["region_sha256"])
    aperture = raw["held_anchor_route"]["receiver_recipe"]
    receiver = raw["receiver_audit"]
    if (aperture["rule"] != SOURCE_RECIPE or aperture["streams"] != list(STREAM)
            or receiver["recording_authority"] != identity["raw_authority_sha256"]
            or native["source"]["input_manifest_sha256"] != identity["inventory_sha256"]
            or native["source"]["session_id"] != identity["session_id"]):
        raise ValueError("Original anchor recipe or signed candidate opportunity changed")
    return pair, result, native, witness, receiver["native"]


def source_pins():
    return {path.name: signed.tag(path.read_bytes()) for path in (Path(__file__), PROTOCOL)}


def predict_case(case):
    _, result, native, _, clock = candidate(case)
    masked, held, modes = mask(native)
    if modes != clock["native_calls"]:
        raise ValueError("Predeclared aperture count disagrees with measured callback scope")
    opportunities = signed.opportunities(masked)
    graph, _, scope = signed.graph(masked, opportunities)
    if graph.keys() & held.keys():
        raise ValueError("Held outcome leaked into Graph")
    proposals, reasons = nominate(held, opportunities, graph)
    return dict(native_sha256=result["native_sha256"], masked_sha256=signed.canonical(masked),
                held_order_sha256=signed.canonical(list(held)), held_lanes=len(held),
                retained_positive_lanes=sum(row["factor"] is not None for row in opportunities.values()),
                graph=scope, eligibility=reasons, proposals=proposals)


def predict():
    graph_pins()
    return dict(sources=source_pins(), track_configuration=signed.PINS["assets/tracks.json"],
                cases={case: predict_case(case) for case in CASES})


def errors_for(proposal, counter, winner):
    target_phase = arrival_phase(counter, winner)
    return dict(hz=abs(winner[HERTZ]-proposal["cfo_hz"]),
                samples=abs(remainder(proposal["arrival"]-target_phase, PERIOD)),
                quarter_samples=abs(remainder(proposal["arrival"]+PERIOD/4-target_phase, PERIOD)))


def evaluation(held, predicted, reference):
    positive = {oid for oid in held if reference[oid]["factor"] is not None}
    scored = {oid: errors_for(proposal, held[oid]["counter"], reference[oid]["factor"])
              for oid, proposal in predicted.items() if oid in positive}
    windows = {}
    for hz, samples in WINDOWS:
        carrier = {oid for oid, row in scored.items() if row["hz"] <= hz}
        joint = {oid for oid in carrier if scored[oid]["samples"] <= samples}
        windows[f"{hz}Hz/{samples}samples"] = dict(
            carrier_only=len(carrier), both=len(joint), quarter_control=sum(scored[oid]["quarter_samples"] <= samples
                                                                          for oid in carrier),
            misses_on_positive_nominations=len(scored)-len(joint),
            unmatched_nominations=len(predicted)-len(joint),
            recall=len(joint)/len(positive) if positive else None,
            precision=len(joint)/len(predicted) if predicted else None)
    return dict(omitted_lanes=len(held), installed_positive=len(positive), proposed=len(predicted),
                positive_proposals=len(scored), installed_empty_proposals=len(predicted)-len(scored),
                uncovered_positives=len(positive)-len(scored), windows=windows), positive, scored


def installed_owners(case, installed):
    path, pin = ((INSTALLED_0049, INSTALLED_0049_SHA) if case == "DS30-0049"
                 else (OWNER_0086, OWNER_0086_PIN))
    witness = signed.document(path, pin)
    if witness["submitted_native_sha256"] != installed["native_sha256"]:
        raise ValueError("Installed owner witness used a different receiver")
    declared = installed["evidence"]["owners"]
    names = witness["ordered_owners"]
    if any(signed.canonical({oid:j for oid,j,_ in rows}) != declared[arm] for arm, rows in names.items()):
        return None
    return signed.owners(names, declared)


def score_case(case, frozen):
    pair, candidate_result, native, witness, clock = candidate(case)
    paired, installed, pub = original(case, "installed")
    if paired != pair or installed["raw_identity"] != candidate_result["raw_identity"]:
        raise ValueError("Original recording and signed inputs differ")
    stock = signed.read_native(pub, installed["native_sha256"])
    if stock["provenance"]["detector_sha256"] != "sha256:"+signed.FULL:
        raise ValueError("Expected the released full-aperture reference")
    masked, held, modes = mask(native)
    if (frozen["native_sha256"] != candidate_result["native_sha256"]
            or frozen["masked_sha256"] != signed.canonical(masked)
            or frozen["held_order_sha256"] != signed.canonical(list(held))):
        raise ValueError("Candidate-only seal differs from the original replay inputs")
    reference, retained = map(signed.opportunities, (stock, masked))
    signed.bind_pair(stock, masked, reference, retained)
    predictions = frozen["proposals"]
    coverage, positive, errors = evaluation(held, predictions, reference)
    owners = installed_owners(case, installed)
    if owners is not None:
        coverage["installed_owners"] = {}
        for arm, rows in owners.items():
            owned = set(held) & rows.keys()
            if not owned <= positive:
                raise ValueError("Installed owner must have an independent measured positive")
            coverage["installed_owners"][arm] = dict(
                omitted=len(owned), nominated=len(owned & predictions.keys()),
                joint={f"{hz}Hz/{samples}samples": sum(errors[oid]["hz"] <= hz and errors[oid]["samples"] <= samples
                                                       for oid in owned & errors.keys()) for hz, samples in WINDOWS})
    age = sorted(r["right_wait_samples"]/ADC for r in predictions.values())
    skipped = len(held)
    return dict(coverage, installed_native_sha256=installed["native_sha256"], graph=frozen["graph"],
                original_graph=witness["ports"]["graph"]["graph"], eligibility=frozen["eligibility"],
                drop_only=dict(proposals=0, omitted_hits=0, false_nominations=0,
                               retained_graph_points=frozen["graph"]["assigned"],
                               retained_positive_lanes=frozen["retained_positive_lanes"]),
                callbacks=dict(skipped_lanes=skipped, skipped_stereo_visits=skipped//2, original=modes,
                               estimated_callback_s={metric: skipped*clock[f"native_{metric}_ns"]["short_primary"]
                                                     /modes["short_primary"]/1e9 for metric in ("wall", "cpu")}),
                right_donor_wait_s=dict(min=age[0], median=median(age), max=age[-1]) if age else None,
                eof_buffer_payload_bytes=dict(short=skipped*80_000*4, full=skipped*200_000*4))


def score(path, pin):
    frozen = signed.document(path, pin)
    if frozen["sources"] != source_pins() or set(frozen["cases"]) != set(CASES):
        raise ValueError("Expected separately sealed unmodified two-case blind predictions")
    return dict(prediction_seal=pin, cases={case: score_case(case, frozen["cases"][case]) for case in CASES})


def deny_installed_outcomes(event, args):
    if event == "open" and isinstance(args[0], (bytes, str)):
        from os import fsdecode

        path = Path(fsdecode(args[0])).resolve()
        if path.is_relative_to(signed.CAMPAIGN) and "installed" in path.parts:
            raise ValueError("Prediction stage cannot open any original installed outcome")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("predict", "score"))
    parser.add_argument("prediction", type=Path, nargs="?")
    parser.add_argument("sha256", nargs="?")
    options = parser.parse_args()
    sys.addaudithook(deny_backing)
    if options.mode == "predict":
        sys.addaudithook(deny_installed_outcomes)
        rows = predict()
    else:
        if options.prediction is None or options.sha256 is None:
            parser.error("Scoring needs the independently sealed prediction and digest")
        rows = score(options.prediction, options.sha256)
    print(json.dumps(rows, sort_keys=True, allow_nan=False, separators=(",", ":")))
