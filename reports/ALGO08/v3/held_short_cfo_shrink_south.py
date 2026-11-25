"""Transfer the fixed target-masked CFO shrink to the original South history packet."""

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

from . import held_short_cfo_shrink as shrink
from . import track_cfo_denoise_south as south


odd, signed = shrink.odd, shrink.odd.signed
SOURCE = Path(__file__)
PROTOCOL = SOURCE.with_name("held-short-cfo-shrink-south-protocol.md")
OFFERS = ("containing", "near-omitted")
SAVED_STOCK = Path("/dev/shm/leo-v3-named-south-transfer-01")
SAVED_STOCK_PIN = "7653b038a30e723e46bf3a5cb690ce8a52d841378f5d60964e1708e2d51cdcca"


def candidates():
    freeze = signed.document(south.DATA/"frozen-build-geography.json", south.FREEZE)
    prior = freeze["south_existing_raw"]
    saved = freeze["proposed_saved_pair"]
    book = saved["packets"]["integrated"]
    path = Path(book["path"])
    origin = path.parents[3]
    relative = str(path.relative_to(origin))
    evidence, selected = {}, {}
    for mode in OFFERS:
        is_inside = mode == "containing"
        label = "containing" if is_inside else "omitted"
        root = origin if is_inside else origin.with_name(origin.name.removesuffix("containing")+mode)
        seal_pin = prior[label+"_prediction_seal_sha256"]
        seal = signed.document(root/"prediction-seal.json", seal_pin)
        bootstrap = "candidate/unified-short-bootstrap.json"
        selector = "candidate-held-anchor-route.json"
        raw = signed.document(root/bootstrap, seal[bootstrap])
        held = signed.document(root/selector, seal[selector])
        clock = signed.document(root/"candidate-clock.json", seal["candidate-clock.json"])["clock"]
        offer = prior[label+"_offer_sha256"]
        recipe = held["receiver_recipe"]
        native_path = root/relative
        if seal[relative] != book["sha256"]:
            raise ValueError("South offered roots do not bind the same selected packet")
        native = signed.read_native(native_path.parent, book["sha256"], path=native_path)
        scope, native_source = raw["receiver_audit"], native["source"]
        if (raw["held_anchor_route"] != held or raw["requested_offer_sha256"] != offer
                or raw["native_sha256"] != "sha256:"+book["sha256"] or held["native_sha256"] != raw["native_sha256"]
                or signed.canonical(recipe) != native["provenance"]["detector_sha256"]
                or recipe["installed_sha256"] != signed.FULL or recipe["shortened_sha256"] != signed.SPARSE
                or recipe["aperture_samples"] != [200_000, 80_000] or recipe["streams"] != list(odd.STREAM)
                or recipe["rule"] != odd.SOURCE_RECIPE or held["choice"]["route"] != "history"
                or held["refinement_calls"] or held["selected"] != 456 or held["observed"] != 1346
                or native_source["session_id"] != saved["session_id"]
                or native_source["input_manifest_sha256"] != "sha256:"+saved["inventory_sha256"]
                or native_source["raw_recording_authority_digest"] != "sha256:"+saved["raw_authority_sha256"]
                or scope["recording_authority"] != native_source["raw_recording_authority_digest"]
                or len(native_source["probes"]) != saved["ordered_probe_rows"]
                or sum(len(row["candidates"]) for row in native_source["probes"]) != held["selected"]
                or clock["exit_code"]):
            raise ValueError("South offer differs from the exact signed 20/8 history acquisition")
        evidence[mode] = dict(offer_sha256=offer, raw_prediction_seal_sha256=seal_pin, native_sha256=book["sha256"],
                              parent_native_sha256=held["parent_native_sha256"], native_calls=scope["native"]["native_calls"],
                              selected=held["selected"], before_history=held["observed"], refine_calls=held["refinement_calls"],
                              capture_authority=native_source["raw_recording_authority_digest"], raw_started_unix_ns=clock["started_unix_ns"])
        selected[mode] = native
    a, b = OFFERS
    if (selected[a] != selected[b] or evidence[a]["parent_native_sha256"] != evidence[b]["parent_native_sha256"]
            or evidence[a]["offer_sha256"] == evidence[b]["offer_sha256"]
            or evidence[a]["raw_started_unix_ns"] >= evidence[b]["raw_started_unix_ns"]):
        raise ValueError("Distinct solver offers must bind the same ordered receiver packet")
    pins = dict(custody=south.FREEZE, protocol=signed.tag(PROTOCOL.read_bytes()), source=signed.tag(SOURCE.read_bytes()),
                shrink_source=signed.tag(shrink.SOURCE.read_bytes()), odd_sources=odd.source_pins(),
                residual_grid=shrink.source_contract())
    return saved, selected[a], evidence, pins


def spacing_ceiling(held, retained):
    """Physical straddling before testing any piece membership or alias."""
    by_lane = defaultdict(list)
    for row in retained.values():
        if row["factor"] is not None:
            key = tuple(row["row"][name] for name in odd.LANE)
            by_lane[key].append(row["counter"])
    states = {}
    for oid, row in held.items():
        counter = row["counter"]
        others = by_lane[row["lane"]]
        i = bisect_left(others, counter)
        reason = "not_bracketed"
        if 0 < i < len(others):
            a, b = counter-others[i-1], others[i]-counter
            reason = "spacing" if not (0 < a <= odd.ADC and 0 < b <= odd.ADC and 4*a*b <= odd.ADC**2) else "passes"
        states[oid] = reason
    return states


