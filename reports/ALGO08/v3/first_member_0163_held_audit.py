"""Replay the existing per-lane gate before joining previously published owners."""

from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from first_member_0163_owner_join import PAIR, PAIR_PIN
from prefix_transfer_0419 import checked, lane_key


OWNER_PIN = "734c3e6150334513ac9df965f4b41f9b6c4f0c4998a1e6afc5792383f005882a"


def scientific_receipt(result):
    """Exclude only selector timing and keep the canonical typed evidence."""
    return {k: v for k, v in result.items() if k != "selector"}


def replay():
    from empty_bootstrap import load_runtime

    load_runtime()
    from anchor_cycle_route import select_route
    from anchor_exposure import enroll
    from continued_cfo import ContinuedChanges
    from continued_cfo_trial import rebinding
    from eight_ms_held_fit import select
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.variants.carrier_continuation import Continuation

    documents = json.loads(gzip.decompress(checked(PAIR, PAIR_PIN)))["documents"]
    published = documents["integrated/detections.json"]["document"]
    witness = documents["integrated-held-anchor-route.json"]["document"]
    if witness["choice"]["route"] != "unfiltered" or witness["refinement_calls"]:
        raise ValueError("Selected packet must preserve all measured original factors")
    recipe = {k: v for k, v in witness["receiver_recipe"].items() if k != "held_native_8ms"}
    parent = rebinding(published, published["source"]["probes"], recipe)
    if (canonical_digest(parent) != witness["parent_native_sha256"]
            or canonical_digest(recipe) != witness["parent_detector_sha256"]):
        raise ValueError("Unable to recover the exact original pre-held chronology")
    packet, unchanged = select(parent, recipe)
    if (canonical_digest(packet) != canonical_digest(published)
            or canonical_digest(scientific_receipt(unchanged)) != canonical_digest(scientific_receipt(witness))):
        raise ValueError("Unmodified frozen selector did not reproduce the sealed publication")
    audited_choice = select_route(parent, audit=True)
    gate, independently = ContinuedChanges(), Continuation()
    result, totals = [], Counter()
    for probe, event in zip(parent["source"]["probes"], enroll(parent), strict=True):
        visit, order, receiver, stream, kind, _ = event
        would_refine = gate.consider(probe, kind == "short")
        _, keep, votes = independently.select(probe)
        if lane_key(probe) != (visit, receiver) or gate.lanes[-1] != ((visit, receiver), keep):
            raise ValueError("The measured chrono gate and installed replay disagree")
        totals[receiver] += would_refine
        result.append(dict(visit=visit, receiver=receiver, actual_rf_hz=probe["actual_rf_hz"], channel=probe["channel"],
                           start_counter=probe["valid_start_counter"], stream_index=order, stream=list(stream),
                           position_in_cycle=order % 8, aperture=kind, native_factors=len(probe["candidates"]),
                           continuation_votes=votes, kept_by_counterfactual_history=keep is not None,
                           would_refine=bool(would_refine), actual_refinement=False))
    if ({str(k): count for k, count in totals.items()} != witness["would_refine_by_radio"]
            or len(gate.paid) != witness["would_refine"]):
        raise ValueError("Per-lane prospective refinements disagree with aggregate sealed witness")
    # Only now open the owner list. Neither the live nor the held-mask policy
    # receives the list, any published fit, or the selected target.
    path = HERE / "measurements/first-member-0163-owner-join.json"
    book = json.loads(checked(path, OWNER_PIN))
    owners = {(row["visit"], row["receiver"]): row for row in book["comparable_nonempty_lanes"] if row["owners"]}
    reviewed = [row | {"owners": owners[row["visit"], row["receiver"]]["owners"]} for row in result
                if (row["visit"], row["receiver"]) in owners]
    if len(reviewed) != 7:
        raise ValueError("Expected exactly the seven authenticated original prefix owners")
    return dict(case="DS30-0163", input_parent_sha256=witness["parent_native_sha256"], owner_ledger_sha256=OWNER_PIN,
                acquisition_pair_sha256=PAIR_PIN, held_selector_sha256=canonical_digest(witness["receiver_recipe"]["held_native_8ms"]),
                continuation_wrapper_sha256=sha256((HERE / "continued_cfo.py").read_bytes()).hexdigest(),
                held_route=audited_choice, observed=witness["observed"], actual_refinements=witness["refinement_calls"],
                would_refine_by_radio=witness["would_refine_by_radio"], all_lane_results=result, owned_lane_review=reviewed)


if __name__ == "__main__":
    print(json.dumps(replay(), sort_keys=True, indent=2, allow_nan=False))