def predict():
    saved, candidate, evidence, pins = candidates()
    masked, held, modes = odd.mask(candidate)
    if any(modes != row["native_calls"] for row in evidence.values()):
        raise ValueError("Odd mask differs from the original aperture accounting")
    shrink.graph_pins()
    retained = signed.opportunities(masked)
    temporal = spacing_ceiling(held, retained)
    graph, _, scope = signed.graph(masked, retained)
    if graph.keys() & held.keys():
        raise ValueError("Target leakage into the masked Graph")
    proposals, why = odd.nominate(held, retained, graph)
    original = signed.opportunities(candidate)
    positive = [oid for oid in held if original[oid]["factor"] is not None]
    changed, gates = shrink.nominate_changes(held, original, proposals)
    return dict(fixture="public_synthetic_south", stage="history_selected", exact_unfiltered_parent_available=False,
                parent_used_for_graph=False, pins=pins, offers=evidence, distinct_candidate_packets=1,
                session=saved["session_id"], inventory_sha256=saved["inventory_sha256"], held_lanes=len(held),
                held_positive_lanes=len(positive), masked_native_sha256=signed.canonical(masked),
                held_order_sha256=signed.canonical(list(held)), graph=scope, graph_rebuilds=1,
                chronological_bracket_counts=dict(Counter(temporal.values())),
                positive_chronological_bracket_counts=dict(Counter(temporal[k] for k in positive)),
                release_forecast_eligibility=why, proposals=proposals, eligible=changed, residual_gates=gates)


def stock_reference(saved):
    path = Path(saved["packets"]["installed"]["path"])
    expected = saved["packets"]["installed"]["sha256"]
    upstream = signed.document(south.NAMED, south.NAMED_SHA)
    paired = signed.document(SAVED_STOCK/"result.json", SAVED_STOCK_PIN)
    if (not upstream["qualified"] or upstream["named"]["native_sha256"] != "sha256:"+expected
            or upstream["named"]["verified"]["raw_authority"] != "sha256:"+saved["raw_authority_sha256"]
            or saved["packets"]["installed"]["acquisition_receipt_sha256"] != SAVED_STOCK_PIN or not paired["verified"]):
        raise ValueError("The installed 20 ms donor lacks original acquisition and saved handoff proof")
    sources, notes = {}, {}
    relative = path.relative_to(SAVED_STOCK/"containing")
    for mode in OFFERS:
        receipt = paired["cases"][mode]
        worker = receipt["worker"]
        source = SAVED_STOCK/mode/relative
        native = signed.read_native(source.parent, expected, path=source)
        if (native["provenance"]["detector_sha256"] != "sha256:"+signed.FULL
                or worker["detector"] != signed.FULL or worker["waveform_calls"] or worker["handoffs"] != 1
                or worker["receipt"]["session_id"] != saved["session_id"] or receipt["external_clock"]["exit_code"]):
            raise ValueError("Installed offered-region replay is not the expected saved 20 ms packet")
        sources[mode] = native
        notes[mode] = dict(native_sha256=expected, terminal_sha256=receipt["terminal_sha256"],
                           started_unix_ns=receipt["external_clock"]["started_unix_ns"], waveform_calls=0)
    if sources["containing"] != sources["near-omitted"] or notes["containing"]["started_unix_ns"] >= notes["near-omitted"]["started_unix_ns"]:
        raise ValueError("Installed offers are not the same ordered saved acquisition")
    return sources["containing"], notes


def score(path, pin):
    plan = signed.document(path, pin)
    saved, candidate, evidence, sources = candidates()
    masked, held, _ = odd.mask(candidate)
    if (plan["pins"] != sources or plan["offers"] != evidence
            or plan["masked_native_sha256"] != signed.canonical(masked)
            or plan["held_order_sha256"] != signed.canonical(list(held))):
        raise ValueError("The sealed forecast does not match the deduplicated fixture")
    original = signed.opportunities(candidate)
    eligible, gates = shrink.nominate_changes(held, original, plan["proposals"])
    if eligible != plan["eligible"] or gates != plan["residual_gates"]:
        raise ValueError("The shrink offsets differ from the sealed candidate-only decisions")
    stock, named = stock_reference(saved)
    reference = signed.opportunities(stock)
    signed.bind_pair(stock, candidate, reference, original)
    values = [shrink.aligned_errors(original[oid], reference[oid], item) for oid, item in eligible.items()]
    rows = [row for row in values if row is not None]
    return dict(prediction_sha256=pin, fixture=plan["fixture"], acquisition_authority=plan["offers"]["containing"]["capture_authority"],
                installed_offers=named, distinct_installed_packets=1, distinct_candidate_packets=1,
                held_lanes=len(held), held_installed_positive=sum(reference[oid]["factor"] is not None for oid in held),
                held_both_positive=sum(reference[oid]["factor"] is not None and original[oid]["factor"] is not None for oid in held),
                outcomes=shrink.evaluate(rows, len(values)-len(rows)),
                waveform_reads=0, ephemeris_reads=0, receiver_calls=0, solver_calls=0, graph_calls=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", nargs=2, metavar=("SEALED_PREDICTION", "SHA256"))
    args = parser.parse_args()
    sys.addaudithook(odd.deny_backing)
    if args.score:
        path, pin = args.score
        result = score(Path(path), pin)
    else:
        def candidate_only(event, operands):
            if event == "open" and isinstance(operands[0], (str, bytes)):
                from os import fsdecode

                path = Path(fsdecode(operands[0])).resolve()
                if path.is_relative_to(SAVED_STOCK) or path == south.NAMED:
                    raise ValueError("The candidate-only phase cannot open archived stock outcomes")

        sys.addaudithook(candidate_only)
        result = predict()
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
